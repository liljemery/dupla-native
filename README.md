# Grupo Dupla — Core (nativo)

## Descripción del sistema

**Dupla** es una plataforma web de gestión de **obras y proyectos de arquitectura** pensada para equipos internos: reúne en un solo entorno el **ciclo de vida del proyecto** (fases y flujo de trabajo), el **repositorio documental** (planos y anexos en formatos técnicos habituales, con carpetas, metadatos y trazabilidad), la **comunicación** (chat con canal general, conversaciones directas, grupos y hilo vinculado a cada obra), y la **operación** (tablero de tareas tipo Kanban, con posibilidad de filtrar por proyecto).

Cada **proyecto** se abre en un **workspace** con pestañas: datos generales, flujo y fase actual, **archivos**, entregas de planos, revisiones, **especificaciones y pliegos** (incl. integración con plantillas GA-FO cuando están disponibles), **presupuesto** y metadatos asociados, **eventos** (historial/auditoría), **materiales**, etc.

Este repositorio es un **monorepo nativo** (sin Docker): `backend`, `frontend`, `processor` y `coordination-service`. La documentación de producto está en [`docs/`](docs/README.md); detalles técnicos en [`docs/TECHNICAL.md`](docs/TECHNICAL.md).

## Requisitos

| Componente | Versión |
|------------|---------|
| **PostgreSQL** | 16+ en `127.0.0.1:5432` (user/pass/db: `dupla`) |
| **Redis** | 7+ en `127.0.0.1:6379` |
| **Python** | 3.12 o 3.13 (backend); 3.11+ (processor/coordination) |
| **Node + pnpm** | Para el frontend |

### Instalar infraestructura (macOS / Homebrew)

```bash
brew install postgresql@16 redis
brew services start postgresql@16
brew services start redis
createuser -s dupla 2>/dev/null || true
psql postgres -c "ALTER USER dupla WITH PASSWORD 'dupla';" 2>/dev/null || true
createdb -O dupla dupla 2>/dev/null || true
```

## Arranque rápido

```bash
./scripts/dev.sh setup      # venvs, var/, backend/.env
./scripts/dev.sh bootstrap  # migraciones + seed (primera vez)
./scripts/dev.sh start      # todos los servicios
```

- API: `http://localhost:8000` — Swagger: `http://localhost:8000/docs`
- Frontend: `http://localhost:5173` (proxy Vite `/api` → backend)
- Processor: `http://localhost:8001`
- Coordination: `http://localhost:8002/health`

Otros comandos: `./scripts/dev.sh check | stop | status`

Tras `start`, puedes comprobar que los microservicios responden:

```bash
curl -sf http://localhost:8001/health && echo "processor OK"
curl -sf http://localhost:8002/health && echo "coordination OK"
```

Usuarios semilla (tras `bootstrap`):

| Usuario | Nombre | Contraseña | Rol | Uso |
|---------|--------|------------|-----|-----|
| `master@dupla.demo` | María López | `master123` | GERENCIA | Administración de usuarios; visión global |
| `tester@dupla.demo` | Carlos Ruiz | `testpass123` | CONTROL | Coordinación de proyectos, chat, tablero |
| `worker@dupla.demo` | Ana Martín | `workerpass123` | PRESUPUESTO | Operación de proyecto, chat, tablero |

## Variables de entorno

Copia `backend/.env.example` → `backend/.env` (o deja que `dev.sh setup` lo haga).

Variables clave:

| Variable | Default local |
|----------|---------------|
| `DATABASE_URL` | `postgresql+asyncpg://dupla:dupla@127.0.0.1:5432/dupla` |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` |
| `PROCESSOR_URL` | `http://localhost:8001` |
| `COORDINATION_URL` | `http://localhost:8002` |
| `DUPLA_ROOT` | `../Dupla` (repo motor clash) |
| `COORDINATION_OUTPUT_ROOT` | `var/coord_outputs` |
| `COORDINATION_SMOKE_MODE` | `true` (demo sin AutoCAD) |

En producción: `JWT_SECRET`, `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS`.

## Arranque manual (por servicio)

### Backend

```bash
cd backend
source .venv/bin/activate
python -m app.db.migrate_bootstrap
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend && pnpm install && pnpm dev
```

### Processor + worker

```bash
cd processor && source .venv/bin/activate
uvicorn main:app --reload --port 8001   # terminal 1
python worker.py                         # terminal 2
```

### Coordination + worker

```bash
export DUPLA_ROOT=../Dupla
export PYTHONPATH=$DUPLA_ROOT:$(pwd)
export COORDINATION_OUTPUT_ROOT=../var/coord_outputs
export COORDINATION_SMOKE_MODE=true
cd coordination-service && source .venv/bin/activate
uvicorn main:app --reload --port 8002   # terminal 1
python worker.py                         # terminal 2
```

## Plantillas GA-FO (Excel 1:1)

- `backend/app/templates/GA-FO-01-(06-2025)-V02- Pliego de Condiciones - Arquitectura.xlsx`
- Alias: `GA-FO-01-pliego.xlsx`
- Opcional: `GA-FO-03-control-planos.xlsx`

## Pruebas

**Frontend**

```bash
cd frontend && pnpm test && pnpm build
```

**Backend** (requiere PostgreSQL en `127.0.0.1:5432`)

```bash
cd backend && source .venv/bin/activate && pytest
```

## Limpieza de cache Vision del processor

```bash
rm -rf var/cache/vision_analyze_plan
find var/artifacts -path "*/vision/*" -delete 2>/dev/null
```

## Producción (checklist mínimo)

| Variable | Requisito |
|----------|-----------|
| `APP_ENV` | `staging` o `production` |
| `JWT_SECRET` | Obligatorio; generar con `openssl rand -hex 32` (no usar el demo) |
| `SMTP_HOST` + `EMAIL_FROM` | Obligatorio para restablecimiento de contraseña |
| `COORDINATION_SMOKE_MODE` | Debe ser `false` (detección real de clashes) |
| `DUPLA_ROOT` | Repo Dupla clonado para motor de coordinación |
| `OPENAI_API_KEY` | Recomendado para presupuesto IA y asistente |

CI: GitHub Actions en `.github/workflows/ci.yml` (backend, processor, frontend).

## Estructura

- `backend/app/routes` — rutas HTTP
- `backend/app/services` — reglas de negocio
- `backend/app/repositories` — acceso a datos
- `backend/app/domain` — enums y reglas compartidas
- `frontend/src` — UI, stores Zustand, esquemas Zod
- `processor/` — microservicio presupuesto/vision + worker RQ
- `coordination-service/` — clash detection + worker RQ
- `scripts/dev.sh` — orquestación local
- `var/` — uploads, cache, artifacts, salidas clash (gitignored)
- `docs/` — documentación de producto
