# Informe de estado funcional — Dupla Native

**Fecha:** 15 de junio de 2026  
**Repositorio:** `dupla-native`  
**Alcance:** Análisis estático del código, documentación interna y verificación runtime del entorno local.

---

## 1. Resumen ejecutivo

**Dupla** es una plataforma web monorepo para equipos de arquitectura y obra. Integra gestión de proyectos, repositorio documental (DWG/DXF/PDF), chat interno, tablero Kanban, presupuesto/pliegos, detección de clashes y administración por roles.

| Indicador | Valor |
|-----------|-------|
| **Completitud global del proyecto** | **68 / 100** |
| Servicios del monorepo | 4 (backend, frontend, processor, coordination-service) |
| Routers API backend | 14 |
| Rutas SPA frontend | 14 |
| Pestañas del workspace de proyecto | 11 |
| Tests automatizados | 13 backend + 17 processor (+ tests frontend) |

### Veredictos clave

| Área | Veredicto |
|------|-----------|
| **Detección de clashes** | **Híbrida:** implementación real con motor Dupla externo cuando está configurado; **simulada por defecto en desarrollo** (`COORDINATION_SMOKE_MODE=true` en `scripts/dev.sh`) |
| **Presupuestos** | **Funcional en dos capas reales:** pipeline operativo (checklist + subcontratos en Postgres) y presupuesto maestro IA (backend → processor). El checklist manual **no** se sincroniza con el takeoff automático |
| **APIs externas** | PostgreSQL y Redis son requeridos; OpenAI, APS y SMTP son opcionales; Supabase **no se usa** |

### Verificación runtime (15/06/2026)

Estado del entorno local al generar este informe:

| Servicio | Puerto | Estado |
|----------|--------|--------|
| PostgreSQL | 5432 | **DOWN** |
| Redis | 6379 | **UP** |
| Backend FastAPI | 8000 | **DOWN** (stopped) |
| Processor | 8001 | **DOWN** (stopped) |
| Coordination-service | 8002 | **DOWN** (stopped) |
| Frontend Vite | 5173 | **DOWN** (stopped) |

> Los servicios de aplicación no estaban levantados durante la verificación. El estado funcional descrito a continuación se infiere del código fuente, la documentación interna y la configuración de desarrollo. Para validación end-to-end se requiere `./scripts/dev.sh start` con Postgres activo.

---

## 2. Arquitectura funcional

### 2.1 Diagrama de componentes

```mermaid
flowchart TB
  subgraph frontend [Frontend React :5173]
    SPA[14 rutas SPA]
    WS[Workspace 11 pestañas]
  end
  subgraph backend [Backend FastAPI :8000]
    API[14 routers REST]
    PG[(PostgreSQL)]
    RD[(Redis)]
  end
  subgraph processor [Processor :8001]
    RQ1[RQ dupla_processing]
    BudgetPipeline[Pipeline presupuesto IA]
  end
  subgraph coord [Coordination :8002]
    RQ2[RQ dupla_coordination]
    DuplaEngine[Motor Dupla externo]
  end
  SPA --> API
  API --> PG
  API --> RD
  API -->|httpx| processor
  API -->|httpx| coord
  processor --> RQ1
  coord --> RQ2
  RQ2 --> DuplaEngine
```

### 2.2 Stack tecnológico

| Capa | Tecnologías |
|------|-------------|
| Frontend | Vite 8, React 19, TypeScript, Tailwind CSS 4, Zustand, Zod, React Router 7 |
| Backend | FastAPI, SQLAlchemy 2 async, Alembic, Pydantic 2, asyncpg, JWT, bcrypt |
| Datos | PostgreSQL 16+, Redis 7+ |
| Processor | FastAPI, RQ worker, OpenAI, PyMuPDF, NumPy, disciplinas CAD |
| Coordination | FastAPI, RQ worker, ezdxf, shapely, motor Dupla vía `DUPLA_ROOT` |
| Orquestación local | `scripts/dev.sh` (sin Docker) |

### 2.3 Estructura de carpetas

```
dupla-native/
├── backend/                 # API FastAPI + PostgreSQL + Alembic
│   └── app/
│       ├── routes/          # 14 routers HTTP
│       ├── services/        # 31 servicios de negocio
│       ├── models/          # 25 modelos ORM
│       └── templates/       # Plantillas Excel GA-FO
├── frontend/                # SPA React (Vite)
│   └── src/
│       ├── pages/           # 14 pantallas
│       ├── components/      # UI, workspace, chat, flows
│       └── api/             # Cliente HTTP
├── processor/               # Microservicio presupuesto/visión + worker RQ
├── coordination-service/    # Detección de clashes + worker RQ
├── docs/                    # Documentación de producto
└── scripts/dev.sh           # setup | bootstrap | start | stop
```

