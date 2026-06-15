# Integración de detección de clashes — `feat/clashes-integration`

> Documento para validar la pestaña **Hallazgos** en desarrollo nativo (sin Docker). Usa `scripts/dev.sh` para orquestar el stack.

- **Branch:** `feat/clashes-integration`  
- **Base:** `feat/budget-analysis-pricing`  
- **Commits incluidos:** `bb44fb2` + `a1ba8bc`  
- **Repo:** `ChrisCip/DuplaPricingAnalysis`

---

## 1. Resumen ejecutivo

Esta branch añade el **pipeline de detección de clashes** encima del trabajo de presupuesto/pricing existente:

| Capa | Qué se entrega |
|------|----------------|
| **Motor (incluido)** | `motor/` en la raíz del monorepo — coordinación y clash detection |
| **Backend FastAPI** | Modelo `ProjectClashJob`, migraciones 031/032, rutas REST `POST/GET /api/projects/{id}/clash/jobs/*`, generación PDF humano y técnico (ReportLab) |
| **Microservicio nuevo** | `coordination-service` (HTTP API) + `coordination-worker` (RQ worker), ambos envuelven el motor Dupla |
| **Frontend React** | Pestaña **Hallazgos** real (no mock): polling cada 5 s, selector de carpeta fuente, inventario CAD, descarga de PDF humano y técnico |
| **Infra** | `coordination-service` + `coordination-worker` locales (puerto 8002, cola RQ `dupla_coordination`) |

---

## 2. Cómo bajar la branch

```bash
git fetch origin
git checkout feat/clashes-integration
git pull
```

Si tu rama local diverge, hacé `git status` y revisalo antes de tocar nada.

---

## 3. Requisitos previos

| Requisito | Por qué |
|-----------|---------|
| **PostgreSQL 16** en `127.0.0.1:5432` | DB principal |
| **Redis 7** en `127.0.0.1:6379` | Cola RQ y caché |
| **Repo `Dupla` clonado localmente** | ~~Motor externo~~ — ahora va en `motor/` dentro del monorepo |
| **Archivo `backend/.env`** | Credenciales (no se commitea) |

### 3.1 Motor de coordinación (incluido)

El motor vive en `motor/` en la raíz del monorepo. `scripts/dev.sh` usa por defecto:

```bash
DUPLA_ROOT=$REPO_ROOT/motor
```

Si lo movés a otra ubicación:

```bash
export DUPLA_ROOT=/ruta/absoluta/a/motor
```

### 3.2 Crear `backend/.env`

```bash
./scripts/dev.sh setup   # copia backend/.env.example si falta
```

Añadir credenciales (pedírselas a quien corresponda):

```dotenv
OPENAI_API_KEY=<sk-proj-...>
CLIENT_ID=<APS client id>
CLIENT_SECRET=<APS client secret>
APS_BUCKET_NAME=dupla_bucket_chris_v2
```

---

## 4. Levantar el stack

```bash
./scripts/dev.sh bootstrap   # primera vez: migraciones + seed
./scripts/dev.sh start
```

Servicios (verificá con `./scripts/dev.sh status`):

| Servicio | Puerto | Rol |
|----------|--------|-----|
| PostgreSQL | 5432 | DB principal |
| Redis | 6379 | Cola RQ y caché |
| `backend` | 8000 | FastAPI + uvicorn |
| `processor` | 8001 | Procesador presupuesto |
| `processor-worker` | — | Worker de presupuesto |
| **`coordination-service`** | **8002** | **HTTP API que envuelve el motor Dupla** |
| **`coordination-worker`** | — | **RQ worker para jobs de clash** |
| `frontend` | 5173 | Vite dev server (proxy `/api` → backend) |

Abrir el navegador en **http://localhost:5173** y entrar con:

| Usuario | Pass | Rol |
|---------|------|-----|
| `master@dupla.demo` | `master123` | GERENCIA |

---

## 5. Cómo usar la pestaña Hallazgos

