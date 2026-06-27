# Despliegue — Grupo Dupla

Guía operativa para levantar Dupla en desarrollo, staging y producción. Para arquitectura de código ver [TECHNICAL.md](./TECHNICAL.md); para arranque rápido local ver [README del repositorio](../README.md).

---

## 1. Arquitectura de runtime

Dupla es un **monorepo** con seis procesos de aplicación más dos infraestructuras de datos:

| Servicio | Rol | Puerto host (típico) | Health / docs |
|----------|-----|----------------------|---------------|
| **frontend** | SPA React (Vite en dev; nginx estático en Docker) | `5173` | UI web |
| **backend** | API FastAPI, auth, proyectos, archivos, flujo | `8000` | `/docs` |
| **processor** | API presupuesto / visión | `8001` | `/health` |
| **processor-worker** | Worker RQ (jobs de presupuesto) | — | — |
| **coordination-service** | API detección de clashes | `8002` | `/health` |
| **coordination-worker** | Worker RQ (jobs CAD/clash) | — | — |
| **PostgreSQL** | Datos relacionales | `5432` | — |
| **Redis** | Colas RQ + epoch de chat | `6379` | — |

El directorio **`motor/`** es el motor de coordinación CAD (LibreDWG, extracción, clash). Se monta o exporta vía `DUPLA_ROOT` y `PYTHONPATH`.

### Flujo de tráfico HTTP

**Desarrollo nativo (`dev.sh start`):**

```
Navegador → :5173 (Vite) ──proxy /api──→ :8000 (backend)
Backend ──HTTP──→ :8001 (processor), :8002 (coordination)
Workers ──Redis──→ processor / coordination
```

**Docker Compose (sin nginx host):**

```
Navegador → :5173 (contenedor frontend/nginx) ──proxy /api──→ backend:8000
Backend ──HTTP──→ processor:8000, coordination-service:8000 (red interna Compose)
```

**Producción Windows (`app.grupodupla.com`):**

```
Internet → nginx host (:80, C:\nginx)
           ├─ /api/, /static/ → 127.0.0.1:8000 (backend en Docker)
           └─ /               → 127.0.0.1:5173 (frontend en Docker)
```

El nginx **del host** es necesario en prod Windows para límites de subida grandes (`client_max_body_size 2048m`) y un único punto de entrada en el puerto 80. La config vive en [`deploy/nginx-host.conf`](../deploy/nginx-host.conf).

---

## 2. Modos de despliegue

| Modo | Cuándo usarlo | Orquestación |
|------|---------------|--------------|
| **Nativo** | Desarrollo diario en macOS/Linux | [`scripts/dev.sh`](../scripts/dev.sh) |
| **Nativo Windows** | Dev en Windows sin Docker | [`scripts/dev_start.ps1`](../scripts/dev_start.ps1) |
| **Docker Compose** | Staging, prod on-prem, entornos reproducibles | [`docker-compose.yml`](../docker-compose.yml) |
| **Compose + Postgres externo** | Postgres ya corre fuera del stack | `docker-compose.external-db.yml` |
| **Prod Windows** | Servidor on-prem actual (Grupo Dupla) | nginx host + Compose + tarea programada |

---

## 3. Desarrollo local (nativo)

### Requisitos

- PostgreSQL 16+ en `127.0.0.1:5432` (usuario/db `dupla`)
- Redis 7+ en `127.0.0.1:6379`
- Python 3.12+ (backend), 3.11+ (processor/coordination)
- pnpm (frontend)
- Opcional: `dwg2dxf` (LibreDWG) para DWG binarios — ver [`docker/install-libredwg.sh`](../docker/install-libredwg.sh) o `brew install libredwg`

### Primera vez

```bash
./scripts/dev.sh setup      # venvs, var/, backend/.env desde .env.example
./scripts/dev.sh bootstrap  # migrate_bootstrap + alembic upgrade head + seed
./scripts/dev.sh start      # arranca los 6 procesos en background
```

Comandos útiles: `check`, `stop`, `status`. Logs en `var/logs/`.

### Windows (sin Docker)