### 2.4 Routers API registrados

Fuente: `backend/app/main.py`

| Router | Prefijo | Área funcional |
|--------|---------|----------------|
| `auth` | `/api/auth` | Login, tokens JWT |
| `users` | `/api` | Perfil, notificaciones |
| `ai_assistant` | `/api/me` | Asistente IA flotante |
| `modules` | `/api` | Módulos de producto |
| `projects` | `/api/projects` | CRUD proyecto, exports, hallazgos |
| `budget` | `/api/projects` | Presupuesto maestro IA |
| `clash` | `/api/projects` | Jobs de clash |
| `clash_workflow` | `/api/projects` | Workflow de hallazgos |
| `workflow_templates` | `/api/workflow-templates` | Plantillas de flujo |
| `project_lifecycle` | `/api/projects` | Archivos, fases, eventos, base precios |
| `admin` | `/api/admin` | Usuarios, workspaces |
| `dashboard` | `/api/dashboard` | KPIs Gerencia |
| `chat` | `/api/chat` | Mensajería |
| `tasks` | `/api/tasks` | Tablero Kanban |

### 2.5 Rutas SPA y workspace

**Rutas principales** (`frontend/src/App.tsx`):

| Ruta | Pantalla | Acceso |
|------|----------|--------|
| `/login` | Login | Público |
| `/app/projects` | Lista de proyectos | Autenticado |
| `/app/projects/:projectUuid` | Workspace de proyecto | Autenticado |
| `/app/chat` | Chat | Autenticado |
| `/app/tasks` | Tablero Kanban | Autenticado |
| `/app/admin` | Usuarios | Gerencia / líder |
| `/app/dashboard` | Panel KPIs | Gerencia / líder |
| `/app/flows` | Plantillas de flujo | Gerencia / líder |

**Pestañas del workspace** (`frontend/src/constants/projectWorkspaceTabs.ts`):

| ID | Etiqueta | Componente |
|----|----------|--------------|
| `hub` | Inicio | Dashboard del proyecto |
| `detalles` | Detalles | Metadatos del proyecto |
| `flujo` | Arranque y flujo | Checklist, pipeline presupuesto |
| `archivos` | Archivos | Repositorio DWG/DXF/PDF |
| `basePrecios` | Base de precios | Upload y clasificación |
| `entregaPlanos` | Control de entregas | Solicitudes de planos |
| `revisiones` | Revisiones | Revisión arquitectura |
| `hallazgos` | Hallazgos | Clash detection + workflow |
| `pliego` | Pliego | GA-FO, especificaciones |
| `presupuestoMaestro` | Presupuesto maestro | Takeoff IA |
| `eventos` | Eventos | Auditoría del proyecto |

> Las pestañas `basePrecios` y `presupuestoMaestro` están ocultas para el rol ARQUITECTURA.

### 2.6 Fases del ciclo de vida (`WorkflowPhase`)

```
BOOTSTRAPPING → AWAITING_FILES → ARCHITECTURE_REVIEW → SPECIFICATIONS
  → BUDGETING_PIPELINE → MANAGEMENT_APPROVAL → BUDGET_APPROVED → COMPLETE
```

---

## 3. Clasificación por estado de funcionamiento

### 3.1 Funcionamiento óptimo

Módulos con CRUD completo, UI cableada, persistencia real en PostgreSQL y sin mocks activos en runtime.

