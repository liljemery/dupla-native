#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
PROCESSOR_DIR="$ROOT/processor"
COORD_DIR="$ROOT/coordination-service"
FRONTEND_DIR="$ROOT/frontend"
VAR_DIR="$ROOT/var"
PID_DIR="$VAR_DIR/pids"
LOG_DIR="$VAR_DIR/logs"

DUPLA_ROOT="${DUPLA_ROOT:-$ROOT/../Dupla}"
export DUPLA_ROOT
export COORDINATION_OUTPUT_ROOT="${COORDINATION_OUTPUT_ROOT:-$VAR_DIR/coord_outputs}"
export DUPLA_CACHE_DIR="${DUPLA_CACHE_DIR:-$VAR_DIR/cache}"
export DUPLA_ARTIFACT_DIR="${DUPLA_ARTIFACT_DIR:-$VAR_DIR/artifacts}"
export COORDINATION_SMOKE_MODE="${COORDINATION_SMOKE_MODE:-true}"
export PYTHONPATH="${DUPLA_ROOT}:${COORD_DIR}:${PYTHONPATH:-}"

usage() {
  cat <<EOF
Uso: $(basename "$0") <comando>

Comandos:
  check      Verifica prerequisitos (Postgres, Redis, Python, pnpm)
  setup      Crea venvs, directorios var/ y copia backend/.env.example si falta
  bootstrap  migrate_bootstrap + alembic + seed del backend
  start      Arranca todos los servicios en segundo plano
  stop       Detiene servicios iniciados por start
  status     Muestra PIDs y URLs

Variables útiles:
  DUPLA_ROOT                 Ruta al repo Dupla (default: ../Dupla)
  COORDINATION_OUTPUT_ROOT   Salida compartida clash (default: var/coord_outputs)
  COORDINATION_SMOKE_MODE    true para demo sin AutoCAD (default: true)
EOF
}