Equivalente a `dev.sh start`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev_start.ps1
```

Requiere venvs ya creados (`dev.sh setup` en WSL, o manualmente con `python -m venv` + `pip install -r requirements.txt` en cada servicio).

---

## 4. Docker Compose

### Archivos

| Archivo | Propósito |
|---------|-----------|
| [`docker-compose.yml`](../docker-compose.yml) | Stack completo: postgres, redis, backend, workers, frontend |
| [`docker-compose.external-db.yml`](../docker-compose.external-db.yml) | Overlay: desactiva postgres del stack y apunta `DATABASE_URL` a `host.docker.internal:5432` |

### Primera vez con Postgres embebido

El volumen de Postgres es **externo** (persistencia entre recreaciones del stack):

```bash
docker volume create dupla_dupla_pg
docker compose up -d --build
```

El contenedor **backend** ejecuta automáticamente (entrypoint):

1. `python -m app.db.migrate_bootstrap` — stamp Alembic en BDs legadas sin revisión
2. `alembic upgrade head` — migraciones
3. `python -m app.seed` — datos demo (idempotente donde aplica)
4. `uvicorn` en `:8000`

### Postgres externo

Cuando Postgres ya corre en el host (contenedor u otro servicio):

```bash
docker compose -f docker-compose.yml -f docker-compose.external-db.yml up -d --build
```

Asegurarse de que Postgres escucha en `5432` y acepta conexiones desde Docker (`host.docker.internal` en Windows/macOS).

### Puertos publicados (Compose)

| Host | Contenedor | Servicio |
|------|------------|----------|
| 5432 | 5432 | postgres |
| 6379 | 6379 | redis |
| 8000 | 8000 | backend |
| 8001 | 8000 | processor |
| 8002 | 8000 | coordination-service |
| 5173 | 80 | frontend |

### Volúmenes Docker

| Volumen | Contenido |
|---------|-----------|
| `dupla_dupla_pg` | Datos PostgreSQL (externo, nombre fijo) |
| `dupla_uploads` | Archivos subidos por proyectos |
| `dupla_outputs` | Salida processor |
| `dupla_coord_outputs` | Salida clash / CAD cache |
| `dupla_cache` | Caché processor |
| `dupla_artifacts` | Artefactos processor (p. ej. visión) |

Bind mount read-only: `./motor` → `/motor` en backend, processor y coordination.

### Rebuild tras cambios

```bash
docker compose up -d --build
# Solo frontend:
docker compose up -d --build frontend
```

---

## 5. Producción Windows (on-prem)

Entorno de referencia: **Windows Server / PC dedicado**, dominio **`app.grupodupla.com`**, nginx instalado en **`C:\nginx`**, Docker Desktop o Docker Engine.

### Componentes

1. **nginx host** — termina TLS/HTTP en :80, proxy a servicios locales.
2. **Docker Compose** — backend, workers, frontend, redis (y opcionalmente postgres).
3. **Tarea programada `DuplaStartup`** — arranque automático al logon (ver script).

### Configuración nginx

Fuente de verdad en el repo: [`deploy/nginx-host.conf`](../deploy/nginx-host.conf).

- `client_max_body_size 2048m` — subidas de planos grandes (evita HTTP 413).
- `location /api/` → `http://127.0.0.1:8000`
- `location /` → `http://127.0.0.1:5173` (contenedor frontend mapeado a 5173)

Sincronizar manualmente tras `git pull`:

```powershell
cd C:\ruta\al\repo
powershell -ExecutionPolicy Bypass -File scripts\sync-nginx-host.ps1
```

### Arranque automático

Registrar una vez (PowerShell como administrador; ajustar rutas y usuario):

