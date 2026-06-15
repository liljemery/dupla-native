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