| Módulo | Archivos clave | Descripción |
|--------|----------------|-------------|
| **Autenticación JWT** | `backend/app/routes/auth.py`, `frontend/src/store/authStore.ts` | Login, guards, cambio de contraseña forzado |
| **Proyectos** | `backend/app/routes/projects.py`, `frontend/src/pages/ProjectsPage.tsx` | CRUD, tipos RESIDENTIAL/TENDER, multi-paso |
| **Archivos y carpetas** | `backend/app/services/project_lifecycle_service.py`, `WorkspaceArchivosTab.tsx` | Subida DWG/DXF/PDF, carpetas anidadas, paginación |
| **Chat interno** | `backend/app/routes/chat.py`, `frontend/src/pages/ChatPage.tsx` | General, DMs, grupos, sync epoch Redis |
| **Tablero Kanban** | `backend/app/routes/tasks.py`, `frontend/src/pages/TaskboardPage.tsx` | Comentarios, archivar, eliminar tarjetas |
| **Eventos de proyecto** | `project_lifecycle.py`, `WorkspaceEventosTab.tsx` | Auditoría paginada con filtros |
| **Transiciones de fase** | `backend/app/domain/workflow_phase.py` | Guards de negocio (p. ej. aprobación arquitectura) |
| **Pliegos / exports GA-FO** | `backend/app/services/pliego_template_fill.py`, `WorkspacePliegosTab.tsx` | Excel/PDF desde plantillas |
| **Flujos de trabajo** | `backend/app/routes/workflow_templates.py`, `FlowsHubPage.tsx` | CRUD plantillas editables |
| **Revisiones arquitectura** | `WorkspaceRevisionesTab.tsx` | Kanban auto al pasar fase |

### 3.2 Funcionamiento mediano

Funcional pero parcial, depende de configuración externa o tiene calidad/alcance variable.

| Módulo | % estimado | Limitación principal |
|--------|------------|----------------------|
| **Dashboard KPIs** | 72% | KPIs agregados parciales vs visión doc completa |
| **Clasificación IA archivos** | 55% | Solo nombre de archivo + MIME; no lee binarios DWG |
| **Presupuesto maestro IA** | 72% | Calidad depende de OpenAI/APS; modo `base_extraction` puede no generar filas |
| **Base de precios** | 78% | Requiere `OPENAI_API_KEY` para clasificación automática |
| **Asistente IA flotante** | 75% | Requiere `OPENAI_API_KEY`; HTTP 503 si no configurada |
| **Informe documental PDF** | 70% | Heurística de archivos + checklist; sin OCR/CAD |
| **Workflow hallazgos post-corrección** | 70% | Ingesta real; reanálisis es manual (sin re-run del motor) |
| **Clasificación DWG enriquecida** | 60% | Requiere credenciales APS + OpenAI |

### 3.3 Funcionamiento simulado o degradado

Fixtures, smoke mode, placeholders o código mock no cableado a la UI activa.

| Componente | Tipo | Detalle |
|------------|------|---------|
| **Clashes en dev** | Smoke mode | `COORDINATION_SMOKE_MODE=true` por defecto en `scripts/dev.sh:18` |
| **Fixture de clashes** | Fake data | `coordination-service/fixtures/smoke_primary_incidents.json` |
| **Tiles visuales clash** | Placeholder | `backend/app/services/clash_tile_placeholder.py` genera SVG si faltan tiles reales |
| **Reanálisis de correcciones** | Simulado | `clash_workflow_service.request_reanalysis()` registra outcome manual del usuario |
| **Mock informe estructural** | Código muerto | `frontend/src/data/mockStructuralAnalysisReport.ts` — sin imports |
| **Demo presupuesto** | Código muerto | `frontend/src/lib/projectMasterBudgetDemo.ts` — sin imports |
| **Pestaña presupuesto huérfana** | UI no cableada | `WorkspacePresupuestoTab.tsx` existe pero no se importa en ningún sitio |
| **Email SMTP** | No operativo | Variables vacías en `.env.example`; reset password no envía correos |
| **Seed demo** | Datos ficticios | Usuarios `*@dupla.demo` en `backend/app/seed.py` |
| **JWT demo** | Secret inseguro | `demo-secret-change-in-production...` en `.env.example` |

---

## 4. Porcentaje de desarrollo por etapa principal

Basado en `docs/modules/flujo-doc-vs-dupla.md`, fases `WorkflowPhase` y análisis del código.

