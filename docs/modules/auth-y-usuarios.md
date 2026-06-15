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
