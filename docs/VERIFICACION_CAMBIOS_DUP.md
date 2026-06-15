# Verificación integral — cambios plan DUP

**Fecha:** 15 de junio de 2026  
**Alcance:** Validación automatizada (CI), correcciones detectadas y smoke E2E local.

---

## 1. Resultados automatizados (paridad CI)

| Capa | Comando | Resultado |
|------|---------|-----------|
| Backend | `pytest tests/ -q` | **99 passed** |
| Processor | `pytest tests/ -q` | **93 passed** |
| Frontend lint | `pnpm lint` | **0 errores** |
| Frontend tests | `pnpm test` (vitest) | **5 passed** (3 archivos) |
| Frontend build | `pnpm build` | **OK** |

Variables usadas (igual que [.github/workflows/ci.yml](../.github/workflows/ci.yml)):

```bash
TEST_DATABASE_URL=postgresql+asyncpg://dupla:dupla@127.0.0.1:5432/dupla
REDIS_URL=redis://127.0.0.1:6379/0
APP_ENV=development
JWT_SECRET=ci-test-jwt-secret-minimum-32-characters-long
```

---

## 2. Correcciones aplicadas en esta verificación

### 2.1 Documentación API TENDER

- **Archivo:** [backend/app/routes/projects.py](../backend/app/routes/projects.py)
- **Cambio:** La descripción del endpoint `POST /api/projects` ahora indica que TENDER inicia en `BOOTSTRAPPING` (primer paso de la plantilla) y no puede retroceder por debajo de revisión de arquitectura.

### 2.2 Test de integración volumetría (DUP-005)

- **Archivo:** [backend/tests/test_budget_pipeline_sync.py](../backend/tests/test_budget_pipeline_sync.py)
- **Nuevo test:** `test_sync_volumetry_from_completed_job_integration` — valida en DB que un `ProjectBudgetJob` `completed` con `output.mode=budget` marca `workflow_meta.budget_pipeline.volumetry_done=true`.

### 2.3 Bug real en sync volumetría

- **Archivo:** [backend/app/domain/budget_pipeline_meta.py](../backend/app/domain/budget_pipeline_meta.py)
- **Problema:** `sync_volumetry_from_completed_job` actualizaba `workflow_meta` en memoria pero no persistía (`flush` + `flag_modified` faltaban).
- **Fix:** Añadidos `flag_modified(project, "workflow_meta")` y `await session.flush()` al final de la función.
- **Impacto:** El checkbox de volumetría en la pestaña Flujo ahora puede sincronizarse correctamente cuando el processor reporta job `completed`.

### 2.4 Conftest

- **Archivo:** [backend/tests/conftest.py](../backend/tests/conftest.py)
- **Cambio:** `project_budget_jobs` incluido explícitamente en `TRUNCATE` entre tests.

---

## 3. Smoke E2E local (stack `dev.sh`)

Prerequisitos: `./scripts/dev.sh check` → OK (Postgres :5432, Redis :6379).

Stack en ejecución (`./scripts/dev.sh status`):

| Servicio | URL | Estado |
|----------|-----|--------|
| Frontend | http://localhost:5173 | running |
| Backend | http://localhost:8000 | running |
| Processor | http://localhost:8001 | running |
| Coordination | http://localhost:8002 | running |

### Flujos API probados

| Flujo | HTTP | Resultado |
|-------|------|-----------|
| Login `master@dupla.demo` | 200 | Token JWT obtenido |
| `GET /api/me` | 200 | OK |
| `GET /api/projects` | 200 | OK |
| `POST /api/projects` (CLIENT) | 201 | Proyecto creado |
| `GET .../architecture` | 200 | OK |
| `GET .../exports/pliego.xlsx` | 200 | OK |
| `GET .../exports/documentary-report.pdf` | 200 | OK |
| `POST /api/auth/forgot-password` | 200 | OK (dev) |
| Coordination `/health` | 200 | OK |

---

## 4. Clashes: modo smoke vs real

| Componente | Verificación |
|------------|--------------|
| [coordination-service/adapters/report_mapper.py](../coordination-service/adapters/report_mapper.py) | `analysis_mode` `"smoke"` / `"real"` en el payload |
| [coordination-service/wrapper/run_clash_analysis.py](../coordination-service/wrapper/run_clash_analysis.py) | `COORDINATION_SMOKE_MODE` → `analysis_mode` + log |
| [frontend/.../WorkspaceHallazgosTab.tsx](../frontend/src/components/project-workspace/tabs/WorkspaceHallazgosTab.tsx) | Banner visible solo si `report.analysis_mode === 'smoke'` |
| [docs/INTEGRACION_FEAT_CLASHES.md](./INTEGRACION_FEAT_CLASHES.md) | Matriz smoke/real documentada (sección 11) |
| [backend/app/config.py](../backend/app/config.py) | `COORDINATION_SMOKE_MODE=true` rechazado en staging/prod |

**Nota:** En desarrollo, `scripts/dev.sh` usa `COORDINATION_SMOKE_MODE=true` por defecto. Para motor real: `COORDINATION_SMOKE_MODE=false ./scripts/dev.sh start` (requiere `DUPLA_ROOT` y acceso al motor).

---

## 5. Criterios de cierre

| Criterio | Estado |
|----------|--------|
| CI local verde (backend 99+, processor 93+, frontend lint/test/build) | Cumplido |
| Tests integración workspace sin regresión | Cumplido |
| Test integración sync volumetría | Cumplido (+ fix persistencia) |
| Descripción TENDER alineada | Cumplido |
| Stack local + flujos API críticos | Cumplido |
| analysis_mode smoke/real documentado y verificado | Cumplido |

---

## 6. Fuera de alcance (no bloqueante)

- Motor Dupla geométrico real sin `DUPLA_ROOT` / AutoCAD en el host
- SMTP productivo (solo fail-fast en prod y token dev validados por tests unitarios)
- Tests E2E con Playwright
- Suite pytest en `coordination-service` (no existe)
