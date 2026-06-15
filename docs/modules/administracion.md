# Módulo: Administración de usuarios (Gerencia)

## Para qué sirve

Que el rol **Gerencia** gestione el **directorio de usuarios** de la aplicación: **listar**, **crear** y **actualizar** cuentas (email, nombre, apellido, rol, contraseña opcional en edición) y **asignar módulos de producto** (p. ej. acceso **Arquitectura** mediante `module_ids`).

Es el único lugar pensado para el alta masiva de identidades; el resto de roles no accede a estas rutas.

## Superficie API — `/api/admin`

| Método | Ruta | Función |
|--------|------|---------|
| GET | `/users` | Lista completa con módulos asignados |
| POST | `/users` | Crear usuario + `module_ids` |
| PATCH | `/users/{user_uuid}` | Actualizar datos, rol, módulos, contraseña opcional |

Todas las rutas exigen `require_gerencia` (403 si el rol no es Gerencia).

## Flujos

### 1. Listar usuarios

1. Al abrir la página admin, `GET /api/admin/users` rellena la tabla.
2. Cada fila muestra email, nombre, rol y módulos (ids).

### 2. Crear usuario

1. Modal en modo crear (`AdminUserModal`): formulario validado con Zod (`adminCreateUserSchema`).
2. `POST /api/admin/users` con cuerpo que incluye `module_ids` (p. ej. `[1]` si “Arquitectura” está marcado).
3. Cierre y refresco de lista.

### 3. Editar usuario

1. Modal en modo edición: mismos campos; contraseña vacía = no cambiar.
2. `PATCH /api/admin/users/{uuid}`.

### 4. Uso indirecto en creación de proyectos

1. `ProjectsPage` (solo Gerencia) llama `GET /api/admin/users` para poblar el selector de **miembros** al crear un proyecto (no es administración de usuarios en sí, pero consume el mismo listado).

## Pantallas y componentes

| Pantalla / componente | Ruta | Influencia |
|----------------------|------|------------|
| `AdminUsersPage` | `/app/admin` | Lista usuarios; abre `AdminUserModal`. Protegida por `RequireGerencia` en `App.tsx`. |
| `AdminUserModal` | Modal | POST/PATCH a `/api/admin/users`. Checkbox de módulo Arquitectura → `module_ids: [1]`. |
| `Sidebar` | Layout | Enlace **Usuarios** solo si `role === 'GERENCIA'`. |

**Esquemas:** `schemas/adminUser.ts` (Zod).

## Relación con otros módulos

- [modulos-producto.md](./modulos-producto.md): los `module_ids` definidos aquí condicionan acceso a proyectos y APIs del dominio.
- [auth-y-usuarios.md](./auth-y-usuarios.md): los usuarios creados inician sesión igual que el resto (`POST /api/auth/token`).
