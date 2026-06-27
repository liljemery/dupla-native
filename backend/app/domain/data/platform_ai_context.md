# Dupla — Contexto operativo para Dupla Assistant (IA)

Respondé en el idioma del usuario. Basá las respuestas en este documento; si algo no figura aquí o puede haber cambiado en código, indicá la incertidumbre y recomendá confirmar en la aplicación.

## Notas de implementación actuales (no siempre están en los módulos markdown)

- La **fase de workflow** (`workflow_phase`) visible en tablero/API se **deriva del índice del paso actual** en la plantilla de flujo ordenada (secuencia estándar de ~7 fases: archivos, revisión arquitectura, especificaciones/pliego, pipeline presupuesto, gerencia, aprobado cliente, completo). Los pasos pueden tener `behavior_kind` genérico; **no confíes en behavior_kind para inferir fase**.
- **Arranque:** los proyectos nuevos inician en **Esperando archivos** (`AWAITING_FILES`); no hay checklist de arranque.
- **Archivos:** extensiones típicas `.dwg`, `.dxf`, `.pdf` según validación del proyecto.
- **Chat humano:** persiste en Postgres; Redis usa epoch para sincronización. Este asistente IA **no** es ese chat.
- **Roles:** GERENCIA, CONTROL, PRESUPUESTO, ARQUITECTURA. Gerencia crea proyectos y rutas admin.

---

## Documentación de producto (referencia)


### docs/modules/modulos-producto.md

# Módulo: Catálogo de módulos de producto

## Para qué sirve

Registrar los **módulos funcionales** de la aplicación (por ejemplo “Arquitectura”) para:

- Asociar **usuarios ↔ módulos** (`user_modules`) y así **autorizar** el acceso a proyectos y APIs del dominio.
- Ofrecer un listado estable (`GET /api/modules`), con posible **caché Redis** en el servicio.

En la práctica, el acceso al workspace de arquitectura exige que el usuario tenga el módulo correspondiente; el seed y la administración asignan el módulo con id **1** (Arquitectura).

## Superficie API

| Método y ruta | Rol | Función |
|---------------|-----|---------|
| `GET /api/modules` | Usuario autenticado | Lista todos los módulos (id, nombre). |

Implementación: `ModuleService` + `routes/modules.py`.

## Flujos

### Asignación al crear/editar usuario (Gerencia)

1. En **Administración**, al crear o editar un usuario, se envían `module_ids` (p. ej. `[1]` para Arquitectura).
2. El backend persiste filas en `user_modules`.
3. Al abrir un proyecto, el servicio comprueba que el usuario tenga el módulo necesario.

### Listado de módulos

1. Cualquier cliente autenticado puede llamar `GET /api/modules` para mostrar opciones (p. ej. futuros selectores).
2. En el frontend actual, el modal de admin usa un checkbox **Arquitectura** mapeado al id `1` sin llamar obligatoriamente a este endpoint.

## Pantallas y componentes

| Pantalla / componente | Influencia |
|----------------------|------------|
| `AdminUserModal` | Envía `module_ids` al crear/editar usuario vía `/api/admin/users`. |
| `AdminUsersPage` | Lista usuarios con `module_ids` devueltos por la API. |
| Resto de la app | El acceso a `GET /api/projects/...` y workspace depende indirectamente de la asignación de módulos hecha aquí o en seed. |

---

### docs/modules/auth-y-usuarios.md

# Módulo: Autenticación, sesión y perfil

## Para qué sirve

- **Identificar** al usuario (email + contraseña) y emitir un **JWT** para todas las llamadas autenticadas.
- **Exponer el perfil** del usuario autenticado (UUID, email, nombre, apellido, rol) para hidratar la sesión en el cliente.
- **Notificaciones in-app** ligadas al ciclo de vida del proyecto (persistencia y lectura); el contador de no leídas se muestra en la barra lateral.

No gestiona el alta de usuarios (eso es **Administración**). El catálogo de módulos de producto (p. ej. “Arquitectura”) está en [modulos-producto.md](./modulos-producto.md).

