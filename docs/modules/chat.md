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
