#!/usr/bin/env bash
# Dupla — arranque local desde cero sin Docker (Linux / macOS).
# Uso:
#   ./scripts/setup-from-scratch.sh
#   ./scripts/setup-from-scratch.sh init [--install-brew-deps] [--skip-bootstrap]
#   ./scripts/setup-from-scratch.sh stop|status|help

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEV="$ROOT/scripts/dev.sh"

usage() {
  cat <<EOF
Dupla — setup local sin Docker (Linux / macOS)

Uso: $(basename "$0") [comando] [opciones]

Comandos:
  init (default)  Prepara DB, venvs, migraciones, seed y arranca servicios
  stop            Detiene servicios
  status          Estado y URLs
  help            Esta ayuda

Opciones (init):
  --install-brew-deps   macOS: brew install postgresql@16 redis y arranca servicios
  --skip-bootstrap      Omite migraciones/seed (DB ya inicializada)

Requisitos (sin --install-brew-deps):
  PostgreSQL 16+ :5432, Redis 7+ :6379, Python 3.12+, pnpm
  Usuario/db: dupla / dupla

URLs: http://localhost:5173  |  http://localhost:8000/docs
Demo: master@dupla.demo / master123
EOF
}

prepend_path_if_dir() {
  [[ -d "$1" ]] && export PATH="$1:$PATH"
}

prepare_postgres_path() {
  prepend_path_if_dir "/opt/homebrew/opt/postgresql@16/bin"
  prepend_path_if_dir "/usr/local/opt/postgresql@16/bin"
  prepend_path_if_dir "/usr/lib/postgresql/16/bin"
}

port_open() {
  python3 - "$1" "$2" <<'PY'
import socket, sys
s = socket.socket()
s.settimeout(0.5)
try:
    s.connect((sys.argv[1], int(sys.argv[2])))
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
}

wait_for_port() {
  local host="$1" port="$2" label="$3" max="${4:-90}"
  local i=0
  while (( i < max )); do
    if port_open "$host" "$port"; then
      echo "OK — $label en $host:$port"
      return 0
    fi
    echo "Esperando $label ($host:$port)… $((i + 1))/$max"
    sleep 1
    ((i++)) || true
  done
  echo "ERROR: $label no responde en $host:$port"
  exit 1
}

install_brew_deps() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: --install-brew-deps solo en macOS con Homebrew"
    exit 1
  fi
  command -v brew >/dev/null || { echo "ERROR: Homebrew no encontrado"; exit 1; }
  echo "==> Instalando PostgreSQL 16 y Redis"
  brew install postgresql@16 redis
  brew services start postgresql@16
  brew services start redis
  prepare_postgres_path
  sleep 3
}

ensure_postgres_dupla_db() {
  prepare_postgres_path
  if ! command -v psql >/dev/null; then
    cat <<'EOF'
AVISO: psql no encontrado. Crea la base manualmente:
  createuser -s dupla
  psql postgres -c "ALTER USER dupla WITH PASSWORD 'dupla';"
  createdb -O dupla dupla
EOF
    return 0
  fi
  echo "==> Usuario y base PostgreSQL dupla"
  psql postgres -v ON_ERROR_STOP=0 <<'SQL' 2>/dev/null || true
DO $$ BEGIN
  CREATE USER dupla WITH PASSWORD 'dupla' SUPERUSER;
EXCEPTION WHEN duplicate_object THEN
  ALTER USER dupla WITH PASSWORD 'dupla';
END $$;
SQL
  createdb -O dupla dupla 2>/dev/null \
    || psql postgres -v ON_ERROR_STOP=0 -c "CREATE DATABASE dupla OWNER dupla;" 2>/dev/null \
    || true
}

cmd_init() {
  local skip_bootstrap=false
  for arg in "$@"; do
    case "$arg" in
      --install-brew-deps) install_brew_deps ;;
      --skip-bootstrap) skip_bootstrap=true ;;
    esac
  done

  echo "==> Dupla — setup desde cero (sin Docker)"
  command -v pnpm >/dev/null || { echo "ERROR: instala pnpm (npm install -g pnpm)"; exit 1; }
  command -v python3 >/dev/null || { echo "ERROR: instala Python 3.12+"; exit 1; }

  ensure_postgres_dupla_db
  wait_for_port 127.0.0.1 5432 "PostgreSQL"
  wait_for_port 127.0.0.1 6379 "Redis"

  chmod +x "$DEV"
  "$DEV" setup

  if [[ "$skip_bootstrap" == false ]]; then
    "$DEV" bootstrap
  else
    echo "==> Omitiendo bootstrap"
  fi

  "$DEV" start
  echo ""
  echo "Logs: $ROOT/var/logs/"
}

main() {
  local cmd="${1:-init}"
  [[ $# -gt 0 ]] && shift
  case "$cmd" in
    init) cmd_init "$@" ;;
    stop) chmod +x "$DEV"; "$DEV" stop ;;
    status) chmod +x "$DEV"; "$DEV" status ;;
    -h|--help|help) usage ;;
    *)
      echo "Comando desconocido: $cmd"
      usage
      exit 1
      ;;
  esac
}

main "$@"