## Superficie API (backend)

| Método y ruta | Rol | Función |
|---------------|-----|---------|
| `POST /api/auth/token` | Público (credenciales) | OAuth2 password: devuelve `access_token` |
| `GET /api/me` | Cualquier usuario autenticado | Perfil actual |
| `GET /api/me/notifications` | Autenticado | Lista notificaciones (`unread_only` opcional) |
| `PATCH /api/me/notifications/{uuid}/read` | Autenticado | Marcar notificación como leída |

La lógica de negocio de notificaciones está en `ProjectLifecycleService` (se crean ante eventos del proyecto; el listado vive bajo `/api/me` por comodidad de cliente).

## Flujos

### 1. Login

1. Usuario envía email y contraseña al endpoint de token.
2. Backend valida credenciales y devuelve JWT.
3. El frontend guarda el token (Zustand) y redirige a `/app/projects`.

### 2. Hidratación de sesión (`/api/me`)

1. Tras tener token, `MainLayout` llama a `GET /api/me` si aún no hay `userUuid` en el store.
2. Se completan email, rol, UUID, nombre y apellido para UI y permisos.

### 3. Notificaciones

1. `Sidebar` consulta `GET /api/me/notifications?unread_only=true` para mostrar badge de avisos.
2. El usuario puede marcar como leídas vía `PATCH` (desde pantallas que lo integren o futuros centros de notificaciones).

## Pantallas y componentes que influyen en este módulo

| Pantalla / componente | Ruta o uso | Influencia |
|----------------------|------------|------------|
| `LoginPage` | `/login` | Envía credenciales; obtiene JWT vía `authStore.login` → `POST /api/auth/token`. |
| `MainLayout` | Layout de `/app/*` | Tras login, llama `GET /api/me` para completar perfil. Monta `useChatSync` (chat, no auth). |
| `Sidebar` | Dentro de `MainLayout` | Polling de notificaciones no leídas; muestra email, rol y botón **Salir** (`logout` borra sesión). |
| `App` (`RequireAuth`) | Rutas bajo `/app` | Sin token → redirección a `/login`. |
| `App` (`RequireGerencia`) | Solo `/app/admin` | Comprueba rol en store (derivado de `/api/me`); no es parte del módulo auth pero usa el mismo perfil. |

**Stores:** `authStore` (token, datos de usuario, `login` / `logout`).

---

### docs/modules/proyectos-y-flujo.md

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

---

### docs/modules/archivos-y-carpetas.md

# Módulo: Archivos de proyecto, carpetas y búsqueda

## Para qué sirve

Gestionar **archivos técnicos** vinculados a un proyecto: almacenamiento en disco, **carpetas** anidadas, **metadatos** (descripción, disciplina, categoría), **listado paginado**, **búsqueda** global en el proyecto, **descarga** y **eliminación**. Solo se aceptan extensiones **.dwg**, **.dxf** y **.pdf** (validación compartida con el frontend).

Opcionalmente, en subida con asistente (`wizard`), se puede invocar **IA (OpenAI)** para sugerir disciplina y descripción (`ProjectFileAiService`).

## Superficie API — `/api/projects/{project_uuid}/...`

| Método | Ruta | Función |
|--------|------|---------|
| GET | `/file-folders` | Listar carpetas (`parent_uuid` opcional para raíz) |
| POST | `/file-folders` | Crear carpeta |
| PATCH | `/file-folders/{folder_uuid}` | Renombrar / mover |
| DELETE | `/file-folders/{folder_uuid}` | Eliminar carpeta vacía |
| POST | `/files` | Subir archivo (multipart: `file`, `category`, `folder_uuid`, `wizard`) |
| GET | `/files` | Listar archivos paginado (`folder_uuid`, `limit`, `offset`) |
| GET | `/files/search` | Buscar por texto `q` y/o `discipline` |
| PATCH | `/files/{file_uuid}` | Actualizar metadatos |
| DELETE | `/files/{file_uuid}` | Borrar archivo |
| GET | `/files/{file_uuid}/download` | Descarga binaria |

