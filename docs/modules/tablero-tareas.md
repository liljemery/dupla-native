# Módulo: Tablero de tareas (Kanban)

## Para qué sirve

Coordinar trabajo con **tarjetas** en columnas (listas), con **asignación** a usuarios del equipo, **movimiento** entre estados, **archivo** de tarjetas y **borrado permanente**. Soporta **comentarios** por tarjeta. El tablero puede verse **global** o **filtrado por proyecto**; también hay filtros por asignatario (“mías”, otro usuario, incluir archivadas).

## Superficie API — `/api/tasks`

| Método | Ruta | Dependencia | Función |
|--------|------|-------------|---------|
| GET | `/assignees` | Autenticado | Usuarios asignables (módulo Arquitectura; con `project_uuid` limita al equipo del proyecto) |
| GET | `/board` | Autenticado | Tablero: query `mine`, `assignee_uuid`, `project_uuid`, `include_archived` |
| POST | `/cards` | `require_task_creator` | Crear tarjeta (Gerencia, Control, Presupuesto, Arquitectura) |
| GET | `/cards/{uuid}/comments` | `require_task_operator` | Listar comentarios |
| POST | `/cards/{uuid}/comments` | `require_task_operator` | Añadir comentario |
| PATCH | `/cards/{uuid}` | `require_task_operator` | Mover, editar, archivar, asignar |
| DELETE | `/cards/{uuid}` | `require_task_operator` | Eliminar tarjeta permanentemente |

## Flujos

### 1. Ver tablero global

1. Usuario abre `/app/tasks`.
2. `TaskboardPage` renderiza `TaskboardView` sin filtro de proyecto.
3. `GET /api/tasks/board` devuelve columnas y tarjetas activas.

### 2. Tablero filtrado por proyecto

1. Navegación a `/app/tasks?project_uuid=<uuid>` (enlace desde contexto de proyecto si existe).
2. Misma vista con `projectUuid` en query: el cliente pasa el filtro al endpoint.

### 3. Tablero embebido en el workspace

1. En `/app/projects/:uuid`, la vista compacta (`ProjectWorkspaceEmbeddedView`) monta `TaskboardView` con `variant="embedded"` y `projectUuid` fijo.
2. Permite gestionar tareas del proyecto sin salir de la página (columnas limitadas visualmente).

### 4. Crear y editar tarjeta

1. Modal de creación (`TaskboardCreateModal`) → `POST /cards` con título, columna, asignado opcional, proyecto opcional.
2. Clic en tarjeta abre `TaskboardCardModal`: edición, comentarios (`GET/POST .../comments`), archivo o borrado vía `PATCH` / `DELETE`.

### 5. Filtrar por asignación

1. Toolbar (`TaskboardToolbar`) ajusta query params o cuerpo de petición para `mine=1` o `assignee_uuid`.

## Pantallas y componentes

| Pantalla / componente | Ruta o contexto | Influencia |
|----------------------|-----------------|------------|
| `TaskboardPage` | `/app/tasks` | Lee `project_uuid` de query; envuelve `TaskboardView` en variante full. |
| `TaskboardView` | Página de tareas o embebido | Carga tablero, columnas, DnD, modales. |
| `TaskboardToolbar` | Dentro de `TaskboardView` | Filtros y acciones de vista. |
| `TaskboardCreateModal` | `TaskboardView` | Alta de tarjetas. |
| `TaskboardCardModal` | `TaskboardView` | Detalle, comentarios, archivo, eliminar. |
| `ProjectWorkspaceEmbeddedView` | `/app/projects/:uuid` | Tablero embebido por proyecto. |

**Tipos / utilidades:** `types/taskBoard.ts`, `lib/taskboard.ts`.

## Relación con otros módulos

- **Proyectos:** las tarjetas pueden referenciar un `project_uuid`; el workspace muestra el tablero contextual.
- **Usuarios / módulos:** los asignables salen de usuarios con módulo Arquitectura o del subconjunto miembros del proyecto.