```powershell
Register-ScheduledTask -TaskName "DuplaStartup" `
  -Action (New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\ruta\al\repo\scripts\windows-compose-startup.ps1"') `
  -Trigger (New-ScheduledTaskTrigger -AtLogon -User "TU_USUARIO") `
  -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable) `
  -Principal (New-ScheduledTaskPrincipal -UserId "TU_USUARIO" -LogonType Interactive -RunLevel Highest)
```

El script espera 90 s a que Docker esté listo, copia `deploy/nginx-host.conf` a `C:\nginx`, reinicia nginx y ejecuta `docker compose up -d --build`. Log: `var/logs/windows-startup.log`.

### Despliegue de una nueva versión (prod)

```powershell
cd C:\ruta\al\repo
git pull
powershell -ExecutionPolicy Bypass -File scripts\sync-nginx-host.ps1   # si cambió nginx-host.conf
docker compose up -d --build
```

Verificar:

```powershell
curl http://127.0.0.1:8000/docs
curl http://127.0.0.1:5173
powershell -ExecutionPolicy Bypass -File scripts\diagnose-upload.ps1   # si hay problemas de subida
```

---

## 6. Variables de entorno

Copia [`backend/.env.example`](../backend/.env.example) → `backend/.env`. En Compose, muchas variables se **sobrescriben** en `docker-compose.yml` (hosts internos `postgres`, `redis`, etc.).

### Obligatorias en producción

| Variable | Descripción |
|----------|-------------|
| `APP_ENV` | `staging` o `production` |
| `JWT_SECRET` | Secreto ≥32 chars (`openssl rand -hex 32`) |
| `DATABASE_URL` | PostgreSQL async (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis para colas y chat |
| `CORS_ORIGINS` | Orígenes permitidos (incluir URL pública del frontend) |
| `FRONTEND_URL` | URL base para enlaces en correos |
| `SMTP_HOST` + `EMAIL_FROM` | Restablecimiento de contraseña |

### Servicios internos

| Variable | Dev nativo | Docker Compose |
|----------|------------|----------------|
| `PROCESSOR_URL` | `http://localhost:8001` | `http://processor:8000` |
| `COORDINATION_URL` | `http://localhost:8002` | `http://coordination-service:8000` |

### Motor CAD / clashes

| Variable | Default | Notas |
|----------|---------|-------|
| `DUPLA_ROOT` | `motor/` | Ruta al motor de coordinación |
| `COORDINATION_OUTPUT_ROOT` | `var/coord_outputs` | Salida de jobs clash |
| `COORDINATION_CACHE_ROOT` | `.../cad_cache` | Caché DWG/DXF entre corridas |
| `COORDINATION_SMOKE_MODE` | `false` en prod | `true` = demo sin detección real |
| `COORDINATION_MAX_WORKERS` | `6` | Paralelismo extracción DWG |
| `PROJECT_FILE_MAX_MB` | `0` (= sin límite app) | Límite adicional en backend |
| `NASAS09_DOWNLOADS` | — | Ruta opcional a planos companion |

### Integraciones opcionales

| Variable | Uso |
|----------|-----|
| `OPENAI_API_KEY` | Presupuesto IA, clasificación, Dupla Assistant |
| `APS_CLIENT_ID` / `APS_CLIENT_SECRET` | Autodesk APS (geometría DWG en viewer/clash) |
| `DEV_EXPOSE_RESET_TOKEN` | Solo dev: token de reset en respuesta API |

El frontend en imagen Docker se builda con `VITE_API_BASE=` vacío: las peticiones van al mismo origen vía proxy nginx (`/api/`).

---

## 7. Base de datos y migraciones

### Orden de arranque (backend)

1. **`migrate_bootstrap`** — Si la BD tiene tablas pero no fila en `alembic_version`, detecta la revisión por esquema y hace **stamp** antes de migrar. También inserta workspace por defecto si falta en esquemas legados.
2. **`alembic upgrade head`** — Aplica migraciones pendientes (p. ej. `046_remove_bootstrap_checklist`).
3. **`app.seed`** — Usuarios demo, plantilla de flujo, workspace. Seguro re-ejecutar en entornos de prueba; en prod revisar si se desea desactivar o usar seed mínimo.

### Comandos manuales

```bash
cd backend
source .venv/bin/activate
python -m app.db.migrate_bootstrap
alembic upgrade head
python -m app.seed   # opcional
```

En contenedor backend ocurre en cada **start/recreación** del contenedor (entrypoint). Para prod con datos reales, valorar un job de migración separado del seed.

### Backup Postgres

```bash
docker exec -t $(docker compose ps -q postgres) pg_dump -U dupla dupla > backup.sql
# Restaurar:
psql -U dupla -d dupla < backup.sql
```

---

## 8. CI/CD

GitHub Actions: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

| Job | Qué ejecuta |
|-----|-------------|
| `backend-test` | Postgres + Redis en servicios GH; `pytest tests/` |
| `processor-test` | `pytest` en processor |
| `frontend-test` | `pnpm lint`, `pnpm test`, `pnpm build` |

Se dispara en push/PR a `main` o `master`. **No despliega** automáticamente a prod; el despliegue on-prem es manual (`git pull` + `docker compose up --build`).

---

## 9. Checklist producción

- [ ] `APP_ENV=production`
- [ ] `JWT_SECRET` único y fuerte
- [ ] `COORDINATION_SMOKE_MODE=false`
- [ ] SMTP configurado para reset de contraseña
- [ ] `CORS_ORIGINS` y `FRONTEND_URL` con URL pública correcta
- [ ] Volumen `dupla_dupla_pg` (o Postgres gestionado) con backup periódico
- [ ] Volúmenes `dupla_uploads` / coord con espacio en disco suficiente
- [ ] nginx host con `2048m` y proxy `/api/` verificado (`diagnose-upload.ps1`)
- [ ] `OPENAI_API_KEY` / APS si se usan presupuesto IA o viewer
- [ ] Tarea `DuplaStartup` o servicio equivalente tras reinicio del servidor
- [ ] No commitear `backend/.env` con secretos reales

---

## 10. Troubleshooting

### HTTP 413 al subir archivos

1. Ejecutar `scripts/diagnose-upload.ps1` (Windows).
2. Confirmar que nginx **activo** tiene `client_max_body_size 2048m` (`nginx -T`).
3. Si `:80` devuelve 413 pero `:8000` no → problema en nginx host → `sync-nginx-host.ps1`.
4. Si ambos devuelven 413 → revisar `PROJECT_FILE_MAX_MB` y límites en Docker.

### Backend no arranca tras migración

- Revisar logs: `docker compose logs backend`
- Ejecutar manualmente `alembic upgrade head` dentro del contenedor
- Verificar `DATABASE_URL` (host `postgres` vs `host.docker.internal`)

### Workers no procesan jobs

- Redis accesible desde processor-worker y coordination-worker
- `docker compose ps` — workers en `running`
- Logs: `docker compose logs processor-worker coordination-worker`

### LibreDWG / DWG binarios

- Imágenes Docker compilan LibreDWG en build (`docker/install-libredwg.sh`)
- Nativo: instalar `dwg2dxf` o subir DXF exportado desde CAD

### Limpiar caché visión processor (dev)

```bash
rm -rf var/cache/vision_analyze_plan
find var/artifacts -path "*/vision/*" -delete 2>/dev/null
```

---

## 11. Scripts del repositorio

Todos bajo [`scripts/`](../scripts/).

### Orquestación y despliegue

| Script | Plataforma | Propósito |
|--------|------------|-----------|
| **`dev.sh`** | macOS / Linux | Orquestador principal de desarrollo: `check`, `setup`, `bootstrap`, `start`, `stop`, `status`. Crea `var/`, venvs, arranca backend :8000, processor :8001 + worker, coordination :8002 + worker, frontend Vite :5173. |
| **`dev_start.ps1`** | Windows | Equivalente a `dev.sh start` sin Docker: lanza los mismos 6 procesos con logs en `var/logs/`. |
| **`windows-compose-startup.ps1`** | Windows | Arranque de producción: espera Docker, sincroniza nginx desde `deploy/nginx-host.conf`, `docker compose up -d --build`. Pensado para tarea programada al logon. |
| **`sync-nginx-host.ps1`** | Windows | Copia `deploy/nginx-host.conf` → `C:\nginx\conf\nginx.conf`, valida con `nginx -t`, reinicia nginx y verifica `2048m` y `location /api/`. |
| **`diagnose-upload.ps1`** | Windows | Diagnóstico de subidas: compara config nginx en disco vs activo, listeners :80, POST de prueba a :80 y :8000 para localizar 413. |

### CAD, clashes y calidad

| Script | Propósito |
|--------|-----------|
| **`foss_cad_gate_spike.py`** | Fase 0 FOSS CAD: valida `dwg2dxf` + ezdxf sobre DWGs reales o de muestra; audita geometría DXF extraída. |
| **`dwg_convert_smoke.py`** | Smoke test DWG→DXF→geometría del pipeline CAD local (`motor/`). |
| **`test_clash_serena18.py`** | Integración end-to-end clash con planos SERENA 18; requiere backend :8000 y coordination :8002. Variable `SERENA18_ROOT` para ruta de planos. |
| **`validate_ga_fo08_pdf.py`** | Valida estructura de un PDF GA-FO-08 contra strings obligatorios del checklist de referencia. |

### Infra compartida (no en `scripts/`)

| Ruta | Propósito |
|------|-----------|
| [`docker/install-libredwg.sh`](../docker/install-libredwg.sh) | Compila e instala LibreDWG en imágenes Docker (Debian bookworm). |
| [`backend/docker-entrypoint.sh`](../backend/docker-entrypoint.sh) | Entrypoint contenedor backend: migrate_bootstrap → alembic → seed → uvicorn. |
| [`deploy/nginx-host.conf`](../deploy/nginx-host.conf) | Config nginx del **host** Windows (proxy a 8000/5173, límite 2 GB). |
| [`frontend/nginx.conf`](../frontend/nginx.conf) | Config nginx **dentro** del contenedor frontend (proxy `/api/` → `backend:8000`). |

---

## 12. Usuarios semilla (post-bootstrap)

Solo entornos de demo / primera instalación con `app.seed`:

| Email | Contraseña | Rol |
|-------|------------|-----|
| `master@dupla.demo` | `master123` | GERENCIA |
| `tester@dupla.demo` | `testpass123` | CONTROL |
| `worker@dupla.demo` | `workerpass123` | PRESUPUESTO |

En producción: cambiar contraseñas o crear usuarios reales y no depender del seed demo.

---

## Referencias

- [README](../README.md) — arranque rápido
- [TECHNICAL.md](./TECHNICAL.md) — arquitectura de código
- [docs/README.md](./README.md) — índice de documentación de producto
