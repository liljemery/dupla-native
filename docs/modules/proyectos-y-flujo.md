# Módulo: Proyectos, workspace y ciclo de vida

## Para qué sirve

Centralizar la **obra** como entidad `Project`: metadatos (nombre, cliente), **tipo de obra** (`RESIDENTIAL` | `TENDER`), **fase del flujo** (`WorkflowPhase`), datos de **bootstrap**, **especificaciones**, **presupuesto** (metadatos en `workflow_meta`), **revisiones de arquitectura**, **subcontratos/cotizaciones**, **eventos** auditables, **miembros** con acceso, y el **documento de arquitectura** (pliegos en JSON: grupos/partidas y materiales).

Además incluye **control de entrega de planos** (filas SDP), **exportaciones** Excel/PDF del pliego y control de planos, y la **apertura del chat del proyecto** (delegando en el módulo Chat).

Para alinear expectativas con el documento de negocio «Flujo Software IA Construcción», ver la **matriz estado por estado** en [flujo-doc-vs-dupla.md](./flujo-doc-vs-dupla.md).

## Superficie API (resumen)

### Router `projects` — `/api/projects`

| Área | Endpoints destacados |
|------|----------------------|
| Lista y alta | `GET /api/projects` · `POST /api/projects` (**solo Gerencia**; multipart: nombre, cliente, `project_kind`, miembros opcionales, archivos opcionales) |
| Proyecto y miembros | `GET /api/projects/{uuid}` · `GET/PUT .../members` (PUT solo **Gerencia**) |
| Datos de arquitectura (JSON) | `GET/PUT .../architecture` — documento pliegos + materiales |
| Entrega de planos | `GET/POST/PATCH/DELETE .../plan-delivery-requests/...` |
| Exportaciones | `GET .../exports/pliego.xlsx` · `.../pliego.pdf` · `.../control-planos.xlsx` · `.../control-planos.pdf` · `.../exports/documentary-report.pdf` (informe checklist/archivos) |
| Hallazgos técnicos | `GET/POST .../technical-findings` |
| Dashboard gerencia | `GET /api/dashboard/summary` (solo Gerencia) |

### Router `project_lifecycle` — mismo prefijo `/api/projects`

| Área | Endpoints destacados |
|------|----------------------|
| Metadatos y fase | `PATCH /{uuid}` · `POST /{uuid}/transitions` · `PUT .../bootstrap` · `PUT .../specifications` · `PATCH .../workflow-meta` |
| Eventos | `GET .../events` (paginado, filtros `event_type`, `q`) |
| Revisiones | `POST/GET .../architecture-revisions` |
| Subcontratos | `GET/POST .../subcontracts` · `POST .../subcontracts/{quote}/lines` · `DELETE .../subcontracts/{quote}` |
| Chat del proyecto | `POST .../chat/conversation` — obtiene o crea conversación vinculada y devuelve su UUID |

Los archivos en disco y carpetas tienen documentación detallada en [archivos-y-carpetas.md](./archivos-y-carpetas.md).

## Flujos principales

### 1. Listar y abrir proyectos

1. Usuario autenticado llama `GET /api/projects` (Gerencia ve todos; el resto ve creados o compartidos).
2. Elige un proyecto y navega a `/app/projects/:projectUuid`.

### 2. Crear proyecto (solo Gerencia)

1. Desde **Proyectos**, modal multi-paso (`CreateProjectModal`): nombre, cliente, tipo RESIDENTIAL/TENDER, miembros opcionales, archivos opcionales.
2. `POST /api/projects` (multipart): crea proyecto; los archivos se suben en cadena al servicio de ciclo de vida.
3. Reglas de negocio: p. ej. licitación (**TENDER**) puede exigir fase y archivos mínimos según validación del backend.

### 3. Vista “tablero del proyecto” vs workspace completo

1. Al entrar en el workspace (`ProjectWorkspacePage`), primero se muestra `ProjectWorkspaceEmbeddedView`: **tablero de tareas filtrado al proyecto** + panel de **fase** + accesos rápidos.
2. **Abrir workspace** despliega pestañas (`WorkspaceTabsLayout`) con todas las áreas (detalles, flujo, archivos, etc.).

### 4. Avanzar fase del workflow

1. Usuario dispara `POST /api/projects/{uuid}/transitions` con `target_phase`.
2. El servicio valida transiciones lineales (`LINEAR_NEXT` / reglas internas) y persiste.
3. La UI muestra etiqueta de fase y botón “siguiente fase” cuando aplica (`WorkspaceFlujoTab`, `ProjectWorkspaceEmbeddedView`).

### 5. Bootstrap y especificaciones

1. **Bootstrap:** `PUT .../bootstrap` reemplaza criterios checklist; editado en pestaña **Flujo**.
2. **Especificaciones:** `PUT .../specifications` guarda documento (resumen GA-FO, etc.); pestaña **Especificaciones** con formulario y estados de ítems.