## Flujos

### 1. Navegación por carpetas

1. Cliente lista carpetas raíz y entra en subcarpetas con `parent_uuid` / `folder_uuid` según listados.
2. `GET .../files` filtra por carpeta actual para paginar sin cargar todo el árbol.

### 2. Subida simple o con asistente

1. Usuario selecciona archivo(s) válidos en UI.
2. `POST .../files` con `folder_uuid` opcional; `wizard=true` activa pipeline con IA si está configurado.
3. Tras crear el registro, el listado se refresca; el **epoch** de chat puede actualizarse en otros flujos del servicio si aplica.

### 3. Búsqueda transversal

1. `GET .../files/search?q=...&discipline=...` devuelve coincidencias con **ruta desde raíz** para localizar archivos en cualquier carpeta.

### 4. Edición y descarga

1. `PATCH` para corregir descripción o disciplina.
2. `GET .../download` sirve el fichero con nombre original.

### 5. Limpieza

1. `DELETE` archivo o carpeta vacía; errores claros si la carpeta no está vacía.

## Pantallas y componentes

| Componente | Ubicación | Influencia |
|------------|-----------|------------|
| `WorkspaceArchivosTab` | Pestaña **Archivos** del workspace (`/app/projects/:uuid`) | Lista paginada, carpetas, búsqueda, subida, mensajes de tipos permitidos. |
| `ProjectFilesUploadWizard` | Invocado desde el flujo de archivos | Subida guiada; puede usar flag `wizard` en API. |
| `ProjectWorkspacePage` | Misma ruta | Monta la pestaña archivos cuando el usuario abre el workspace completo. |

**Constantes frontend:** `constants/projectAllowedFiles.ts`, `constants/projectFileDisciplines.ts` (alineadas con backend).

## Relación con otros módulos

- **Proyectos:** todo cuelga del `project_uuid`; permisos de proyecto/módulo Arquitectura aplican igual que en el resto del workspace.
- **Chat:** el servicio puede bump de epoch en Redis al subir o al enlazar actividad; la sincronización de mensajes es independiente pero la UI de archivos convive en el mismo contexto de proyecto.

---

### docs/modules/tablero-tareas.md

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

---

### docs/modules/chat.md

# Módulo: Chat interno

## Para qué sirve

Comunicación **entre usuarios** de la organización: canal **general** (avisos), **chats directos**, **grupos** y **conversación por proyecto** (creada desde el workspace). Los mensajes se persisten en base de datos; al enviar, se incrementa un **epoch** en **Redis** por conversación para que los clientes detecten actividad nueva y refresquen (`chat_message_epoch_bump`).

Las respuestas de listado de conversaciones pueden incluir **participantes** (p. ej. emails en grupos) para poblar la barra lateral.

## Superficie API — `/api/chat`

| Método | Ruta | Función |
|--------|------|---------|
| GET | `/conversations` | Listar conversaciones del usuario (general + directos + grupos) |
| POST | `/conversations/direct` | Abrir u obtener DM con `user_uuid` |
| POST | `/conversations/group` | Crear grupo (título + `member_uuids`) |
| GET | `/directory` | Directorio de usuarios para iniciar chat o armar grupo |
| GET | `/conversations/{uuid}/messages` | Mensajes (`after_uuid`, `limit`) |
| POST | `/conversations/{uuid}/messages` | Enviar mensaje; bump epoch |
| GET | `/messages` | Compatibilidad: mensajes del canal general |
| POST | `/messages` | Compatibilidad: enviar al general; bump epoch del general |

**Proyecto:** la conversación ligada al proyecto no está bajo `/api/chat` en la creación: se usa `POST /api/projects/{uuid}/chat/conversation` (ver [proyectos-y-flujo.md](./proyectos-y-flujo.md)); una vez existe el UUID, el cliente usa las mismas rutas de mensajes.

## Flujos

### 1. Entrar al chat y elegir conversación

1. `ChatPage` carga `GET /conversations`.
2. Usuario selecciona una fila en `ChatConversationSidebar` (muestra participantes en grupos).
3. Se cargan mensajes con `GET .../conversations/{id}/messages`.

