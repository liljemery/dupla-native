# Módulos del sistema

Cada documento incluye: **finalidad del módulo**, **flujos** (secuencias usuario ↔ API), **tablas de rutas** cuando aplica, y **mapeo a pantallas y componentes** React (`frontend/src`). Detalle de tipos y contratos: [TECHNICAL.md](../TECHNICAL.md) y Swagger `/docs`.

| Módulo | Archivo |
|--------|---------|
| Autenticación, sesión y perfil | [auth-y-usuarios.md](./auth-y-usuarios.md) |
| Catálogo de módulos (Arquitectura, etc.) | [modulos-producto.md](./modulos-producto.md) |
| Proyectos, workspace y ciclo de vida | [proyectos-y-flujo.md](./proyectos-y-flujo.md) |
| Doc externo «Flujo IA» vs implementación | [flujo-doc-vs-dupla.md](./flujo-doc-vs-dupla.md) |
| Archivos, carpetas y búsqueda | [archivos-y-carpetas.md](./archivos-y-carpetas.md) |
| Chat interno | [chat.md](./chat.md) |
| Tablero de tareas | [tablero-tareas.md](./tablero-tareas.md) |
| Administración (Gerencia) | [administracion.md](./administracion.md) |

### Rutas de la SPA (`App.tsx`)

| Ruta | Pantalla |
|------|----------|
| `/login` | Login |
| `/app/projects` | Lista / tablero de proyectos |
| `/app/projects/:projectUuid` | Workspace del proyecto |
| `/app/chat` | Chat |
| `/app/tasks` | Tablero de tareas (query `project_uuid` opcional) |
| `/app/admin` | Usuarios (solo Gerencia) |
| `/app/dashboard` | KPIs agregados (solo Gerencia) |