load_env() {
  if [[ -f "$BACKEND_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$BACKEND_DIR/.env"
    set +a
  fi
}

port_open() {
  local host="$1"
  local port="$2"
  python3 - "$host" "$port" <<'PY'
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
s = socket.socket()
s.settimeout(0.5)
try:
    s.connect((host, port))
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
}

cmd_check() {
  echo "==> Verificando prerequisitos"
  command -v python3 >/dev/null || { echo "Falta python3"; exit 1; }
  command -v pnpm >/dev/null || { echo "Falta pnpm (npm install -g pnpm)"; exit 1; }
  port_open 127.0.0.1 5432 || { echo "PostgreSQL no responde en 127.0.0.1:5432"; exit 1; }
  port_open 127.0.0.1 6379 || { echo "Redis no responde en 127.0.0.1:6379"; exit 1; }
  echo "OK — Postgres :5432, Redis :6379, python3, pnpm"
}

ensure_venv() {
  local dir="$1"
  if [[ ! -d "$dir/.venv" ]]; then
    echo "==> Creando venv en $dir"
    python3 -m venv "$dir/.venv"
    # shellcheck disable=SC1091
    source "$dir/.venv/bin/activate"
    pip install -q -r "$dir/requirements.txt"
    deactivate
  fi
}

cmd_setup() {
  echo "==> Preparando directorios"
  mkdir -p \
    "$VAR_DIR/uploads" \
    "$VAR_DIR/cache" \
    "$VAR_DIR/artifacts" \
    "$VAR_DIR/coord_outputs" \
    "$VAR_DIR/processor_outputs" \
    "$PID_DIR" \
    "$LOG_DIR" \
    "$BACKEND_DIR/var/uploads"

  if [[ ! -f "$BACKEND_DIR/.env" ]]; then
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    echo "Creado backend/.env desde .env.example"
  fi

  ensure_venv "$BACKEND_DIR"
  ensure_venv "$PROCESSOR_DIR"
  ensure_venv "$COORD_DIR"

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo "==> pnpm install (frontend)"
    (cd "$FRONTEND_DIR" && pnpm install)
  fi

  echo "OK — setup completo"
}

wait_for_db() {
  local deadline=$((SECONDS + 60))
  while (( SECONDS < deadline )); do
    if port_open 127.0.0.1 5432; then
      return 0
    fi
    sleep 1
  done
  echo "Timeout esperando PostgreSQL"
  exit 1
}

cmd_bootstrap() {
  load_env
  cmd_setup
  wait_for_db
  echo "==> Bootstrap backend (migrate_bootstrap + alembic + seed)"
  # shellcheck disable=SC1091
  source "$BACKEND_DIR/.venv/bin/activate"
  cd "$BACKEND_DIR"
  python -m app.db.migrate_bootstrap
  alembic upgrade head
  python -m app.seed
  deactivate
  echo "OK — base de datos lista"
}

write_pid() {
  local name="$1"
  local pid="$2"
  echo "$pid" >"$PID_DIR/$name.pid"
}

read_pid() {
  local name="$1"
  local file="$PID_DIR/$name.pid"
  if [[ -f "$file" ]]; then
    cat "$file"
  fi
}

is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

cmd_stop() {
  local name pid
  for name in frontend backend processor processor-worker coordination coordination-worker; do
    pid="$(read_pid "$name" || true)"
    if is_running "$pid"; then
      echo "Deteniendo $name (pid $pid)"
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_DIR/$name.pid"
  done
  echo "OK — servicios detenidos"
}

cmd_status() {
  local name pid
  for name in frontend backend processor processor-worker coordination coordination-worker; do
    pid="$(read_pid "$name" || true)"
    if is_running "$pid"; then
      echo "$name: running (pid $pid)"
    else
      echo "$name: stopped"
    fi
  done
  echo ""
  echo "URLs:"
  echo "  Frontend   http://localhost:5173"
  echo "  Backend    http://localhost:8000/docs"
  echo "  Processor  http://localhost:8001"
  echo "  Coordination http://localhost:8002/health"
}

cmd_start() {
  load_env
  cmd_check
  cmd_setup

  if is_running "$(read_pid backend || true)"; then
    echo "Servicios ya en ejecución. Usa: $(basename "$0") stop"
    cmd_status
    exit 0
  fi

  mkdir -p "$PID_DIR" "$LOG_DIR"

  echo "==> Arrancando backend :8000"
  # shellcheck disable=SC1091
  source "$BACKEND_DIR/.venv/bin/activate"
  (
    cd "$BACKEND_DIR"
    nohup python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 \
      >"$LOG_DIR/backend.log" 2>&1 &
    echo $! >"$PID_DIR/backend.pid"
  )
  deactivate

  echo "==> Arrancando processor API :8001"
  # shellcheck disable=SC1091
  source "$PROCESSOR_DIR/.venv/bin/activate"
  (
    cd "$PROCESSOR_DIR"
    export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
    nohup python -m uvicorn main:app --reload --host 0.0.0.0 --port 8001 \
      >"$LOG_DIR/processor.log" 2>&1 &
    echo $! >"$PID_DIR/processor.pid"
  )

  echo "==> Arrancando processor-worker"
  (
    cd "$PROCESSOR_DIR"
    export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
    nohup python worker.py >"$LOG_DIR/processor-worker.log" 2>&1 &
    echo $! >"$PID_DIR/processor-worker.pid"
  )
  deactivate

  echo "==> Arrancando coordination API :8002"
  # shellcheck disable=SC1091
  source "$COORD_DIR/.venv/bin/activate"
  (
    cd "$COORD_DIR"
    export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
    nohup python -m uvicorn main:app --reload --host 0.0.0.0 --port 8002 \
      >"$LOG_DIR/coordination.log" 2>&1 &
    echo $! >"$PID_DIR/coordination.pid"
  )

  echo "==> Arrancando coordination-worker"
  (
    cd "$COORD_DIR"
    export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
    nohup python worker.py >"$LOG_DIR/coordination-worker.log" 2>&1 &
    echo $! >"$PID_DIR/coordination-worker.pid"
  )
  deactivate

  echo "==> Arrancando frontend :5173"
  (
    cd "$FRONTEND_DIR"
    nohup pnpm dev --host 127.0.0.1 --port 5173 >"$LOG_DIR/frontend.log" 2>&1 &
    echo $! >"$PID_DIR/frontend.pid"
  )

  sleep 2
  cmd_status
  echo ""
  echo "Logs en $LOG_DIR/"
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    check) cmd_check ;;
    setup) cmd_setup ;;
    bootstrap) cmd_bootstrap ;;
    start) cmd_start ;;
    stop) cmd_stop ;;
    status) cmd_status ;;
    -h|--help|help|"") usage ;;
    *) echo "Comando desconocido: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