| Etapa / Fase | % | Estado | Notas |
|--------------|---|--------|-------|
| Auth y sesión | 95% | Óptimo | JWT, roles, cambio contraseña |
| Creación y gestión de proyectos | 90% | Óptimo | RESIDENTIAL/TENDER, multi-paso, miembros |
| Carga documental (archivos) | 88% | Óptimo | DWG/DXF/PDF, carpetas, paginación, búsqueda |
| Clasificación IA | 55% | Mediano | Sin lectura binaria DWG ni OCR |
| Checklist bootstrap | 90% | Óptimo | Criterios configurables por proyecto |
| Revisión arquitectura | 85% | Óptimo | Kanban auto, guard de aprobación |
| Especificaciones / pliegos | 82% | Óptimo | GA-FO Excel/PDF |
| Pipeline presupuesto operativo | 65% | Mediano | Flags manuales en `workflow_meta.budget_pipeline` |
| Presupuesto maestro (takeoff IA) | 72% | Mediano | Pipeline real vía processor; calidad variable |
| Base de precios | 78% | Mediano | Upload + clasificación OpenAI opcional |
| Detección de clashes | 62% | Mediano/Simulado | Real con Dupla+APS; smoke por defecto en dev |
| Workflow hallazgos (BIM) | 70% | Mediano | Ingesta real; reanálisis simulado |
| Aprobación control/gerencia | 80% | Óptimo | `control_review_done` + fases |
| Chat y colaboración | 90% | Óptimo | Epoch Redis, DMs, grupos, proyecto |
| Tablero tareas | 88% | Óptimo | Comentarios, archivar, borrar |
| Admin / dashboard | 72% | Mediano | KPIs parciales vs visión doc |
| Asistente IA flotante | 75% | Mediano | Requiere `OPENAI_API_KEY` |
| Producción / DevOps | 45% | Simulado | Sin CI GitHub Actions; JWT demo; SMTP vacío |

---

## 5. Features: funcionan vs no funcionan

### 5.1 Funcionan correctamente

Requiere stack local levantado (`./scripts/dev.sh start`) con Postgres y Redis activos.

| Feature | Evidencia |
|---------|-----------|
| Login/logout y guards de rol | `POST /api/auth/token`, `RequireAuth`, `RequireElevatedAccess` |
| Workspace por proyecto con 11 pestañas | `ProjectWorkspacePage.tsx`, tabs por rol |
| Subida y organización de archivos técnicos | Validación `.dwg/.dxf/.pdf`, carpetas anidadas |
| Chat con sync epoch | `useChatSync.ts`, Redis epoch |
| Tablero Kanban global y por proyecto | `/api/tasks/board`, comentarios, archivar |
| Transiciones de fase con guards | `POST /api/projects/{uuid}/transitions` |
| Exports PDF documental y pliegos Excel | `GET .../exports/documentary-report.pdf` |
| Encolado presupuesto IA | `POST /api/projects/{uuid}/budget/jobs` → processor |
| Polling presupuesto | `GET /api/projects/{uuid}/budget/jobs/latest` (5 s) |
| Encolado clash | `POST /api/projects/{uuid}/clash/jobs` → coordination-service |
| Polling clash | `useStructuralAnalysisJob.ts` (5 s) |
| Exports PDF clash humano/técnico | `clash_export_service.py`, ReportLab |
| CRUD usuarios (Gerencia) | `/api/admin/users` |
| Plantillas de flujo editables | `/api/workflow-templates` |
| Subcontratos presupuesto | `GET/POST .../subcontracts` |
| Control de entregas de planos | `plan_delivery_request` model |

### 5.2 No funcionan o funcionan de forma limitada

| Feature | Problema | Severidad |
|---------|----------|-----------|
| Reset de contraseña por email | SMTP no configurado; `EmailService.is_configured` retorna false | Alta (prod) |
| Clash detection geométrica real | Requiere `DUPLA_ROOT`, `COORDINATION_SMOKE_MODE=false`, APS | Media (dev) |
| Takeoff automático ↔ checklist presupuesto | Desacoplados; flags manuales no validan contra processor | Media |
| Clasificación IA por contenido de plano | Solo heurística nombre/MIME | Media |
| Reanálisis post-corrección clashes | Estado manual; no re-ejecuta motor Dupla | Media |
| Parser BC3 FIEBDC completo | TODO en `processor/processors/bc3_parser.py` | Media |
| Pestaña `WorkspacePresupuestoTab` | Código huérfano, UI duplicada en `WorkspaceFlujoTab` | Baja |
| Modo `base_extraction` | Puede completar sin filas de presupuesto | Media |
| Embeddings APU matcher | Docstring desactualizado vs implementación parcial | Baja |
| CI/CD automatizado | No hay workflows en `.github/` | Alta (prod) |

---

## 6. APIs e integraciones externas

### 6.1 Tabla de servicios

