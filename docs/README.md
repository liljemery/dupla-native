# Documentación Grupo Dupla — Plataforma Arquitectura

**Última revisión documental:** 2026-04-18 (alineada con los commits del día: usuarios con nombre, tipos de proyecto, archivos con carpetas e IA, chat con participantes, tablero con comentarios y borrado, eventos y archivos paginados, UI unificada).

## Visión general del producto

**Dupla** es una aplicación web para equipos de arquitectura y obra: gestiona **proyectos** con un **flujo de trabajo por fases**, **archivos técnicos** (DWG, DXF, PDF) organizados en **carpetas**, **clasificación asistida**, **chat** (general y por proyecto/grupo), **tablero tipo Kanban** con tarjetas y comentarios, **presupuesto / pliegos / materiales** en el espacio de trabajo del proyecto, y **administración de usuarios** por rol.

Los usuarios se autentican con **JWT**; las capacidades dependen del **rol** (Gerencia, Control, Presupuesto, Arquitectura) y del **módulo** asignado (p. ej. Arquitectura).

### Propuesta de valor

- Un solo lugar para el **estado del proyecto** (fase, eventos, trazabilidad).
- **Archivos de obra** con validación de tipo, metadatos (disciplina, descripción) y sincronización de chat vía **epoch** en Redis.
- **Colaboración** por chat con participantes visibles en conversaciones de grupo.
- **Operación de campo** vía tablero de tareas con comentarios y archivo/borrado de tarjetas.

### Stack resumido

| Capa | Tecnología |
|------|------------|
| API | FastAPI, SQLAlchemy async, Alembic, Pydantic |
| Datos | PostgreSQL |
| Caché / sync chat | Redis |
| Frontend | Vite, React, TypeScript, Tailwind, Zustand, Zod |
| Despliegue | Scripts nativos (`scripts/dev.sh`); Docker Compose; prod Windows — ver [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |

## Mapa de documentación

| Documento | Contenido |
|-----------|-----------|
| Despliegue | [DEPLOYMENT.md](./DEPLOYMENT.md) — Docker, prod Windows, nginx, migraciones, scripts, troubleshooting |
| [README del repositorio](../README.md) | Cómo levantar el entorno, seed, pruebas, estructura de carpetas de código |
| [Informe funcional completo](./INFORME_ESTRUCTURA_FUNCIONAL_COMPLETO.md) | Estado actual del producto (~74%), clashes, presupuesto, integraciones |
| [Roadmap hacia 100%](./ROADMAP_COMPLETITUD_100.md) | Problemas pendientes, Grupo A (prioridades) y Grupo B (resto), hitos M1–M4 |
| [Documentación técnica](./TECHNICAL.md) | Arquitectura, convenciones, integraciones (OpenAI), variables de entorno, testing |
| [Módulos del sistema](./modules/README.md) | Índice y enlaces a cada área funcional |
| [Playbook de ejecución](./playbook.md) | Lineamientos históricos de producto (grillas tipo Excel, JSONB); complementar con `TECHNICAL.md` para el esquema actual |

## Módulos (por área funcional)

Cada ficha incluye **para qué sirve el módulo**, **flujos** (paso a paso) y **pantallas/componentes** del frontend que disparan o consumen la API.

1. [Autenticación, sesión y perfil](./modules/auth-y-usuarios.md) — JWT, `/api/me`, notificaciones en sidebar.
2. [Catálogo de módulos de producto](./modules/modulos-producto.md) — `GET /api/modules`, asignación `module_ids` y acceso al dominio.
3. [Proyectos, workspace y ciclo de vida](./modules/proyectos-y-flujo.md) — Proyecto, fases, pestañas del workspace, exports, plan delivery, arquitectura JSON, chat del proyecto.
4. [Archivos, carpetas y búsqueda](./modules/archivos-y-carpetas.md) — Subidas, carpetas, paginación, IA opcional.
5. [Chat interno](./modules/chat.md) — General, directos, grupos, epoch Redis, participantes.
6. [Tablero de tareas](./modules/tablero-tareas.md) — Kanban global o por proyecto, comentarios, archivo/borrado.
7. [Administración (Gerencia)](./modules/administracion.md) — CRUD de usuarios y módulos.

## Cambios recientes reflejados en código (2026-04-18)

Resumen orientado a producto:

- **Usuarios:** campos `first_name` y `last_name`; roles operativos ampliados (Gerencia, Control, Presupuesto, Arquitectura).
- **Proyectos:** tipo **RESIDENTIAL** / **TENDER**; modal de creación **multi-paso**; fases de flujo actualizadas (p. ej. transición hacia **ARCHITECTURE_REVIEW**, fase **COMPLETE**).
- **Archivos:** carpetas de proyecto; listados **paginados** y **búsqueda**; validación estricta **.dwg / .dxf / .pdf**; asistente de subida e integración **OpenAI** para clasificación/descripción.
- **Chat:** participantes en respuestas de conversación; mejoras de sidebar y layout.
- **Tablero:** comentarios en tarjetas; **archivar** y **eliminar** tarjetas de forma permanente.
- **Eventos de proyecto:** listado con **paginación** y filtros.
- **UI:** consistencia tipográfica y de layout (layout principal, pestañas de workspace, archivos en rejilla/lista).

Para detalle de implementación, rutas y modelos, ver [TECHNICAL.md](./TECHNICAL.md).