### 6. Revisiones de arquitectura

1. `POST .../architecture-revisions` con decisión APPROVED | REJECTED | PARTIAL y notas.
2. Listado con `GET .../architecture-revisions` — pestaña **Revisiones**.

### 7. Presupuesto (pipeline) y cotizaciones de subcontrato

1. `PATCH .../workflow-meta` actualiza `budget_pipeline` dentro de `workflow_meta` — pestaña **Presupuesto**.
2. Subcontratos: crear cotización, añadir líneas, eliminar cotización vía rutas `/subcontracts`.

### 8. Entrega de planos (SDP)

1. CRUD vía `.../plan-delivery-requests` — pestaña **Entrega planos**.

### 9. Datos “Excel” de pliegos y materiales

1. `GET .../architecture` carga documento; el usuario edita en pestañas **Pliegos** y **Materiales** (store local + guardado con `PUT .../architecture` a través de `workspaceStore` / flujos de guardado del workspace).

### 10. Eventos e historial

1. `GET .../events` con paginación — pestaña **Eventos** (`WorkspaceEventosTab`).

### 11. Miembros del proyecto

1. `GET .../members` lista equipo; `PUT .../members` solo **Gerencia** — modal `ProjectConfigModal`.

### 12. Exportaciones

1. Descargas desde `ProjectWorkspaceHeader` (Excel/PDF pliego y control planos) llamando a las rutas `.../exports/...`.

### 13. Chat del proyecto

1. `POST .../chat/conversation` devuelve UUID de conversación.
2. La UI redirige a `/app/chat?conversation=...` para seguir en el módulo Chat.

### 14. Notificaciones

Generadas en eventos del ciclo de vida; consumo vía `GET /api/me/notifications` (ver [auth-y-usuarios.md](./auth-y-usuarios.md)).

## Pantallas y pestañas (mapeo UI → API)

| Pantalla / bloque | Ruta o ubicación | Qué toca |
|-------------------|------------------|----------|
| `ProjectsPage` | `/app/projects` | `GET /api/projects`; **Gerencia:** `POST /api/projects`, carga `GET /api/admin/users` para elegir miembros al crear. |
| `ProjectsBoardView` / `ProjectsListView` | Dentro de `ProjectsPage` | Navegación a `/app/projects/:uuid`; búsqueda local en lista. |
| `CreateProjectModal` | Modal en `ProjectsPage` | Construye multipart del `POST /api/projects`. |
| `ProjectWorkspacePage` | `/app/projects/:projectUuid` | Orquesta proyecto, fase, bootstrap, specs, revisiones, presupuesto, plan delivery, chat link, `ProjectConfigModal`. |
| `ProjectWorkspaceHeader` | Cabecera del workspace | Exportaciones `GET .../exports/*`. |
| `ProjectWorkspaceEmbeddedView` | Vista inicial del workspace | Tablero embebido (`TaskboardView` + proyecto); avanzar fase; abrir chat; entrar al workspace de pestañas. |
| `WorkspaceDetallesTab` | Pestaña Detalles | Muestra datos del proyecto; enlaces a chat. |
| `WorkspaceFlujoTab` | Pestaña Flujo | Bootstrap `PUT .../bootstrap`, transiciones `POST .../transitions`. |
| `WorkspaceArchivosTab` | Pestaña Archivos | Ver [archivos-y-carpetas.md](./archivos-y-carpetas.md). |
| `WorkspaceEntregaPlanosTab` | Entrega planos | CRUD plan-delivery-requests. |
| `WorkspaceRevisionesTab` | Revisiones | POST/GET architecture-revisions. |
| `WorkspaceEspecificacionesTab` | Especificaciones | `PUT .../specifications`. |
| `WorkspacePresupuestoTab` | Presupuesto | `PATCH .../workflow-meta`, rutas subcontratos. |
| `WorkspaceEventosTab` | Eventos | `GET .../events` paginado. |
| `WorkspacePliegosTab` / `WorkspaceMaterialesTab` | Pliegos / Materiales | `GET/PUT .../architecture` vía store de workspace. |
| `ProjectConfigModal` | Modal configuración | `PATCH` metadatos proyecto, `PUT .../members` (Gerencia), refresco de miembros `GET .../members`. |

**Stores:** `workspaceStore` (documento de arquitectura en cliente), estado local en `ProjectWorkspacePage` para fase, revisiones, cotizaciones, etc.

## Dependencias con otros módulos

- **Tablero:** el workspace embebido usa el mismo componente de tablero filtrado por `project_uuid` ([tablero-tareas.md](./tablero-tareas.md)).
- **Chat:** conversación de proyecto creada vía API de ciclo de vida; mensajes en `/api/chat/...`.
