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

DUPLA_ROOT="${DUPLA_ROOT:-$ROOT/motor}"

load_env() {
  if [[ -f "$BACKEND_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$BACKEND_DIR/.env"
    set +a
  fi
}

# Cargar backend/.env antes de fijar defaults (COORDINATION_SMOKE_MODE, APS, etc.)
load_env

export DUPLA_ROOT
export COORDINATION_OUTPUT_ROOT="${COORDINATION_OUTPUT_ROOT:-$VAR_DIR/coord_outputs}"
export DUPLA_CACHE_DIR="${DUPLA_CACHE_DIR:-$VAR_DIR/cache}"
export DUPLA_ARTIFACT_DIR="${DUPLA_ARTIFACT_DIR:-$VAR_DIR/artifacts}"
export COORDINATION_SMOKE_MODE="${COORDINATION_SMOKE_MODE:-false}"
export COORDINATION_MAX_WORKERS="${COORDINATION_MAX_WORKERS:-6}"
export COORDINATION_CACHE_ROOT="${COORDINATION_CACHE_ROOT:-$VAR_DIR/coord_outputs/cad_cache}"
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
  DUPLA_ROOT                 Ruta al motor de coordinación (default: motor/ en la raíz del repo)
  COORDINATION_OUTPUT_ROOT   Salida compartida clash (default: var/coord_outputs)
  COORDINATION_CACHE_ROOT    Caché CAD persistente entre corridas (default: var/coord_outputs/cad_cache)
  COORDINATION_MAX_WORKERS   Workers paralelos para extracción DWG (default: 6)
  COORDINATION_ANALYSIS_PROFILE  fast_compare_local | fast_compare | standard (auto si no se define)
  COORDINATION_SMOKE_MODE    false para detección real (default: false; override en backend/.env)
EOF
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
  if command -v dwg2dxf >/dev/null; then
    echo "OK — LibreDWG (dwg2dxf) disponible"
  else
    echo "AVISO — dwg2dxf no encontrado (presupuesto/clash con DWG binarios)."
    echo "        macOS: brew install libredwg   |   Linux: ./docker/install-libredwg.sh"
    echo "        Alternativa: sube un DXF exportado desde CAD junto a cada DWG."
  fi
  if [[ -x "$BACKEND_DIR/.venv/bin/python" ]] \
    && ! "$BACKEND_DIR/.venv/bin/python" -c "import ezdxf" 2>/dev/null; then
    echo "AVISO — backend sin ezdxf. Ejecuta: ./scripts/dev.sh setup"
  fi
  echo "OK — Postgres :5432, Redis :6379, python3, pnpm"
}

resolve_python() {
  local profile="${1:-default}"
  local candidate
  if [[ "$profile" == "backend" ]]; then
    for candidate in python3.12 python3.13; do
      if command -v "$candidate" >/dev/null; then
        echo "$candidate"
        return 0
      fi
    done
  else
    for candidate in python3.12 python3.11 python3.13; do
      if command -v "$candidate" >/dev/null; then
        echo "$candidate"
        return 0
      fi
    done
  fi
  command -v python3
}

venv_python_minor() {
  "$1/.venv/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
}

venv_site_packages_minor() {
  local dir="$1"
  local sp
  sp="$(find "$dir/.venv/lib" -maxdepth 1 -type d -name 'python3.*' 2>/dev/null | head -1)"
  if [[ -z "$sp" ]]; then
    echo ""
    return
  fi
  basename "$sp" | sed 's/^python//'
}

ensure_venv() {
  local dir="$1"
  local profile="default"
  [[ "$dir" == *backend* ]] && profile="backend"
  local py
  py="$(resolve_python "$profile")"

  if [[ -d "$dir/.venv" ]]; then
    local py_ver pkg_ver
    py_ver="$(venv_python_minor "$dir")"
    pkg_ver="$(venv_site_packages_minor "$dir")"
    if [[ -n "$pkg_ver" && "$py_ver" != "$pkg_ver" ]]; then
      echo "==> Recreando venv en $dir (Python $py_ver vs site-packages $pkg_ver)"
      rm -rf "$dir/.venv"
    fi
  fi
  if [[ ! -d "$dir/.venv" ]]; then
    echo "==> Creando venv en $dir ($("$py" --version))"
    "$py" -m venv "$dir/.venv"
  fi
  echo "==> Sincronizando dependencias en $dir"
  "$dir/.venv/bin/python" -m pip install -q -r "$dir/requirements.txt"
}

cmd_setup() {
  echo "==> Preparando directorios"
  mkdir -p \
    "$VAR_DIR/uploads" \
    "$VAR_DIR/cache" \
    "$VAR_DIR/artifacts" \
    "$VAR_DIR/coord_outputs" \
    "$VAR_DIR/coord_outputs/cad_cache" \
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

# Arranca un proceso en sesión nueva (macOS no tiene setsid; Python start_new_session sí).
launch_detached() {
  local name="$1"
  shift
  local log_file="$LOG_DIR/$name.log"
  local pid
  pid="$(
    python3 - "$log_file" "$@" <<'PY'
import subprocess
import sys

log_path = sys.argv[1]
cmd = sys.argv[2:]
with open(log_path, "a", buffering=1) as logf:
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
print(proc.pid)
PY
  )"
  write_pid "$name" "$pid"
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

stop_pid_tree() {
  local pid="$1"
  [[ -z "$pid" ]] && return 0
  if ! is_running "$pid"; then
    return 0
  fi
  # Mata hijos (uvicorn --reload, vite, etc.) y luego el proceso raíz.
  pkill -TERM -P "$pid" 2>/dev/null || true
  kill -TERM "$pid" 2>/dev/null || true
  sleep 0.5
  pkill -KILL -P "$pid" 2>/dev/null || true
  kill -KILL "$pid" 2>/dev/null || true
}

free_port() {
  local port="$1"
  local pids
  pids="$(lsof -ti:"$port" 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "Liberando puerto $port (pids huérfanos: $pids)"
    # shellcheck disable=SC2086
    kill -TERM $pids 2>/dev/null || true
    sleep 0.3
    # shellcheck disable=SC2086
    kill -KILL $pids 2>/dev/null || true
  fi
}

cmd_stop() {
  local name pid
  for name in frontend backend processor processor-worker coordination coordination-worker; do
    pid="$(read_pid "$name" || true)"
    if is_running "$pid"; then
      echo "Deteniendo $name (pid $pid)"
      stop_pid_tree "$pid"
    fi
    rm -f "$PID_DIR/$name.pid"
  done
  for port in 5173 8000 8001 8002; do
    free_port "$port"
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
  launch_detached backend bash -c "cd '$BACKEND_DIR' && source .venv/bin/activate && exec python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

  echo "==> Arrancando processor API :8001"
  launch_detached processor bash -c "cd '$PROCESSOR_DIR' && source .venv/bin/activate && export REDIS_URL='${REDIS_URL:-redis://127.0.0.1:6379/0}' && exec python -m uvicorn main:app --reload --host 0.0.0.0 --port 8001"

  echo "==> Arrancando processor-worker"
  launch_detached processor-worker bash -c "cd '$PROCESSOR_DIR' && source .venv/bin/activate && export REDIS_URL='${REDIS_URL:-redis://127.0.0.1:6379/0}' && exec python worker.py"

  echo "==> Arrancando coordination API :8002"
  launch_detached coordination bash -c "cd '$COORD_DIR' && source .venv/bin/activate && export REDIS_URL='${REDIS_URL:-redis://127.0.0.1:6379/0}' && export COORDINATION_SMOKE_MODE='${COORDINATION_SMOKE_MODE:-false}' && export COORDINATION_OUTPUT_ROOT='${COORDINATION_OUTPUT_ROOT:-$VAR_DIR/coord_outputs}' && export COORDINATION_CACHE_ROOT='${COORDINATION_CACHE_ROOT:-$VAR_DIR/coord_outputs/cad_cache}' && export COORDINATION_MAX_WORKERS='${COORDINATION_MAX_WORKERS:-6}' && export DUPLA_ROOT='${DUPLA_ROOT:-$ROOT/motor}' && export NASAS09_DOWNLOADS='${NASAS09_DOWNLOADS:-}' && mkdir -p \"\$COORDINATION_OUTPUT_ROOT\" \"\$COORDINATION_CACHE_ROOT\" && exec python -m uvicorn main:app --reload --host 0.0.0.0 --port 8002"

  echo "==> Arrancando coordination-worker"
  launch_detached coordination-worker bash -c "cd '$COORD_DIR' && source .venv/bin/activate && export REDIS_URL='${REDIS_URL:-redis://127.0.0.1:6379/0}' && export COORDINATION_SMOKE_MODE='${COORDINATION_SMOKE_MODE:-false}' && export COORDINATION_OUTPUT_ROOT='${COORDINATION_OUTPUT_ROOT:-$VAR_DIR/coord_outputs}' && export COORDINATION_CACHE_ROOT='${COORDINATION_CACHE_ROOT:-$VAR_DIR/coord_outputs/cad_cache}' && export COORDINATION_MAX_WORKERS='${COORDINATION_MAX_WORKERS:-6}' && export DUPLA_ROOT='${DUPLA_ROOT:-$ROOT/motor}' && export NASAS09_DOWNLOADS='${NASAS09_DOWNLOADS:-}' && mkdir -p \"\$COORDINATION_OUTPUT_ROOT\" \"\$COORDINATION_CACHE_ROOT\" && exec python worker.py"

  echo "==> Arrancando frontend :5173"
  launch_detached frontend bash -c "cd '$FRONTEND_DIR' && exec pnpm dev --host 127.0.0.1 --port 5173"

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
