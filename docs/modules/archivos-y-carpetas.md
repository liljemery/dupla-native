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
