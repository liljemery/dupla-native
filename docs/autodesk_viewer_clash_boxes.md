# Autodesk Viewer Clash Boxes

## Objetivo

Mostrar boxes sobre clashes detectados por Motor Dupla en Autodesk Platform Services Viewer, sin reemplazar el detector existente.

La integración adapta la salida del motor a un contrato JSON consumible por una extensión del Viewer. El frontend dibuja overlays por `bbox`, no por `dbId`, por lo que puede funcionar aunque todavía no exista mapeo exacto de entidad CAD a elemento APS.

## Fuente de datos

Fuente principal:

- `ProjectClashItem.bounds_minx_mm`
- `ProjectClashItem.bounds_miny_mm`
- `ProjectClashItem.bounds_maxx_mm`
- `ProjectClashItem.bounds_maxy_mm`
- `ProjectClashItem.centroid_x_mm`
- `ProjectClashItem.centroid_y_mm`
- `ProjectClashItem.alignment_dx_mm`
- `ProjectClashItem.alignment_dy_mm`
- `ProjectClashItem.raw_json`

Fuente fallback:

- Artefactos del job en `ProjectClashJob.output_dir`
- `primary_incidents.json`
- `clash_project_report.json`

Campos del motor que el adapter intenta aprovechar cuando existen:

- `plan_intersection_bounds_mm`
- `plan_centroid_mm`
- `world_bounds`
- `world_centroid`
- `model_centroid`
- `bounds`

## Espacios de Coordenadas

### `model_bbox_mm`

Corresponde al bbox normalizado del motor. Puede incluir `alignment_offset_mm`, `alignment_dx_mm`, `alignment_dy_mm` o traducciones internas del pipeline de coordinación.

Usarlo cuando Autodesk Viewer esté cargando un modelo compuesto o normalizado con el mismo sistema de coordenadas del motor.

### `world_bbox_mm`

Corresponde al bbox más cercano al DWG original. Si el motor no entrega `world_bounds`, el backend calcula:

```text
world_bbox_mm = model_bbox_mm - alignment_offset_mm
```

Si no hay offset disponible, el backend usa `model_bbox_mm` como fallback y agrega warning `MISSING_ALIGNMENT_OFFSET`.

Este es el default porque APS normalmente muestra el DWG original traducido.

### `viewer_bbox`

Es el bbox efectivo que debe dibujar el frontend:

- `coordinate_space=world`: `viewer_bbox = world_bbox_mm`
- `coordinate_space=model`: `viewer_bbox = model_bbox_mm`

Después de elegir `world` o `model`, el backend aplica la configuración persistida de `CoordinateMapper` del proyecto. Por eso el response también incluye:

- `raw_model_bbox_mm`
- `raw_world_bbox_mm`
- `viewer_bbox`
- `mapper_applied`
- `alignment_offset_mm`
- `coordinate_settings_applied`

## Mapper por Proyecto

La calibración se guarda en `project_viewer_coordinate_settings`.

Campos:

- `coordinate_space`: `world` o `model`
- `scale`: escala uniforme
- `offset_x`, `offset_y`, `offset_z`: desplazamiento en coordenadas viewer
- `invert_y`: invierte el eje Y
- `rotation_degrees`: rotación alrededor del origen
- `unit_factor`: conversión de unidad antes de aplicar escala
- `notes`: notas de calibración

Usar este mapper cuando APS muestre el derivative con origen, escala o eje distinto al usado por el motor.

Ejemplos:

- DWG original APS: empezar con `coordinate_space=world`.
- Modelo compuesto/normalizado por motor: probar `coordinate_space=model`.
- Si boxes salen desplazados pero con tamaño correcto: ajustar `offset_x` / `offset_y`.
- Si boxes salen en escala incorrecta: ajustar `unit_factor` o `scale`.
- Si boxes salen espejados verticalmente: activar `invert_y`.
- Si boxes salen rotados: ajustar `rotation_degrees`.

## Variables de Entorno

APS usa la configuración ya existente del backend:

- `CLIENT_ID`
- `CLIENT_SECRET`
- `APS_BUCKET_NAME`

El frontend nunca recibe `CLIENT_SECRET`. Solo consume un token temporal desde el backend.