### 2. Enviar mensaje

1. `ChatComposer` envía `POST .../messages` con el cuerpo del mensaje.
2. Backend persiste y ejecuta **epoch bump** en Redis para esa conversación.
3. `useChatSync` / store (`chatStore`) detecta cambios y actualiza hilos o badge de no leídos.

### 3. Nuevo chat directo o grupo

1. Desde modales (`ChatDirectModal`, `ChatGroupModal`): `POST .../direct` o `.../group` con datos del formulario.
2. Tras crear/abrir, la conversación aparece en la lista y se puede seleccionar.

### 4. Chat del proyecto

1. En el workspace, **Abrir chat** llama `POST /api/projects/{uuid}/chat/conversation`.
2. Redirección a `/app/chat?conversation=<uuid>` para continuar en la pantalla de chat centralizada.

### 5. Sincronización

1. `MainLayout` ejecuta `useChatSync` en todas las rutas autenticadas para mantener al día conversaciones/mensajes sin recargar la página a mano.

## Pantallas y componentes

| Pantalla / componente | Ruta | Influencia |
|----------------------|------|------------|
| `ChatPage` | `/app/chat` | Lista conversaciones, carga mensajes, envía mensajes, modales directo/grupo; lee `?conversation=` de la URL. |
| `ChatConversationSidebar` | `ChatPage` | Lista conversaciones + participantes. |
| `ChatComposer` / `ChatMessageList` | `ChatPage` | Envío y visualización de mensajes. |
| `ChatDirectModal` / `ChatGroupModal` | `ChatPage` | Altas de conversaciones. |
| `MainLayout` | Layout | `useChatSync` global. |
| `Sidebar` | Layout | Indicador de mensajes no leídos (`chatStore.hasUnread`). |
| `ProjectWorkspacePage` / `WorkspaceDetallesTab` / `ProjectWorkspaceEmbeddedView` | `/app/projects/:uuid` | Botón abrir chat del proyecto → API proyecto + redirect a Chat. |

**Stores:** `chatStore`; **hook:** `useChatSync`.

---

### docs/TECHNICAL.md (extracto)

# Documentación técnica — Grupo Dupla

## 1. Arquitectura del monorepo

```
dupla/
├── backend/          # FastAPI, SQLAlchemy, Alembic
│   └── app/
│       ├── routes/       # Routers HTTP (prefijos /api/...)
│       ├── services/     # Lógica de negocio
│       ├── repositories/ # Acceso a datos (cuando aplica)
│       ├── models/       # ORM SQLAlchemy
│       ├── schemas/      # Pydantic (entrada/salida API)
│       ├── domain/       # Enums, constantes, reglas puras (p. ej. workflow, uploads)
│       ├── security/     # JWT, contraseñas
│       └── cache/        # Redis (p. ej. epoch de mensajes de chat)
├── frontend/       # Vite + React + TypeScript
│   └── src/
│       ├── api/          # Cliente HTTP
│       ├── components/   # UI reutilizable y workspace
│       ├── pages/        # Rutas de página
│       ├── store/        # Zustand
│       ├── constants/    # Roles, fases, tipos de archivo, etc.
│       └── types/        # Tipos TS compartidos
└── docs/             # Documentación de producto y técnica
```

### Principios

- **API REST** bajo prefijos coherentes; documentación interactiva en `/docs` (Swagger).
- **UUID** como identificador expuesto en API para entidades de dominio; `id` numérico interno solo donde el modelo lo requiera y no se expone al cliente.
- **Separación** routes → services → repositories/models; validación con Pydantic en el borde HTTP.

## 2. Backend

### 2.1 Routers registrados (`app/main.py`)