| Servicio | Rol | Estado | Condición de operación |
|----------|-----|--------|------------------------|
| **PostgreSQL** | Fuente de verdad (SQLAlchemy + Alembic) | **Requerido** | `:5432`, `DATABASE_URL` |
| **Redis** | Cache módulos, epoch chat, colas RQ | **Requerido** | `:6379`, `REDIS_URL` |
| **Processor** (`:8001`) | Presupuesto IA, visión, takeoff | **Real** (cuando activo) | Worker RQ `dupla_processing` |
| **Coordination** (`:8002`) | Detección de clashes | **Real / smoke** | Worker RQ `dupla_coordination`; smoke por defecto |
| **Motor Dupla** (`DUPLA_ROOT`) | Clash geométrico CAD | **Opcional** | Repo externo, branch `refactor-clash-segmentado` |
| **OpenAI** | Asistente, visión, clasificación GA-FO | **Opcional** | `OPENAI_API_KEY`, `DUPLA_OPENAI_KEYS` |
| **Autodesk APS** | Derivados DWG (OSS + Model Derivative) | **Opcional** | `CLIENT_ID`, `CLIENT_SECRET`, bucket |
| **SMTP** | Reset de contraseña | **No configurado** | Variables vacías en `.env.example` |
| **Supabase** | — | **No usado** | Sin referencias en el repositorio |

### 6.2 Endpoints de health

| Servicio | Endpoint | Verificado |
|----------|----------|------------|
| Processor | `GET /health` | No (servicio DOWN) |
| Coordination | `GET /health` | No (servicio DOWN) |
| Backend | Sin endpoint `/health` dedicado | `/docs` como proxy |

### 6.3 Variables de entorno críticas

Fuente: `backend/.env.example`, `scripts/dev.sh`

```bash
DATABASE_URL=postgresql+asyncpg://dupla:dupla@127.0.0.1:5432/dupla
REDIS_URL=redis://127.0.0.1:6379/0
PROCESSOR_URL=http://localhost:8001
COORDINATION_URL=http://localhost:8002
JWT_SECRET=demo-secret-change-in-production-min-32-chars!!
COORDINATION_SMOKE_MODE=true   # default en dev.sh
DUPLA_ROOT=../Dupla            # motor externo clashes
OPENAI_API_KEY=                # vacío por defecto
SMTP_HOST=                     # vacío por defecto
CLIENT_ID=                       # APS vacío por defecto
```

### 6.4 Mapa de integración por dominio

| Dominio | Servicio backend | Integración externa |
|---------|------------------|---------------------|
| Auth | `auth.py` | JWT local + SMTP opcional |
| Chat | `chat.py` | Postgres + Redis epoch |
| Asistente IA | `ai_assistant_service.py` | OpenAI AsyncOpenAI + Redis historial |
| Clasificación archivos | `project_file_classification_service.py` | APS + OpenAI |
| Clashes | `clash_service.py` | coordination-service vía httpx |
| Presupuesto | `budget_service.py` | processor vía httpx |
| Módulos | `modules.py` | Redis cache opcional |

---

## 7. Errores y riesgos graves

### 7.1 Seguridad

| # | Riesgo | Ubicación | Impacto |
|---|--------|-----------|---------|
| 1 | **JWT secret demo** en producción | `backend/.env.example:6` | Compromiso de sesiones si no se rota |
| 2 | **Sin CI/CD** | No hay `.github/workflows/` | Sin gates de calidad en PRs |
| 3 | **Vulnerabilidad NuGet** | `processor/aps_integration/DuplaExtractor/` — `System.Text.Json 8.0.0` (GHSA) | Riesgo en componente .NET del extractor APS |

### 7.2 Funcionalidad rota o engañosa

| # | Problema | Ubicación | Impacto |
|---|----------|-----------|---------|
| 4 | **Email SMTP no configurado** | `email_service.py` — log warning y return silencioso | Reset password no funciona |
| 5 | **Clashes simulados por defecto** | `scripts/dev.sh:18` — `COORDINATION_SMOKE_MODE=true` | Puede inducir a pensar que la detección es fake en todos los entornos |
| 6 | **Parser BC3 incompleto** | `processor/processors/bc3_parser.py:98,123` — TODO FIEBDC | Export BC3 falla en descomposiciones complejas |
| 7 | **Takeoff desacoplado del checklist** | `workflow_meta.budget_pipeline` vs processor | Operadores marcan flags manualmente sin validación |

### 7.3 Deuda técnica

| # | Problema | Ubicación |
|---|----------|-----------|
| 8 | Mocks huérfanos sin uso | `mockStructuralAnalysisReport.ts`, `projectMasterBudgetDemo.ts` |
| 9 | Pestaña presupuesto duplicada | `WorkspacePresupuestoTab.tsx` no importada |
| 10 | Tours desactualizados | `productTours.ts` describe presupuesto como demo |
| 11 | Doc apu_matcher contradictoria | `processor/pricing/apu_matcher.py` — docstring vs implementación |