1. Login → entrar a un proyecto (o crear uno nuevo).
2. Subir archivos `.dwg` a la pestaña **Archivos**, etiquetando cada uno con su disciplina (ARQ, EST, ELC, etc.).
3. Ir a la pestaña **Hallazgos**.
4. En "Información de coordinación":
   - Elegir la **Carpeta fuente** (por ejemplo `Raíz / TEST_01`).
   - El **Inventario** muestra cuántos archivos hay por disciplina.
   - Si el cuadro dice **"Listo para ejecutar análisis de clashes"**, podés correr.
5. Botón **"Ejecutar análisis"** en la cabecera derecha.
6. Estado pasa a **"ANÁLISIS EN CURSO"** y hace polling cada 5 s.
7. Cuando termina, los dos botones de PDF en el footer se habilitan:
   - **PDF revisión arquitecto** (humano, vertical, narrativa)
   - **PDF auditoría técnica** (índice landscape + detalle por incidencia)

### En modo smoke

El stack local arranca `coordination-service` con `COORDINATION_SMOKE_MODE=false` por defecto en `scripts/dev.sh` (modo real vía APS). Para demo sin credenciales APS, exporta `COORDINATION_SMOKE_MODE=true` y reinicia el worker; entonces usa el fixture de `coordination-service/fixtures/smoke_primary_incidents.json`.

Para producción se quita esa variable y se monta un host con accore disponible.

---

## 6. Detalle de los commits

### Commit 1 — `bb44fb2`

> **feat(clashes): integrate coordination jobs, PDF exports, and Hallazgos UI**

47 archivos cambiados (+5 175 / −36). Bloques principales:

#### Backend nuevo
- `app/routes/clash.py`
- `app/services/clash_service.py`
- `app/services/clash_export_service.py`
- `app/services/clash_reports/` (módulo PDF ReportLab — 7 archivos)
- `app/models/project_clash_job.py`
- `alembic/versions/031_project_clash_jobs.py`
- `alembic/versions/032_clash_job_export_metadata.py`
- `tests/test_clash_exports.py`, `test_clash_report_formatting.py`, `test_clash_report_normalize.py`
- `scripts/generate_sample_clash_pdfs.py`, `generate_tortuga_verification_pdfs.py`

#### Backend modificado (sólo adiciones)
- `app/main.py` (+2) — registra `clash.router`
- `app/config.py` (+14) — `coordination_url`, `coordination_default_profile`
- `app/models/__init__.py` (+2) — exporta `ProjectClashJob`
- `app/models/project.py` (+8) — columna `coordination_profile` + relación `clash_jobs`
- `requirements.txt` (+1) — `reportlab==4.2.5`
- `tests/conftest.py` — añade `project_clash_jobs` al TRUNCATE

#### Microservicio nuevo
- `coordination-service/` completo: `main.py`, `worker.py`, `wrapper/run_clash_analysis.py`, `adapters/`, `tasks/`, `fixtures/`

#### Frontend nuevo
- `api/structuralAnalysis.ts`
- `hooks/useStructuralAnalysisJob.ts`
- `lib/coordinationInventory.ts`
- `constants/coordinationProfiles.ts`
- `types/clashJob.ts`

#### Frontend modificado
- `components/project-workspace/tabs/WorkspaceHallazgosTab.tsx` — reemplazo completo, deja de usar el mock y conecta con la API real
- `pages/ProjectWorkspacePage.tsx` — pasa la prop `project={project}` a Hallazgos
- `components/project-workspace/ProjectWorkspaceDashboard.tsx` — usa `getProjectFilesCount` para no traer la lista entera

#### Infra
- `scripts/dev.sh` — orquestación nativa de coordination-service + coordination-worker
- Directorio compartido `var/coord_outputs` (`COORDINATION_OUTPUT_ROOT`)
- Repo Dupla externo vía `DUPLA_ROOT` (default `../Dupla`)

---

### Commit 2 — `a1ba8bc`

> **fix(clashes): restore CLASSIFIED_BUCKETS exports and keep workers alive on idle**

Dos fixes detectados al correr el stack la primera vez:

#### Fix backend
- `backend/app/domain/file_discipline.py` (+54)  
  `clash_service.py` importa `CLASSIFIED_BUCKETS`, `DISCIPLINE_BUCKETS`, `DISCIPLINE_LABELS`, `DISCIPLINE_SHORT` y `discipline_bucket()` — el módulo original sólo exponía el enum `FileDiscipline`. Se añaden las constantes y la función **sin tocar los nombres del enum** (siguen siendo `ARQUITECTURA`, `ESTRUCTURA`, etc. para no romper otros módulos del equipo).

#### Fix infra
- Workers RQ con reconexión manual si Redis corta el socket idle: reiniciar con `./scripts/dev.sh stop && ./scripts/dev.sh start`

---

## 7. Verificación rápida tras levantar

```bash
# 1. Servicios arriba
./scripts/dev.sh status

# 2. Backend sirve docs
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/docs   # → 200

# 3. Coordination service responde
curl -s http://localhost:8002/health

# 4. Worker escucha la cola
tail -5 var/logs/coordination-worker.log
# → "*** Listening on dupla_coordination..."

# 5. Tests del backend
cd backend && source .venv/bin/activate
pytest tests/test_clash_report_normalize.py tests/test_clash_report_formatting.py -q
```

---

## 8. Troubleshooting

### Error de API en la UI

Revisar logs del backend:

```bash
tail -30 var/logs/backend.log
```

- Si hay `ImportError`, revisar que el repo esté actualizado.
- Si hay error de Postgres, verificar que PostgreSQL esté en `127.0.0.1:5432`.

### "ANÁLISIS EN CURSO" no termina

El worker probablemente se desconectó de Redis:

```bash
./scripts/dev.sh stop && ./scripts/dev.sh start
tail -20 var/logs/coordination-worker.log
```

### Falta `backend/.env`

```bash
./scripts/dev.sh setup
```

### El motor Dupla no aparece

Verificar `DUPLA_ROOT`:

```bash
ls "$DUPLA_ROOT"
# Debe listar coordination/, config/, etc.
```

Si está vacío, exportá `DUPLA_ROOT` con la ruta absoluta correcta y reiniciá coordination.

---

## 9. Endpoints REST nuevos

| Método | Ruta | Uso |
|--------|------|-----|
| `POST` | `/api/projects/{id}/clash/jobs` | Encolar análisis (recibe `folder_uuid`) |
| `GET` | `/api/projects/{id}/clash/jobs/latest` | Estado del último job (polling) |
| `GET` | `.../clash/jobs/latest/exports/human.pdf` | PDF para revisión manual |
| `GET` | `.../clash/jobs/latest/exports/technical.pdf` | PDF de auditoría técnica |
| `GET` | `/api/projects/{id}/coordination/folders` | Carpetas elegibles del proyecto |
| `GET` | `/api/projects/{id}/coordination/inventory` | Conteo CAD por disciplina + blockers |

---

## 11. Matriz de entornos (smoke vs real)

| Entorno | `APP_ENV` | `COORDINATION_SMOKE_MODE` | Comportamiento |
|---------|-----------|---------------------------|----------------|
| Desarrollo local | `development` | `true` (default en `scripts/dev.sh`) | Fixtures JSON; banner «Modo demo» en pestaña Hallazgos |
| Staging / producción | `staging` / `production` | **`false` obligatorio** | Motor Dupla real; backend rechaza arranque si smoke=true |

La respuesta API incluye `analysis_mode: "smoke" | "real"` en el informe estructural para distinguir corridas simuladas.

---

- [ ] `DUPLA_ROOT` documentado en `backend/.env.example` (hecho).
- [ ] Cuando el motor real esté disponible, desactivar `COORDINATION_SMOKE_MODE` y agregar un host con accore para clash real.
- [ ] Documentar la rotación de credenciales del `.env` (las que están circulando deberían rotarse si se compartieron por chat).

---

*Documento generado automáticamente a partir de los commits `bb44fb2` y `a1ba8bc` en branch `feat/clashes-integration`.*
