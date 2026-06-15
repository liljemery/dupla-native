# Matriz: documento «Flujo Software IA Construcción» vs Dupla

Referencia: [`docs/provided_info/Flujo_Software_IA_Construccion.docx`](../provided_info/Flujo_Software_IA_Construccion.docx) (visión objetivo). Esta tabla enlaza **estados y fases del documento** con **implementación actual** (API, modelos, UI).

## Leyenda

| Símbolo | Significado |
|---------|-------------|
| Cubierto | Comportamiento equivalente en producción |
| Parcial | Parte del alcance; ver notas |
| Planeado / doc | Cubierto vía documentación o flags sin automatizar todo el doc |

---

## Sección 3 — Login y dashboard

| Doc (tabla doc) | Dupla | Estado |
|-----------------|-------|--------|
| Login por rol | `POST /api/auth/token`, JWT, `/api/me` | Cubierto |
| Dashboard personalizado (tareas, alertas, KPIs) | Lista de proyectos, notificaciones sidebar, tablero | Parcial — KPI agregados vía `GET /api/dashboard/summary` (Gerencia) |

---

## Fases 1–2 — Proyecto y documentación

| Doc | Dupla | Estado |
|-----|-------|--------|
| Tipo licitación / residencial | `project_kind` RESIDENTIAL / TENDER | Cubierto |
| Campos: código, ubicación, área, niveles, plazo, responsable | Columnas `project_code`, `location_text`, `estimated_area_sqm`, `floor_levels_count`, `deadline`, `responsible_user_id` en `projects`; edición `PATCH /api/projects/{uuid}` | Cubierto |
| Carga planos PDF/DWG/DXF | `ProjectFile`, carpetas, validación extensión | Cubierto |

---

## Fase 3 — Clasificación y checklist

| Doc | Dupla | Estado |
|-----|-------|--------|
| IA clasifica por contenido | `ProjectFileAIService`: nombre + MIME solamente | Parcial |
| Checklist configurable | `project_bootstrap_criteria`, `PUT .../bootstrap` | Cubierto |
| Informe documental automático | `GET .../exports/documentary-report.pdf` | Cubierto (heurística archivos + checklist; sin OCR/CAD) |

---

## Fases 4–5 — Análisis técnico e informes

| Doc | Dupla | Estado |
|-----|-------|--------|
| Detección interferencias / CAD | No hay pipeline CV/BIM | Planeado vía modelo `project_technical_findings` (hallazgos futuros OCR/reglas) |
| Dos informes (técnico + documental) | Informe documental PDF; hallazgos vía API `/technical-findings` | Parcial |

---

## Fases 6–7 — Arquitectura y presupuesto

| Doc | Dupla | Estado |
|-----|-------|--------|
| Tarea automática Arquitectura | Tarjeta Kanban al pasar a `ARCHITECTURE_REVIEW` | Cubierto (automatización) |
| Sin presupuesto sin aprobación arquitectura | Guard `SPECIFICATIONS`: revisión `APPROVED` | Cubierto |

---

## Fases 8–11 — Presupuesto y controles

| Doc | Dupla | Estado |
|-----|-------|--------|
| Takeoff automático | Flags `budget_pipeline` (manual) | Parcial |
| Control antes que Gerencia | `budget_pipeline.control_review_done` obligatorio antes de `BUDGET_APPROVED`; checkbox en pestaña Presupuesto | Cubierto (regla explícita sin nueva fase `WorkflowPhase`) |
| Dos presupuestos + informe económico | Pliego/export Excel existentes | Parcial |

---

## Sección 17–18 — PM integrado y estados

| Doc | Dupla | Estado |
|-----|-------|--------|
| Tareas, comentarios, trazabilidad | Tablero, chat, `project_events` | Cubierto |
| Estados granulares del doc | `WorkflowPhase` lineal más simple | Parcial — ver tabla abajo |

### Equivalencia aproximada `WorkflowPhase` ↔ doc

| Estados doc (§18) | Fase Dupla |
|-------------------|------------|
| Creado | `BOOTSTRAPPING` / creación |
| Documentación cargada | `AWAITING_FILES` |
| En clasificación / análisis IA | Parcial — no hay sub-estados; checklist + archivos |
| Informes generados | Parcial — informe documental exportable |
| En revisión arquitectura | `ARCHITECTURE_REVIEW` |
| Aprobado arquitectura → presupuesto | Tras revisión → `SPECIFICATIONS` → `BUDGETING_PIPELINE` |
| En revisión control / gerencia | `MANAGEMENT_APPROVAL` + flags pipeline + `control_review_done` |
| Aprobado cliente | `BUDGET_APPROVED` → `COMPLETE` |

---

## Rutas y modelos clave (índice rápido)

| Área | Archivos / rutas |
|------|------------------|
| Proyecto y metadatos extendidos | [`Project`](../../backend/app/models/project.py), `PATCH /api/projects/{uuid}` |
| Transiciones | `POST /api/projects/{uuid}/transitions`, [`LINEAR_NEXT`](../../backend/app/domain/workflow_phase.py) |
| Pipeline presupuesto | `workflow_meta.budget_pipeline`, `PATCH .../workflow-meta` |
| Informe documental | `GET /api/projects/{uuid}/exports/documentary-report.pdf` |
| Hallazgos técnicos | Tabla `project_technical_findings`, `GET/POST .../technical-findings` |
| Dashboard KPI | `GET /api/dashboard/summary` |
| Tablero | `/api/tasks/board`, creación automática desde ciclo de vida |

---

## Desviaciones explícitas respecto al doc

1. **Una fase `MANAGEMENT_APPROVAL`** para aprobaciones económicas finales; **Control** no tiene `WorkflowPhase` propia — la revisión de Control se exige con **`control_review_done`** antes de cerrar a `BUDGET_APPROVED`.
2. **IA de clasificación** no lee binarios DWG ni ejecuta visión por computador en planos.
3. **Takeoff** no se calcula desde geometría; el pipeline es checklist operativo.