### 7.4 Regresiones documentadas en tests

| Test | Bug que cubre |
|------|---------------|
| `processor/tests/test_pipeline_cad_only_dedup.py` | Duplicados takeoff en fallback CAD-only |
| `processor/tests/test_no_duplicate_takeoffs.py` | `item_key` duplicados antes de presupuesto |
| `processor/tests/test_extract_level_markers_filter.py` | Marcadores de nivel falsos desde texto CAD |

> Estos tests existen como red de seguridad; indica que el pipeline de presupuesto ha tenido bugs de deduplicación en escenarios CAD-only.

---

## 8. Análisis profundo: Detección de clashes

### 8.1 Veredicto

**Híbrido — real cuando está configurado; simulado en desarrollo por defecto.**

| Capa | Real / Simulado | Condición |
|------|-----------------|-----------|
| Detección geométrica (Dupla runner) | **Real** | `DUPLA_ROOT` + `COORDINATION_SMOKE_MODE=false` + APS |
| Detección en dev local | **Simulada** | `COORDINATION_SMOKE_MODE=true` (default en `dev.sh`) |
| API backend + DB + workflow | **Real** | Siempre |
| Tiles visuales | **Real si existen**; **placeholder SVG** si no | `clash_tile_placeholder.py` |
| Reanálisis post-corrección | **Simulado** | Outcome manual del usuario |
| Frontend pestaña Hallazgos | **Real** | API via `useStructuralAnalysisJob.ts` |
| Mock frontend legacy | **No usado** | `mockStructuralAnalysisReport.ts` sin imports |

### 8.2 Flujo end-to-end

```mermaid
sequenceDiagram
  participant FE as Frontend Hallazgos
  participant BE as Backend FastAPI
  participant CS as Coordination :8002
  participant W as coordination-worker
  participant D as Motor Dupla

  FE->>BE: POST /clash/jobs (multipart DWG)
  BE->>CS: POST /jobs/clash-analysis
  CS->>W: RQ job
  alt smoke_mode=true
    W->>W: Carga fixture JSON
  else smoke_mode=false
    W->>D: run_nasas09_project_coordination.py
    D-->>W: primary_incidents.json
  end
  W-->>CS: report + artifacts
  BE->>CS: GET /jobs/{id} (polling)
  BE->>BE: Ingesta en project_clash_items
  FE->>BE: GET structural-analysis-report
```

### 8.3 Evidencia en código

**Modo real** — invoca subprocess al runner Dupla (`coordination-service/wrapper/run_clash_analysis.py`):

```python
if smoke_mode:
    primary = _smoke_primary_incidents(profile_slug, project_name, file_entries)
else:
    _invoke_runner(inputs_dir, registry_path, output_dir, include_disciplines)
    primary = load_json_if_exists(output_dir / "primary_incidents.json")
```

**Fixture smoke** — `coordination-service/fixtures/smoke_primary_incidents.json` (2 incidentes de ejemplo).

**Frontend real** — polling cada 5 s, sin mock:

```typescript
// frontend/src/hooks/useStructuralAnalysisJob.ts
const r = await getStructuralAnalysisReport(projectUuid, token)
```

### 8.4 Configuración para clashes reales

1. Clonar repo Dupla: `git clone ... Dupla && git checkout refactor-clash-segmentado`
2. Exportar `DUPLA_ROOT=/ruta/absoluta/a/Dupla`
3. Configurar credenciales APS en `.env`
4. Establecer `COORDINATION_SMOKE_MODE=false`
5. Levantar stack: `./scripts/dev.sh start`

---

## 9. Análisis profundo: Presupuestos

### 9.1 Veredicto

**Funcional en dos niveles; no simulado en la pestaña activa.**

| Capa | Implementación | % | Simulado |
|------|----------------|---|----------|
| Pipeline operativo | `workflow_meta.budget_pipeline`, subcontratos, UI en `WorkspaceFlujoTab.tsx` | 70% | No |
| Presupuesto maestro IA | `BudgetService` → processor → `build_budget_from_sources` | 72% | No |
| Demo/mock legacy | `projectMasterBudgetDemo.ts` | — | Sí (sin uso) |

### 9.2 Capa 1: Pipeline operativo

**Persistencia:** JSONB en Postgres (`projects.workflow_meta.budget_pipeline`)

