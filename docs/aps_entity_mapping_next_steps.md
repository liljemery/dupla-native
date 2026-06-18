# APS Entity Mapping Next Steps

## Objetivo

Resolver, en una fase posterior, qué entidad exacta de Autodesk Viewer corresponde a cada lado de un clash del Motor Dupla.

La integración actual no exige `dbId`. Dibuja boxes por `viewer_bbox`, que es suficiente para validar visualmente clashes en planta. El mapeo a entidad se debe tratar como enriquecimiento, no como requisito para visualizar.

## Campos ya Preparados

El contrato del viewer ya reserva:

- `entity_a_id`
- `entity_b_id`
- `source_refs`
- `viewer_dbid_a`
- `viewer_dbid_b`
- `file_id_a`
- `file_id_b`
- `dwg_a`
- `dwg_b`
- `file_pair`

## Estrategias de Mapeo

### 1. CAD Handle

Si el motor conserva handles de DXF/DWG:

1. Guardar handle en `source_refs`.
2. Consultar propiedades APS por `externalId`, layer o metadata derivada.
3. Resolver `dbId` cuando APS preserve el identificador.

Riesgo: APS no siempre expone handles CAD de forma estable en derivatives 2D.

### 2. Layer + Proximidad Espacial

Cuando no exista handle:

1. Leer geometría/properties APS.
2. Filtrar por layer.
3. Buscar entidades cerca de `viewer_bbox` o `center`.
4. Seleccionar candidatos por intersección o distancia mínima.

Riesgo: muchos elementos pequeños en el mismo layer pueden generar ambigüedad.

### 3. Properties APS

Usar `viewer.model.getBulkProperties` para extraer:

- layer
- name
- external id
- object type
- block name
- handle si existe

Luego persistir una tabla de candidatos por clash.

### 4. `clash_element_mapper.py`

Revisar y extender `clash_element_mapper.py` para que produzca:

- `viewer_dbid_a`
- `viewer_dbid_b`
- confidence del match
- método usado: `cad_handle`, `layer_spatial`, `property_match`
- lista de candidatos alternos

## Persistencia Recomendada

Crear una tabla o JSON enriquecido por `ProjectClashItem`:

```json
{
  "viewer_mapping": {
    "dbid_a": 123,
    "dbid_b": 456,
    "confidence": "medium",
    "method": "layer_spatial",
    "candidates_a": [123, 124],
    "candidates_b": [456]
  }
}
```

## API Recomendada

Ya existe endpoint placeholder:

```http
GET /api/projects/{project_id}/viewer/clashes/{clash_id}/mapping-candidates
```

Devuelve:

```json
{
  "clash_id": "CL-0001",
  "viewer_dbid_a": null,
  "viewer_dbid_b": null,
  "candidates": [],
  "strategy": "not_implemented",
  "warnings": [
    {
      "code": "DBID_MAPPING_NOT_IMPLEMENTED",
      "message": "El viewer funciona por bbox. El mapeo exacto a dbId queda para la siguiente fase."
    }
  ]
}
```

Agregar más adelante:

```http
POST /api/projects/{project_id}/viewer/clashes/{clash_id}/resolve-entities
GET /api/projects/{project_id}/viewer/clashes/{clash_id}/entity-candidates
```

## Fases

### Fase 1: boxes por bbox

Estado: implementado.

- `viewer_bbox` controla overlays.
- `viewer_dbid_a/b` puede ser `null`.
- `mapping-candidates` no bloquea visualización.

### Fase 2: candidatos APS

Pendiente:

1. Consultar APS properties con `getBulkProperties`.
2. Construir índice espacial de fragment/model bounds.
3. Mapear `source_ref` o `cad_handle` cuando exista.
4. Si no hay handle, usar proximidad espacial contra `viewer_bbox`.
5. Guardar `viewer_dbid_a/b` solo cuando el match tenga confianza suficiente.

### Fase 3: interacción avanzada

Pendiente:

1. Highlight de entidad además del box.
2. Selección directa desde Viewer para confirmar candidato.
3. Ocultar/aislar disciplinas.
4. Persistir resolución manual del mapping.

## Criterio de Calidad

No escribir automáticamente `viewer_dbid_a/b` como definitivo si:

- hay más de un candidato cercano
- el layer no coincide
- el bbox de la entidad no intersecta el bbox del clash
- APS está mostrando un coordinate space distinto al del clash

En esos casos, guardar candidatos y marcar `confidence=low`.