| Router | Prefijo base | Área |
|--------|--------------|------|
| `auth` | `/api/auth` | Login, tokens |
| `users` | `/api` | Perfil / usuarios (según rutas definidas) |
| `modules` | `/api` | Módulos de producto |
| `projects` | `/api/projects` | CRUD y vistas de proyecto |
| `project_lifecycle` | `/api/projects` | Archivos, carpetas, eventos, fases, exportaciones |
| `admin` | `/api/admin` | Administración (p. ej. usuarios; restricción por rol Gerencia) |
| `chat` | `/api/chat` | Conversaciones y mensajes |
| `tasks` | `/api/tasks` | Tablero / tarjetas / comentarios |

Los routers `projects` y `project_lifecycle` comparten el prefijo `/api/projects`; las rutas se diferencian por path y método.

### 2.2 Datos y migraciones

- **Alembic** versiona el esquema; antes de seed o tests: `alembic upgrade head`.
- **PostgreSQL** es la fuente de verdad relacional.
- Modelos destacados (evolutivo): `User` (email, `first_name`, `last_name`, `UserRole`), `Project` (`project_kind`, workflow), `ProjectFile`, `ProjectFileFolder`, entidades de chat, tablero, comentarios de tarjeta, eventos de proyecto.

### 2.3 Roles (`UserRole`)

Valores actuales en código: `GERENCIA`, `CONTROL`, `PRESUPUESTO`, `ARQUITECTURA`. La semilla demo define usuarios de ejemplo con nombres y apellidos (ver `app/seed.py`).

### 2.4 Flujo de trabajo (`WorkflowPhase`)

Definido en `app/domain/workflow_phase.py`. Transiciones lineales principales en `LINEAR_NEXT` / `LINEAR_PREV`. La fase final incluye `COMPLETE`.

### 2.5 Tipo de proyecto (`ProjectKind`)

`RESIDENTIAL` | `TENDER` (`app/domain/project_kind.py`), persistido en proyecto.

### 2.6 Archivos de proyecto

- **Extensiones permitidas:** `.dwg`, `.dxf`, `.pdf` — validación compartida (`app/domain/project_uploads.py`) y mensajes alineados con el frontend.
- **Carpetas:** modelo dedicado y endpoints de ciclo de vida para organizar archivos.
- **IA:** servicio dedicado (p. ej. `project_file_ai_service`) para clasificación y texto de apoyo usando API de OpenAI según configuración.

### 2.7 Redis

- Utilizado para coordinación de **epoch** de mensajes de chat (`cache/redis_client.py`): al publicar mensajes se puede incrementar el epoch para que los clientes sincronicen listados o estado.

### 2.8 Configuración

`app/config.py` (pydantic-settings): base de datos, Redis, CORS, secretos JWT, claves de OpenAI cuando apliquen. Los defaults apuntan a `127.0.0.1` y `localhost` para desarrollo nativo.

### 2.9 Pruebas backend

```bash
cd backend && pytest
```

Requiere PostgreSQL accesible según la configuración; si no hay BD, los tests pueden omitirse con mensaje explícito.

## 3. Frontend

### 3.1 Stack

- **Vite** + **React** + **TypeScript**
- Estado: **Zustand** (`store/`)
- Formularios / validación: **Zod** + esquemas en `schemas/`
- Estilos: **Tailwind** + componentes propios
- **lucide-react** para iconografía (entre otras dependencias)

### 3.2 Organización

- **Páginas:** login, proyectos, workspace de proyecto, chat, tablero, admin.
- **Workspace del proyecto:** pestañas (detalles, archivos, flujo, eventos, pliegos, materiales, presupuesto, etc.) centralizadas en layouts como `WorkspaceTabsLayout`.
- **Constantes** alineadas con backend: `userRoles.ts`, `workflowPhases.ts`, `projectKind.ts`, `projectAllowedFiles.ts`, etc.

### 3.3 Cliente API

`frontend/src/api/client.ts` centraliza llamadas HTTP al backend (incl. prefijo `/api` vía proxy en desarrollo).

### 3.4 Build y pruebas

```bash
cd frontend && pnpm install && pnpm test && pnpm build
```

El proxy de desarrollo en Vite reenvía `/api` al backend local.

## 4. Desarrollo local nativo

`scripts/dev.sh` orquesta Postgres, Redis, backend, frontend, processor y coordination-service sin contenedores.