**Campos del checklist:**
- `subcontracts_done`, `volumetry_done`, `cost_analysis_done`, `budget_marked_complete`
- `control_review_done`, `client_approved_version_label`
- `volumetry`, `cost_analysis`, `budget_versions`

**API:**
- `PATCH /api/projects/{uuid}/workflow-meta`
- `GET/POST /api/projects/{uuid}/subcontracts`

**Limitación:** Los flags son **manuales**. No se validan contra el resultado del processor ni contra geometría CAD. Según `docs/modules/flujo-doc-vs-dupla.md`: *"Takeoff no se calcula desde geometría; el pipeline es checklist operativo"*.

### 9.3 Capa 2: Presupuesto maestro IA

**Flujo end-to-end:**

```mermaid
sequenceDiagram
  participant FE as WorkspacePresupuestoMaestroTab
  participant BE as BudgetService
  participant PR as Processor :8001
  participant W as processor-worker
  participant AI as OpenAI / APS

  FE->>BE: POST /budget/jobs
  BE->>PR: POST /jobs/process (multipart DWG/PDF)
  PR->>W: RQ job dupla_processing
  W->>AI: Visión + takeoff + partidas
  W-->>PR: JSON presupuesto + Excel + BC3
  BE->>PR: GET /jobs/{id} (polling)
  BE->>BE: Guarda en project_budget_jobs
  FE->>BE: GET /budget/result
```

**Endpoints backend:**
- `POST /api/projects/{uuid}/budget/jobs` — encola job (202)
- `GET /api/projects/{uuid}/budget/jobs/latest` — estado + sync
- `GET /api/projects/{uuid}/budget/result` — JSON del presupuesto completado

**Endpoints processor:**
- `POST /jobs/process` — requiere al menos un `.dwg`
- `GET /jobs/{job_id}` — `queued|started|completed|failed`
- `GET /jobs/{job_id}/download` — ZIP (Excel, BC3, informes)

**Archivos clave del pipeline:**
- `processor/core/pipeline.py` — orquestación
- `processor/budget/composer.py` — composición de partidas
- `processor/budget/export_excel.py`, `export_bc3.py` — exports
- `processor/agents/vision_agent.py` — extracción con OpenAI

**Limitaciones conocidas:**
- Requiere `OPENAI_API_KEY` / `DUPLA_OPENAI_KEYS` para visión
- Modo `base_extraction` puede completar sin filas → UI muestra pantalla de re-procesar
- Parser BC3 incompleto para FIEBDC complejo
- Tests documentan bugs históricos de duplicados takeoff en CAD-only

### 9.4 Base de precios

| Componente | Archivo | Estado |
|------------|---------|--------|
| UI | `WorkspacePriceDatabaseTab.tsx` | Real |
| Servicio | `price_database_service.py` | Real |
| API | `GET/POST/DELETE .../price-database/files`, `POST .../apply` | Real |
| Clasificación IA | Background con OpenAI | Opcional |

---

## 10. Completitud global del proyecto

### 10.1 Estimación: 68 / 100

Escala: **0** = proyecto vacío, **100** = producto terminado según visión documentada en `Flujo_Software_IA_Construccion.docx`.

### 10.2 Desglose ponderado

| Área | % área | Peso | Contribución |
|------|--------|------|--------------|
| Núcleo colaborativo (auth, proyectos, archivos, chat, tareas) | 88% | 30% | 26.4 |
| Flujo de obra y ciclo de vida | 78% | 20% | 15.6 |
| Dominio IA (presupuesto, clasificación, asistente) | 65% | 25% | 16.25 |
| Coordinación / clashes | 62% | 15% | 9.3 |
| Producción (email, CI, seguridad, APS hardened) | 48% | 10% | 4.8 |
| **Total ponderado** | | | **72.35%** |

> Se redondea conservadoramente a **68%** considerando gaps respecto a la visión completa del documento de referencia (takeoff automático vinculado, clasificación por contenido, estados granulares, dos presupuestos + informe económico).

### 10.3 Qué falta para acercarse al 100%

| Gap vs visión doc | Estado actual | % faltante estimado |
|-------------------|---------------|---------------------|
| Takeoff automático desde geometría | Checklist manual | ~15% del dominio presupuesto |
| Clasificación IA por contenido DWG | Solo nombre + MIME | ~10% del dominio archivos |
| Detección interferencias CAD real en dev | Smoke mode default | ~8% del dominio clashes |
| Estados granulares del doc (§18) | `WorkflowPhase` lineal | ~5% del flujo |
| Dos presupuestos + informe económico | Parcial (pliego/export) | ~10% del dominio presupuesto |
| Email / reset password | SMTP vacío | ~5% auth |
| CI/CD y hardening producción | Sin pipelines | ~10% infra |

