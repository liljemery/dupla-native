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

```bash
./scripts/dev.sh setup
./scripts/dev.sh bootstrap   # primera vez
./scripts/dev.sh start
```

Puertos: frontend `5173`, backend `8000`, processor `8001`, coordination `8002`.

Despliegue con Docker, producción Windows (nginx + Compose), variables de entorno y scripts: **[docs/DEPLOYMENT.md](./DEPLOYMENT.md)**.

## 5. Seguridad

- Contraseñas hasheadas (no almacenar en claro).
- **JWT** para sesiones API; rutas protegidas con dependencias FastAPI.
- CORS configurado por entorno.
- Archivos: tipo MIME/extension acotados; nombres sanitizados en subida.

## 6. Integraciones externas

- **OpenAI:** clasificación / descripción de archivos de proyecto cuando está configurada la clave y el flujo lo invoca.

## 7. Referencias cruzadas

- Índice de documentación: [docs/README.md](./README.md)
- Módulos funcionales (flujos y pantallas por módulo): [docs/modules/README.md](./modules/README.md)

### Rutas de la aplicación web

Definidas en `frontend/src/App.tsx`: `/login`; tras autenticación, `/app/projects`, `/app/projects/:projectUuid`, `/app/chat`, `/app/tasks`, `/app/admin` (esta última solo rol Gerencia). Ver tabla en [modules/README.md](./modules/README.md).