## Endpoints

### Viewer HTML

```http
GET /api/projects/{project_id}/viewer?coordinate_space=world
GET /api/projects/{project_id}/viewer?coordinate_space=model
GET /api/projects/{project_id}/viewer?coordinate_space=world&debug=true
```

### Configuración del Viewer

```http
GET /api/projects/{project_id}/viewer/config?coordinate_space=world
```

Devuelve URN APS, URL de token, URL de clashes, modo de viewer y viewables disponibles.

Si no hay modelo traducido o archivo compatible, responde con error claro: `Modelo no traducido en APS todavía`.

La configuración prefiere `ProjectFile.aps_urn`. Si no existe, usa fallback derivado desde bucket/object key y agrega warning `USING_DERIVED_URN_FALLBACK`.

### APS Translate y Manifest por Archivo

```http
POST /api/projects/{project_id}/aps/translate
POST /api/projects/{project_id}/files/{file_id}/aps/translate
POST /api/projects/{project_id}/files/{file_id}/aps/refresh-manifest
```

Estos endpoints persisten:

- `aps_bucket_key`
- `aps_object_key`
- `aps_object_id`
- `aps_urn`
- `aps_derivative_status`
- `aps_viewable_guid`
- `aps_last_translated_at`
- `aps_manifest_json`

### Clashes para Viewer

```http
GET /api/projects/{project_id}/viewer/clashes?coordinate_space=world
GET /api/projects/{project_id}/viewer/clashes?coordinate_space=model
```

Filtros:

- `severity=critical|high|medium|low`
- `discipline=architecture|structure|plumbing|mechanical|electrical`
- `include_resolved=true|false`

### Coordinate Settings

```http
GET /api/projects/{project_id}/viewer/coordinate-settings
PUT /api/projects/{project_id}/viewer/coordinate-settings
POST /api/projects/{project_id}/viewer/coordinate-settings/reset
```

Body de `PUT`:

```json
{
  "coordinate_space": "world",
  "scale": 1.0,
  "offset_x": 0.0,
  "offset_y": 0.0,
  "offset_z": 0.0,
  "invert_y": false,
  "rotation_degrees": 0.0,
  "unit_factor": 1.0,
  "notes": "Calibrado desde Autodesk Viewer"
}
```

### APS Token

```http
GET /api/aps/token
```

Devuelve token temporal con scopes mínimos para visualizar derivatives.

### APS Manifest

```http
GET /api/projects/{project_id}/aps/manifest
```

Consulta el estado de traducción APS y devuelve derivatives/viewables detectados.

### Status de Clash

```http
POST /api/projects/{project_id}/viewer/clashes/{clash_id}/status
```

Body:

```json
{
  "status": "reviewed",
  "comment": "Validado en reunión de coordinación"
}
```

### Mapping Candidates

```http
GET /api/projects/{project_id}/viewer/clashes/{clash_id}/mapping-candidates
```

Hoy devuelve candidatos vacíos con warning `DBID_MAPPING_NOT_IMPLEMENTED`. El viewer sigue funcionando por bbox.

## Cómo Correr

Desde `backend/`:

```bash
uvicorn app.main:app --reload
```

Abrir:

```text
http://localhost:8000/api/projects/{project_id}/viewer?coordinate_space=world
```

Demo local sin APS real:

```text
http://localhost:8000/api/projects/demo/viewer?debug=true
```

Modo calibración:

```text
http://localhost:8000/api/projects/{project_id}/viewer?coordinate_space=world&calibrate=true
```

## Tests

Desde `backend/`:

```bash
pytest tests/test_clash_coordinate_mapper.py tests/test_clash_viewer_adapter.py
pytest tests/test_viewer_coordinate_settings.py tests/test_aps_urn_persistence.py tests/test_mapping_candidates.py
pytest tests/test_clash_viewer_routes.py
```

Los tests de rutas dependen de que el fixture de Postgres del backend esté disponible. Si no lo está, se marcan como skipped.

## Frontend

Archivos principales:

- `backend/app/static/aps_viewer/index.html`
- `backend/app/static/aps_viewer/viewer.js`
- `backend/app/static/aps_viewer/ClashBoxesExtension.js`
- `backend/app/static/aps_viewer/ClashSidebar.js`
- `backend/app/static/aps_viewer/apiClient.js`

La extensión registra:

```js
Autodesk.Viewing.theExtensionManager.registerExtension("Dupla.ClashBoxesExtension", ClashBoxesExtension);
```

Los boxes se dibujan en un overlay scene:

```js
viewer.impl.createOverlayScene("dupla-clash-boxes-overlay");
```

## Planos 2D

El viewer está configurado para mostrar planos/sheets 2D de APS como fondo del clash review.

Reglas:

- El backend prefiere `role=2d`, `role=sheet`, nombres tipo `sheet` o `layout` al detectar `aps_viewable_guid`.
- El frontend vuelve a preferir un viewable 2D aunque exista un GUID configurado a un viewable 3D.
- Si APS no entrega ningún sheet/layout 2D, el frontend usa el primer viewable disponible como fallback.
- No se reconstruye el plano desde geometrías DXF locales; el plano visible es el derivative APS del DWG/DXF/PDF.

Los boxes siguen siendo overlay por bbox, encima del plano 2D.

## Debug

Usar:

```text
/api/projects/{project_id}/viewer?coordinate_space=world&debug=true
```

El modo debug muestra:

- coordinate space activo
- warnings del backend
- crosshair en demo
- labels por clash en demo
- mensaje cuando los valores grandes en mm son esperados

Para validar alineación:

1. Abrir con `coordinate_space=world`.
2. Confirmar que los boxes caen sobre el DWG original APS.
3. Abrir con `coordinate_space=model`.
4. Comparar desplazamientos.
5. Si `model` alinea y `world` no, el DWG mostrado probablemente fue transformado igual que el motor.
6. Si ninguno alinea, ajustar `CoordinateMapper` por proyecto.

## Modo Calibración

Usar:

```text
/api/projects/{project_id}/viewer?coordinate_space=world&calibrate=true
```

El panel flotante “Calibración de coordenadas” permite:

- alternar `world` / `model`
- ajustar `scale`
- ajustar `offset_x`, `offset_y`, `offset_z`
- activar `invert_y`
- ajustar `rotation_degrees`
- ajustar `unit_factor`
- aplicar cambios temporalmente sin guardar
- guardar configuración con `PUT /viewer/coordinate-settings`
- resetear configuración
- mostrar centroides
- mostrar labels
- inspeccionar bbox raw y bbox transformado del clash seleccionado

Flujo recomendado:

1. Abrir con `coordinate_space=world&calibrate=true`.
2. Seleccionar un clash visible en la lista.
3. Ajustar offsets o escala.
4. Presionar “Aplicar” para validar visualmente.
5. Presionar “Guardar configuración”.
6. Refrescar el navegador y confirmar que los boxes quedan alineados.
7. Usar “Reset” para volver a identidad.

## world vs model

`world` sigue siendo el default porque Autodesk Viewer normalmente muestra el DWG original traducido por APS.

`model` debe usarse cuando el viewable APS corresponde a un modelo compuesto, normalizado o transformado igual que el Motor Dupla.

No asumir que `model_bbox_mm` coincide con APS si APS cargó el DWG original.

## dbId Mapping

`viewer_dbid_a` y `viewer_dbid_b` todavía no son obligatorios.

La integración actual:

- dibuja boxes por `viewer_bbox`
- no bloquea si no hay CAD handle
- no bloquea si no hay `dbId`
- expone endpoint placeholder de candidatos

La fase posterior resolverá entidades APS por properties, handles, `source_refs` y proximidad espacial.

## Limitaciones

- Los clashes actuales son principalmente planta 2D en milímetros.
- No todos los clashes tienen CAD handle.
- `viewer_dbid_a` y `viewer_dbid_b` pueden ser `null`.
- APS puede aplicar transformaciones de unidad/origen según derivative; si ocurre, se debe configurar mapper por proyecto.
- Si archivos fueron separados por `file_translation_mm`, el DWG original APS debe usar `world_bbox_mm`.
- El mapeo exacto a entidad APS queda para una fase posterior.