---

## 11. Recomendaciones prioritarias

| Prioridad | Acción | Impacto |
|-----------|--------|---------|
| **P0** | Configurar SMTP en staging/prod para reset password | Desbloquea flujo auth completo |
| **P0** | Rotar `JWT_SECRET` y documentar requisitos de producción | Seguridad |
| **P1** | Documentar claramente `COORDINATION_SMOKE_MODE` vs modo real | Evita confusión sobre clashes |
| **P1** | Vincular flags `budget_pipeline` con resultado del processor | Cierra gap takeoff vs checklist |
| **P1** | Añadir CI básico (pytest backend + processor, lint frontend) | Calidad continua |
| **P2** | Eliminar mocks huérfanos y `WorkspacePresupuestoTab.tsx` | Reduce deuda técnica |
| **P2** | Completar parser BC3 FIEBDC | Export BC3 robusto |
| **P2** | Actualizar `productTours.ts` (presupuesto ya no es demo) | UX coherente |
| **P3** | Implementar reanálisis real post-corrección de clashes | Workflow BIM completo |
| **P3** | Ampliar clasificación IA a contenido binario DWG (APS + visión) | Cierra gap doc vs producto |

---

## 12. Metodología y fuentes

### 12.1 Fuentes consultadas

| Fuente | Uso |
|--------|-----|
| Código fuente (`backend/`, `frontend/`, `processor/`, `coordination-service/`) | Implementación real vs mock |
| `docs/modules/flujo-doc-vs-dupla.md` | Matriz doc vs producto |
| `docs/INTEGRACION_FEAT_CLASHES.md` | Integración clashes |
| `docs/README.md` | Estado documentado (2026-04-18) |
| `backend/.env.example` | Configuración integraciones |
| `scripts/dev.sh` | Defaults de desarrollo |
| Tests (`backend/tests/`, `processor/tests/`) | Regresiones conocidas |

### 12.2 Limitaciones

- **Verificación runtime parcial:** solo Redis estaba activo al generar el informe; Postgres y servicios de aplicación estaban DOWN.
- **APIs externas (OpenAI, APS, SMTP):** evaluadas por configuración en `.env.example`, no por llamadas live.
- **Calidad del presupuesto IA:** no se evaluó con planos reales; depende de keys y calidad de modelos.
- **Porcentajes:** estimaciones basadas en matriz doc vs código; no métricas de cobertura automatizadas.

### 12.3 Cómo reproducir la verificación

```bash
# 1. Levantar infraestructura
brew services start postgresql@16   # o equivalente
brew services start redis

# 2. Setup y arranque
cd dupla-native
./scripts/dev.sh setup
./scripts/dev.sh bootstrap
./scripts/dev.sh start

# 3. Verificar servicios
./scripts/dev.sh status
curl http://localhost:8001/health
curl http://localhost:8002/health

# 4. Tests
cd backend && .venv/bin/pytest tests/ -q
cd processor && .venv/bin/pytest tests/ -q
```

---

## Apéndice A — Índice de archivos clave

### Presupuesto
- `backend/app/routes/budget.py`
- `backend/app/services/budget_service.py`
- `backend/app/models/project_budget_job.py`
- `frontend/src/api/budget.ts`
- `frontend/src/hooks/useBudgetJob.ts`
- `frontend/src/components/project-workspace/tabs/WorkspacePresupuestoMaestroTab.tsx`
- `frontend/src/components/project-workspace/tabs/WorkspaceFlujoTab.tsx`
- `processor/main.py`, `processor/tasks.py`, `processor/core/pipeline.py`

### Clashes
- `backend/app/routes/clash.py`, `clash_workflow.py`
- `backend/app/services/clash_service.py`, `clash_workflow_service.py`
- `coordination-service/wrapper/run_clash_analysis.py`
- `coordination-service/fixtures/smoke_primary_incidents.json`
- `frontend/src/hooks/useStructuralAnalysisJob.ts`
- `frontend/src/components/project-workspace/tabs/WorkspaceHallazgosTab.tsx`

### Configuración
- `backend/.env.example`
- `processor/.env.example`
- `scripts/dev.sh`

---

*Informe generado el 15 de junio de 2026. Para actualizaciones, re-ejecutar verificación runtime y revisar commits posteriores a la última revisión documental (2026-04-18).*
