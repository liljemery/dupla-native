# Pipeline de Identificación de Clashes — Dupla

## Índice

1. [Visión general](#1-visión-general)
2. [Fase 0 — Selección y auditoría de fuentes](#2-fase-0--selección-y-auditoría-de-fuentes)
3. [Fase 1 — Extracción y normalización de geometría](#3-fase-1--extracción-y-normalización-de-geometría)
4. [Fase 2 — Alineación de marcos de referencia](#4-fase-2--alineación-de-marcos-de-referencia)
5. [Fase 3 — Detección de clashes](#5-fase-3--detección-de-clashes)
6. [Fase 4 — Mapeo semántico](#6-fase-4--mapeo-semántico)
7. [Backend — Storage y workflow](#7-backend--storage-y-workflow)
8. [API — Endpoints y respuestas](#8-api--endpoints-y-respuestas)
9. [Diagrama de estados del workflow](#9-diagrama-de-estados-del-workflow)
10. [Mapa de archivos](#10-mapa-de-archivos)

---

## 1. Visión general

El pipeline toma archivos CAD crudos de un proyecto NASAS y produce incidentes de clash geo-referenciados, persistidos en base de datos y expuestos en tres APIs: clash jobs, workflow de revisión y viewer APS.

```
Archivos CAD/PDF (NASAS)
        │
        ▼ Fase 0
  Selección & Auditoría ──── rechaza: combinados, as-built, anotación >60%
        │
        ▼ Fase 1
  Extracción & Normalización ── DWG/DXF/PDF/raster → elementos en metros
        │
        ▼ Fase 2
  Alineación de marco ─────── Layer A (identity) → B (grid) → C (manual)
        │
        ▼ Fase 3
  Detección de clashes ──────┬── Cross-discipline 2.5D  (clash.py)
        │                    └── Intra-discipline 2D    (intra_clash.py)
        │
        ▼ Fase 4
  Mapeo semántico ─────────── incidente → entidad CAD exacta + nombre
        │
        ▼ Backend
  ProjectClashJob ─────────── ProjectClashItem ─── ProjectClashEvent
        │
        ▼ API
  /clash/jobs   /clash-workflow   /viewer
```

**Script orquestador:** `motor/coordination/scripts/run_nasas09_project_coordination.py`  
Stages configurables: `coordinate_audit` · `arq_est` · `hotspots` · `full`

---

## 2. Fase 0 — Selección y auditoría de fuentes

### 2.1 Selección de archivos

**Módulo:** `motor/coordination/selection/source_selection.py`

Filtra el árbol NASAS para quedarse solo con archivos de planta válidos.

**Criterios de inclusión:**
- Extensión `.dwg`, `.dxf`, `.pdf`, `.png`, `.jpg`
- Ruta dentro de `/planos recibidos/` (configurable)
- No coincide con patrones de exclusión:
  - revisiones internas: `revision/`, `obsoleto`
  - derivados de PDF: imágenes detectadas por hash
  - combinados: `solapado`, `overlay`, `TODAS`, `COORDINACION`
- Si existen `.dwg` y `.dxf` del mismo documento: prefiere `.dxf`

**Output:** `list[Path]` + `dict` de rechazos por categoría

---

### 2.2 Auditoría de elegibilidad

**Módulo:** `motor/coordination/selection/coordinate_audit.py`

Para cada archivo candidato calcula su estado de elegibilidad.

```
AuditStatus:
  eligible          → ≥20 elementos primarios, ratio_anotación < 60%
  annotation_noise  → anotaciones / total > umbral
  bbox_only         → sin geometría primaria útil
  needs_alignment   → archivo combinado / as-built / muy grande
  extract_failed    → sin perfil ni elementos extraídos
```

**Banda de coordenadas:** clasifica centroide en celda 500km × 500km; descarta pares de disciplinas en bandas distintas.

**Output por archivo:**

```json
{
  "rel_path": "planos recibidos/ELEC/SERENA18_ELEC_P1.dxf",
  "discipline": "ELECTRICIDAD",
  "level_id": "NPT_P1",
  "audit_status": "eligible",
  "coordinate_band_key": [147, 75],
  "centroid_mm": [73285000, 37610000],
  "selected_primary_count": 538,
  "notes": []
}
```

---

### 2.3 Pre-matching documental

**Módulo:** `motor/coordination/selection/fast_compare.py`

Calcula un score 0–1 para cada par de archivos. Score ≥ 0.75 → `auto_comparable`.

| Componente | Peso |
|---|---|
| Disciplinas distintas requeridas | 25% |
| Mismo nivel (level_id) | 25% |
| Compatibilidad de tipo de plano | 20% |
| Hint de overlap geométrico | 15% |
| Proximidad de revisión (≤45 días = 1.0) | 10% |
| Calidad de ancla documental | 5% |

**Decisiones de salida:** `auto_comparable` · `manual_candidate` · `not_comparable`

---

## 3. Fase 1 — Extracción y normalización de geometría

### 3.1 Extracción por fuente

| Módulo | Fuente | Método |
|---|---|---|
| `from_dwg_accore.py` | DWG via AutoCAD Core Console | Perfilado de entidades + bbox clustering |
| `from_dwg_com.py` | DWG via COM (Windows) | Lectura directa de entidades |
| `from_dwg_ezdxf.py` | DXF via ezdxf | Parsing nativo Python |
| `from_dwg_aps.py` | SVF APS | Fragmentos del viewer Autodesk |
| `from_pdf_vector.py` | PDF vectorial | Extracción de paths |
| `from_raster_image.py` | PNG/JPG | Vision-based bbox |
| `from_aps_viewer_dump.py` | JSON dump APS | Propiedades APS + geometría SVF |

Todos los extractores producen una lista de elementos con:

```python
{
  "handle": str,          # Handle CAD (hex)
  "layer": str,
  "entity_type": str,     # "LWPOLYLINE", "INSERT", etc.
  "model_bounds": [xmin, ymin, xmax, ymax],   # en unidades nativas
  "model_center": [x, y],
  "physical": bool,
  "geometry_quality": str  # "good" | "coarse" | "proxy" | "annotation"
}
```

---

### 3.2 Normalización de unidades

**Módulo:** `motor/coordination/core/units.py`  
**Orquestador:** `motor/coordination/core/geometry_normalizer.py`

**Estrategia de inferencia (en orden de confianza):**

1. **Texto de cotas:** compara valor numérico en dimension text con distancia medida → razón directa
2. **Longitud de elementos:** la mediana de elementos físicos debe estar en rango 0.05–50m
3. **Outline del edificio plausible:** el bbox del cluster principal debe ser 10–500m en la dimensión mayor

**Reconciliación declarado vs inferido:**

```
Si |factor_declarado - factor_inferido| / factor_declarado < 5% → usa declarado
Si discrepan → usa inferido y marca unit_correction en el artefacto
```

**Factores por unidad INSUNITS:**

| INSUNITS | Unidad | factor_to_meters |
|---|---|---|
| 1 | inch | 0.0254 |
| 2 | foot | 0.3048 |
| 4 | mm | 0.001 |
| 5 | cm | 0.01 |
| 6 | m | 1.0 |

> INSUNITS se considera no confiable si el outline resultante no es físicamente plausible para un edificio (10–500m).

---

### 3.3 Limpieza de geometría

**Módulo:** `motor/coordination/core/geometry_cleaner.py`

Separa el cluster principal de elementos stray.

**Método `percentile_main_cluster`:**
1. Calcula percentil 5–95 de centros de elementos físicos
2. Agrega padding 20% en cada dirección
3. Marca como `stray` todo lo exterior a esa ventana
4. El cluster principal obtiene `cleaned_outline_bounds_m` y `cleaned_centroid_m`

**Output:**

```json
{
  "method": "percentile_main_cluster",
  "stray_count": 71,
  "cleaned_outline_bounds_m": [-19.3, 25.6, 115.8, 123.9],
  "cleaned_outline_size_m": [135.1, 98.3],
  "cleaned_centroid_m": [48.2, 74.7]
}
```

---

### 3.4 Artefacto de salida (Phase 1)

Cada disciplina produce un archivo `{DISC}.sanitized.geometry.json`:

```json
{
  "dxf_path": "/path/to/file.dxf",
  "unit_sanitation": {
    "factor_to_meters": 0.001,
    "factor_reason": "geometry_inferred_meters",
    "declared_insunits": 4,
    "declared_units": "mm"
  },
  "unit_correction": null,
  "cleanup": {
    "cleaned_outline_bounds_m": [-19.3, 25.6, 115.8, 123.9],
    "cleaned_outline_size_m": [135.1, 98.3],
    "cleaned_centroid_m": [48.2, 74.7],
    "stray_count": 71
  },
  "elements": [
    {
      "handle": "2BF06F",
      "layer": "I-PLUMB-FIXT",
      "entity_type": "INSERT",
      "model_bounds": [-19100, 25800, -18900, 26100],
      "model_center": [-19000, 25950],
      "model_bounds_m": [-19.1, 25.8, -18.9, 26.1],
      "model_center_m": [-19.0, 25.95],
      "physical": true,
      "geometry_quality": "good"
    }
  ]
}
```

---

## 4. Fase 2 — Alineación de marcos de referencia

**Módulo:** `motor/coordination/core/frame_alignment.py`  
**Control manual:** `motor/coordination/core/control_points.py`

Resuelve un transform 2D por disciplina que mapea sus coordenadas (metros sanitizados) al frame de la disciplina de referencia (ARQ, fallback EST).

```
ref_xy_m = matrix @ disc_xy_m + translation
         = scale · R · (1 o flip_y) @ disc_xy_m + translation
```

### Capas de resolución (en orden)

#### Layer A — Identidad

Compara centroid y esquinas de bbox entre la disciplina y la referencia.  
Si `max(centroid_delta, corner_rms) ≤ 2.0 m` → transform identidad, listo.

#### Layer B — Ancla automática

Intenta registración automática en tres pasos:

1. **Grid bubbles:** líneas en capas `EJE*`/`GRID`/`AXIS` + etiquetas TEXT; matching por texto idéntico (e.g. `"B-3"`)
2. **Intersecciones de grid:** clustering de líneas horizontales/verticales → array de intersecciones
3. **Polígono de outline:** 4 esquinas del bbox del edificio, con variantes de rotación y flip

Para cada alternativa corre `fit_similarity` (SVD Umeyama) ± RANSAC si ≥4 puntos.  
Acepta si `residual_rms ≤ 1.0 m` y `0.5 ≤ scale ≤ 2.0`.

#### Layer C — Control points manuales (persistidos)

El usuario identifica el mismo punto físico en el plano de la disciplina y en ARQ. Opciones:

- `disc_handle` / `ref_handle`: handle CAD → `ezdxf` resuelve el centro del bbox de la entidad
- `disc_xy` / `ref_xy`: coordenadas en metros tecleadas directamente

**Gates para persistir:**

| Métrica | Umbral |
|---|---|
| Puntos mínimos | ≥ 3 |
| No colineales | ratio SVD > 0.02 |
| `|scale − 1.0|` | ≤ 0.02 |
| RMS del fit | ≤ 0.5 m |
| Hold-out error | ≤ 0.5 m |

Si todos los gates pasan: status `solved`; transform escrito en `alignment_manifest.json`.

**Comando dry-run / solve:**

```bash
export PYTHONPATH="$(pwd)/motor"
PY=/Users/samuelfernandez/anaconda3/bin/python

# Validar sin persistir
$PY motor/coordination/core/control_points.py \
  --manifest var/coord_outputs/serena18_run/alignment_manifest.json \
  --work-dir var/coord_outputs/serena18_run \
  --discipline ELEC --no-persist --verify

# Persistir si OK
$PY motor/coordination/core/control_points.py \
  --manifest var/coord_outputs/serena18_run/alignment_manifest.json \
  --work-dir var/coord_outputs/serena18_run \
  --discipline ELEC --solve --verify
```

**Output de `frame_alignment.py`:**

```json
{
  "reference": "ARQ",
  "verdict": "FRAME PARTIAL: [ARQ, EST] aligned; [ELEC, MEC, HS] need manual control points.",
  "verdict_kind": "FRAME_PARTIAL",
  "transforms": {
    "ARQ": {
      "layer": "A", "method": "identity_reference",
      "scale": 1.0, "rotation_deg": 0.0,
      "translation": [0.0, 0.0], "matrix": [[1,0],[0,1]],
      "status": "ok"
    },
    "EST": {
      "layer": "C", "method": "manual_control_points_persisted",
      "scale": 0.9990, "rotation_deg": 0.78,
      "translation": [-160120.38, -626236.62],
      "matrix": [[0.9989, -0.0136],[0.0136, 0.9989]],
      "residual_rms_m": 0.008, "residual_max_m": 0.011,
      "n_control_points": 4, "status": "ok"
    },
    "ELEC": {
      "layer": null, "method": "needs_manual_control_points",
      "status": "needs_manual_control_points"
    }
  },
  "features": {
    "ARQ": {"physical_count": 1590, "outline_size_m": [135.1, 98.3]},
    "EST": {"physical_count": 420,  "outline_size_m": [38.1, 19.3]}
  }
}
```

---

## 5. Fase 3 — Detección de clashes

### 5.1 Cross-discipline 2.5D

**Módulo:** `motor/coordination/core/clash.py`

Detecta solapamientos geométricos entre elementos de **disciplinas distintas** con validación vertical (eje Z).

**Inputs:**
- `elements: list[Element25D]` — footprint (polígono) + ZInterval por elemento
- `registry: ProjectLevelRegistry` — offsets de niveles en mm
- `planar_tolerance_mm` (default 0) — buffer de holgura
- `min_plan_area_mm2` (default 1.0) — área mínima de intersección

**Algoritmo:**
1. Construye `STRtree` sobre footprints (optimización espacial para >80 elementos)
2. Para cada par inter-disciplina con intersección en planta:
   - Verifica solapamiento Z: `[z_min_a, z_max_a] ∩ [z_min_b, z_max_b]`
   - Calcula área de intersección en planta
   - Asigna `confidence` según `geometry_quality` del par (min de los dos)
3. Agrupa en incidentes por celda 2km × 2km

**Output — `ClashConflict`:**

```json
{
  "element_id_a": "ELEC|L1|I-CONDUIT|handle:3A2B1C",
  "element_id_b": "STRUC|L1|S-BEAM|handle:7F8E9D",
  "discipline_a": "ELECTRICIDAD",
  "discipline_b": "ESTRUCTURA",
  "clash_type": "HARD",
  "overlap_depth_z_mm": 120.0,
  "z_overlap_range_project_mm": [2400.0, 2520.0],
  "plan_intersection_area_mm2": 45000.0,
  "plan_intersection_centroid_mm": [48200.0, 74700.0],
  "plan_intersection_bounds_mm": [48000, 74500, 48400, 74900],
  "level_ids": ["NPT_P1", "NPT_P1"],
  "confidence": "medium",
  "geometry_sources": ["dwg_accore_bbox", "dwg_accore_bbox"],
  "source_refs": ["ELEC.dxf|I-CONDUIT|LWPOLYLINE|3A2B1C", "EST.dxf|S-BEAM|LINE|7F8E9D"],
  "notes": []
}
```

**Output — `ClashIncident`:**

```json
{
  "incident_id": "incident_0001",
  "file_pair": ["ELEC.dxf", "EST.dxf"],
  "level_id": "NPT_P1",
  "cell_key": [24, 37],
  "member_count": 5,
  "representative_conflict": { "...": "ClashConflict del más representativo" },
  "confidence": "medium"
}
```

---

### 5.2 Intra-discipline 2D

**Módulo:** `motor/coordination/core/intra_clash.py`

Detecta solapamientos entre capas **conflictivas** dentro de la misma disciplina.

**Configuración de pares (ejemplo ARQ interior):**

```python
LayerPairRule("I-PLUMB-FIXT", "I-FURN",   "Sanitario bajo mobiliario",        min_overlap_frac=0.40, weight=1.5)
LayerPairRule("I-EQUIPMENT",  "I-FURN",   "Equipo solapado con mobiliario",   min_overlap_frac=0.40, weight=1.3)
LayerPairRule("I-WALL",       "I-WALL",   "Muro duplicado / solapado",        min_overlap_frac=0.70, weight=1.2)
LayerPairRule("I-MILLWORK",   "I-MILLWORK","Carpintería duplicada",            min_overlap_frac=0.70, weight=1.2)
LayerPairRule("I-FURN",       "I-FURN",   "Mobiliario solapado (duplicado)",  min_overlap_frac=0.85, weight=0.5)
```

**Severidad por `overlap_frac × weight`:**

| Umbral | Severidad |
|---|---|
| ≥ 0.80 | `critical` |
| ≥ 0.50 | `major` |
| < 0.50 | `minor` |

**Output — `IntraClash`:**

```json
{
  "handle_a": "2BF06F",
  "handle_b": "2BF490",
  "layer_a": "I-PLUMB-FIXT",
  "layer_b": "I-FURN",
  "rule_label": "Sanitario bajo mobiliario (acceso bloqueado)",
  "overlap_area_m2": 2.88,
  "overlap_frac": 1.0,
  "overlap_bounds_m": [41.43, 64.70, 42.33, 67.90],
  "centroid_m": [41.88, 66.30],
  "severity": "critical"
}
```

**Output — `IntraIncident` (agrupado por celda 3m):**

```json
{
  "incident_id": "ARQ-INTRA-001",
  "severity": "critical",
  "members": ["...lista de IntraClash..."],
  "representative": { "...": "el de mayor overlap_frac × weight" },
  "bounds_m": [41.43, 64.70, 42.33, 67.90],
  "layers": ["I-PLUMB-FIXT", "I-FURN"]
}
```

---

## 6. Fase 4 — Mapeo semántico

### 6.1 Clasificación semántica

**Módulo:** `motor/coordination/semantic/semantic_elements.py`

Clasifica cada elemento CAD a un tipo constructivo conservador usando solo evidencia local (layer, nombre de bloque, handle).

**Tipos:** `door` · `window` · `column` · `beam` · `slab` · `wall` · `duct` · `pipe` · `conduit` · `fixture` · `equipment` · `unknown_*`

**Output — `SemanticElement25D`:**

```json
{
  "semantic_element_id": "SEM-ELEC-001",
  "source_element_id": "ELEC|L1|I-CONDUIT|3A2B1C",
  "discipline": "ELECTRICIDAD",
  "level_id": "NPT_P1",
  "layer": "I-CONDUIT",
  "cad_handle": "3A2B1C",
  "entity_type": "LWPOLYLINE",
  "block_name": null,
  "element_type": "conduit",
  "element_name": null,
  "bbox_mm": [48000, 74500, 48400, 74900],
  "centroid_mm": [48200, 74700],
  "geometry_confidence": "high",
  "semantic_type_confidence": "medium",
  "semantic_type_reason": "layer_token_match",
  "classification_signals": ["layer:I-CONDUIT → token:CONDUIT"]
}
```

---

### 6.2 Mapeo de incidente a entidad CAD

**Módulo:** `motor/coordination/core/clash_element_mapper.py`

Para cada incidente busca la entidad CAD más probable en cada disciplina.

**Score de matching (por candidato):**

| Componente | Peso |
|---|---|
| Solapamiento de bbox | 35% |
| Distancia de centroides | 25% |
| Coincidencia de layer | 15% |
| Calidad de geometría | 15% |
| Coincidencia de CAD handle | 10% |

**Confidence:** `high` (≥0.75) · `medium` (≥0.55) · `low` (<0.55)

**Output:**

```json
{
  "generated_at": "2026-06-18T01:33:53Z",
  "mapped_incidents_count": 42,
  "unmapped_incidents_count": 8,
  "mapping_confidence_mix": {"high": 29, "medium": 10, "low": 3},
  "mapped": [
    {
      "incident_id": "incident_0001",
      "side_a": {
        "matched_element": { "cad_handle": "3A2B1C", "element_type": "conduit" },
        "match_score": 0.82,
        "match_confidence": "high"
      },
      "side_b": {
        "matched_element": { "cad_handle": "7F8E9D", "element_type": "beam" },
        "match_score": 0.71,
        "match_confidence": "medium"
      }
    }
  ]
}
```

---

## 7. Backend — Storage y workflow

### 7.1 Modelo de datos

```
ProjectClashJob
│  id, project_id, job_id (remoto), status, cad_fingerprint,
│  run_sequence, result (JSONB payload completo), output_dir
│
└── ProjectClashItem  [1:N]
│     id, job_id, clash_code ("incident_0001"),
│     severity, priority, report_confidence, status,
│     reviewer_decision, dwg_a, dwg_b, level_id,
│     discipline_a, discipline_b, layer_a, layer_b,
│     centroid_x_mm, centroid_y_mm,
│     bounds_minx_mm, bounds_miny_mm, bounds_maxx_mm, bounds_maxy_mm,
│     area_mm2, overlap_depth_mm, member_count, raw_json
│
└── ProjectClashEvent  [1:N por ClashItem]
      id, clash_item_id, event_type, actor,
      previous_status, new_status, decision, comment,
      related_run_id, correction_id
```

**Prioridad asignada automáticamente:**

| Severity | Priority |
|---|---|
| `critical` | P1 |
| `high` / `medium` | P2 |
| `low` | P3 |

---

### 7.2 State machine del workflow

```
detected
  │
  ├─→ needs_review
  │       │
  │       ├─→ correction_required
  │       │       │
  │       │       └─→ correction_uploaded
  │       │               │
  │       │               └─→ pending_reanalysis
  │       │                       │
  │       │                       ├─→ resolved
  │       │                       └─→ still_present
  │       │
  │       └─→ false_positive
  │
  └─→ closed  (desde cualquier estado terminal)
```

**Decisiones del revisor → cambio de estado automático:**

| Decisión | Estado resultante |
|---|---|
| `correct_dwg_a` / `correct_dwg_b` / `correct_both` | `correction_required` |
| `false_positive` | `false_positive` |
| `design_decision_needed` | `needs_review` |
| `external_discipline_required` | `needs_review` |
| `keep_pending` | sin cambio |

---

### 7.3 Servicios principales

**`clash_service.py`** — Orquestación de jobs

- `enqueue_clash_job()` — crea `ProjectClashJob`, llama al coordination service
- `get_latest_job()` — busca el job más reciente del proyecto
- `sync_job_status()` — sincroniza status desde coordination service
- `compute_cad_fingerprint()` — SHA256 de la lista de archivos CAD (detecta si re-corre sobre mismos archivos)
- `get_coordination_inventory()` — pre-flight: lista archivos CAD, blockers, configuración actual

**`clash_workflow_service.py`** — State machine + dashboard

- `ensure_ingested()` — puebla `ProjectClashItem` desde `job.result` (idempotente)
- `get_dashboard()` — agrupaciones por severity, status, discipline con filtros
- `list_clashes()` — lista paginable con filtros
- `get_clash_detail()` — detalle + eventos + correcciones
- `change_status()` — transición de estado con validación de grafo
- `record_decision()` — registra `ReviewerDecision` + auto-transición de estado

**`clash_coordinate_mapper.py`** — Transformaciones de coordenadas para el viewer

```python
@dataclass(frozen=True)
class CoordinateMapper:
    scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0
    invert_y: bool = False
    rotation_degrees: float = 0.0
    unit_factor: float = 1.0

    def map_point(x, y, z=0.0) -> {"x": float, "y": float, "z": float}
    def map_bbox(bbox) -> {"min_x", "min_y", "min_z", "max_x", "max_y", "max_z"}
```

---

## 8. API — Endpoints y respuestas

### 8.1 Clash Jobs API (`/api/projects/{project_uuid}/clash/...`)

#### `POST /clash/jobs` — Encolar detección

**Body:**
```json
{
  "profile_slug": "standard",
  "folder_uuid": "uuid-de-carpeta-opcional"
}
```

**Response:**
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "job_id": "remote-job-id",
  "status": "queued",
  "coordination_profile": "standard",
  "cad_fingerprint": "sha256hex",
  "run_sequence": 1,
  "created_at": "2026-06-18T01:33:53Z"
}
```

#### `GET /clash/jobs/latest` — Estado del último job

```json
{
  "id": "uuid",
  "status": "completed",
  "run_sequence": 1,
  "result": {
    "clashes_detected": 56,
    "severity_counts": {"critical": 27, "major": 25, "minor": 4},
    "disciplines_analyzed": ["ARQ", "EST"],
    "output_dir": "/path/to/artifacts"
  },
  "updated_at": "2026-06-18T01:45:00Z"
}
```

#### `GET /coordination/inventory` — Pre-flight

```json
{
  "cad_files": [
    {"name": "SERENA18_ELEC_P1.dxf", "discipline": "ELECTRICIDAD", "size_mb": 12.4}
  ],
  "blockers": [],
  "can_run": true,
  "warnings": ["ELEC unit factor under review"]
}
```

#### `GET /clash/jobs/latest/exports/technical.pdf`
#### `GET /clash/jobs/latest/exports/human.pdf`

Responden con `Content-Disposition: attachment; filename="Reporte Tecnico ... v01.pdf"` y bytes del PDF.

---

### 8.2 Workflow API (`/api/projects/{project_uuid}/clash-workflow/...`)

#### `GET /clash-workflow/dashboard`

**Query params:** `priority`, `severity`, `status`, `level_id`, `discipline`, `assigned_to`, `dwg`

**Response:**
```json
{
  "total": 56,
  "by_severity": {"critical": 27, "major": 25, "minor": 4},
  "by_status": {"detected": 40, "needs_review": 10, "resolved": 6},
  "by_discipline_pair": {"ARQ×EST": 12, "ARQ×ELEC": 20},
  "clashes": [
    {
      "id": "uuid",
      "clash_code": "incident_0001",
      "severity": "critical",
      "priority": "P1",
      "status": "detected",
      "discipline_a": "ARQUITECTURA",
      "discipline_b": "ESTRUCTURA",
      "level_id": "NPT_P1",
      "centroid_x_mm": 48200.0,
      "centroid_y_mm": 74700.0,
      "area_mm2": 45000.0,
      "member_count": 5,
      "assigned_to": null
    }
  ]
}
```

#### `GET /clash-workflow/clashes/{item_id}` — Detalle

```json
{
  "id": "uuid",
  "clash_code": "incident_0001",
  "severity": "critical",
  "status": "needs_review",
  "dwg_a": "SERENA18_ARQ_P1.dxf",
  "dwg_b": "SERENA18_EST_P1.dxf",
  "layer_a": "A-WALL",
  "layer_b": "S-BEAM",
  "centroid_x_mm": 48200.0,
  "centroid_y_mm": 74700.0,
  "overlap_depth_mm": 120.0,
  "autocad_zoom_command": "ZOOM W 47800,74300 48600,75100",
  "events": [
    {
      "event_type": "ingested",
      "actor": "system",
      "created_at": "2026-06-18T01:40:00Z"
    },
    {
      "event_type": "status_change",
      "actor": "revisor@dupla.cl",
      "previous_status": "detected",
      "new_status": "needs_review",
      "comment": "Verificar con EST"
    }
  ],
  "corrections": []
}
```

#### `POST /clash-workflow/clashes/{item_id}/status`

```json
{ "new_status": "needs_review", "comment": "Revisado en sitio" }
```

#### `POST /clash-workflow/clashes/{item_id}/decision`

```json
{ "decision": "correct_dwg_a", "comment": "Viga se mueve 15cm" }
```

#### `POST /clash-workflow/clashes/{item_id}/corrections`

```json
{
  "target": "dwg_a",
  "revision_name": "REV-03",
  "filename": "SERENA18_EST_P1_rev03.dxf",
  "content": "<base64 bytes>"
}
```

---

### 8.3 Viewer API (`/api/projects/{project_id}/viewer/...`)

#### `GET /viewer/config`

```json
{
  "project_id": "uuid",
  "urn": "urn:adsk.objects:os.object:...",
  "default_viewable_guid": "guid-del-viewable",
  "viewer_mode": "2d",
  "units": "mm",
  "default_coordinate_space": "world",
  "clashes_url": "/api/projects/uuid/viewer/clashes",
  "token_url": "/api/aps/token",
  "manifest_url": "/api/aps/manifest/uuid",
  "viewables": [
    {"guid": "guid", "name": "Planta Nivel 1", "role": "2d"}
  ],
  "warnings": []
}
```

#### `GET /viewer/clashes`

**Query params:** `severity`, `discipline`, `include_resolved` (bool)

**Response — `ClashViewerResponse`:**

```json
{
  "project_id": "uuid",
  "coordinate_space": "world",
  "units": "mm",
  "source": "motor_dupla",
  "coordinate_settings_applied": {
    "scale": 1.0,
    "offset_x": -160120.0,
    "offset_y": -626236.0,
    "offset_z": 0.0,
    "invert_y": false,
    "rotation_degrees": 0.0,
    "unit_factor": 1.0
  },
  "summary": {"total": 56, "critical": 27, "high": 25, "medium": 4, "low": 0},
  "clashes": [
    {
      "id": "clash-uuid",
      "source_clash_id": "incident_0001",
      "discipline_a": "ELECTRICIDAD",
      "discipline_b": "ESTRUCTURA",
      "layer_a": "I-CONDUIT",
      "layer_b": "S-BEAM",
      "clash_type": "hard_2d",
      "confidence": "medium",
      "severity": "critical",
      "status": "open",
      "model_bbox_mm": {
        "min_x": 48000, "min_y": 74500, "min_z": 2400,
        "max_x": 48400, "max_y": 74900, "max_z": 2520
      },
      "world_bbox_mm": {
        "min_x": -112120, "min_y": -551736, "min_z": 2400,
        "max_x": -111720, "max_y": -551336, "max_z": 2520
      },
      "viewer_bbox": { "min_x": -112.12, "min_y": -551.74, "min_z": 2.4,
                       "max_x": -111.72, "max_y": -551.34, "max_z": 2.52 },
      "center": {"x": -111.92, "y": -551.54, "z": 2.46},
      "mapper_applied": true,
      "description": "ELECTRICIDAD vs ESTRUCTURA en NPT_P1",
      "recommendation": "Revisar trayectoria de conducto"
    }
  ]
}
```

#### `GET /viewer/coordinate-settings` / `PUT /viewer/coordinate-settings`

Persiste el transform de coordenadas modelo → viewer (scale, offset, rotation, invert_y, unit_factor).

#### `GET /viewer/clashes/{clash_id}/mapping-candidates`

Retorna candidatos de dbId APS para highlighting en el viewer.  
Actualmente retorna listas vacías (TBD cuando APS properties estén disponibles).

---

## 9. Diagrama de estados del workflow

```
  ┌─────────────┐
  │  detected   │◄── ingestión automática desde job
  └──────┬──────┘
         │ revisor lo toma
         ▼
  ┌──────────────┐
  │ needs_review │
  └──────┬───────┘
         │ decision: correct_dwg_*
         ▼
  ┌────────────────────┐
  │ correction_required│
  └──────────┬─────────┘
             │ DWG subido
             ▼
  ┌────────────────────┐
  │correction_uploaded │
  └──────────┬─────────┘
             │ request reanalysis
             ▼
  ┌────────────────────┐
  │ pending_reanalysis │
  └──────────┬─────────┘
         ┌───┴───────────────┐
         ▼                   ▼
    ┌──────────┐        ┌──────────────┐
    │ resolved │        │ still_present│
    └──────────┘        └──────────────┘

  (desde needs_review)
  │ decision: false_positive
  ▼
  ┌───────────────┐
  │ false_positive│
  └───────────────┘

  (desde cualquier estado terminal)
  ▼
  ┌────────┐
  │ closed │
  └────────┘
```

---

## 10. Mapa de archivos

### Motor

| Archivo | Responsabilidad |
|---|---|
| `core/clash.py` | Detección 2.5D cross-discipline |
| `core/intra_clash.py` | Detección intra-discipline por capas |
| `core/clash_element_mapper.py` | Mapeo incidente → entidad CAD |
| `core/models_25d.py` | Modelos Pydantic (Element25D, ZInterval, ClashConflict) |
| `core/frame_alignment.py` | Alineación multi-disciplina (Layer A/B/C) |
| `core/control_points.py` | Entrada y validación de control points manuales |
| `core/geometry_normalizer.py` | Orquesta inferencia de unidades + limpieza |
| `core/geometry_cleaner.py` | Separación cluster principal / strays |
| `core/units.py` | Conversiones y reconciliación de unidades |
| `core/nasas_paths.py` | Offsets por-archivo (deshabilitado en common frame) |
| `core/registry.py` | Level registry (offsets NPT por proyecto) |
| `selection/source_selection.py` | Filtrado de archivos NASAS |
| `selection/coordinate_audit.py` | Auditoría de elegibilidad y bandas de coordenadas |
| `selection/fast_compare.py` | Pre-matching documental entre pares |
| `selection/level_inference.py` | Inferencia de nivel desde nombre de archivo |
| `semantic/semantic_elements.py` | Clasificación semántica CAD |
| `semantic/vision_validator.py` | Validación por vision model (opcional) |
| `extraction/from_dwg_accore.py` | Extracción vía AutoCAD Core Console |
| `extraction/from_dwg_ezdxf.py` | Extracción vía ezdxf |
| `extraction/from_dwg_com.py` | Extracción vía COM |
| `extraction/from_dwg_aps.py` | Extracción desde fragmentos APS |
| `extraction/from_aps_viewer_dump.py` | Extracción desde dump APS JSON |
| `extraction/from_pdf_vector.py` | Extracción desde PDF vectorial |
| `extraction/from_raster_image.py` | Extracción desde imagen raster |
| `reporting/ga_fo_08.py` | PDF institucional GA-FO-08 |
| `reporting/plan_render.py` | Render PNG de plano con clashes |
| `scripts/run_nasas09_project_coordination.py` | Orquestador principal del pipeline |
| `scripts/run_arq_intra_clash.py` | Pipeline intra-clash ARQ + PDF |

### Backend

| Archivo | Responsabilidad |
|---|---|
| `routes/clash.py` | Endpoints de jobs, inventory, exports |
| `routes/clash_workflow.py` | Endpoints de workflow (dashboard, decisiones, tiles) |
| `routes/clash_viewer.py` | Endpoints del viewer APS |
| `routes/aps_viewer.py` | Token APS, manifest, translate |
| `services/clash_service.py` | Orquestación de jobs, fingerprint, sync |
| `services/clash_workflow_service.py` | State machine, ingesta, dashboard |
| `services/clash_coordinate_mapper.py` | Transform modelo → viewer |
| `services/clash_element_mapping_service.py` | dbId resolution APS (TBD) |
| `services/clash_viewer_adapter.py` | Construye ClashViewerResponse |
| `services/clash_export_service.py` | PDF/Excel exports (técnico, humano, final) |
| `services/clash_reports/` | Generadores de PDF por tipo |
| `models/project_clash_job.py` | ORM: job de ejecución |
| `models/project_clash_item.py` | ORM: incidente individual |
| `models/project_clash_event.py` | ORM: auditoría de eventos |
| `models/project_clash_correction.py` | ORM: DWGs corregidos |
| `models/project_viewer_coordinate_settings.py` | ORM: settings de coordenadas |
| `domain/clash_coordinates.py` | ClashLocation (centroid, bounds, autocad command) |
| `domain/clash_workflow_enums.py` | ClashStatus, ReviewerDecision, transitions |
| `schemas/clash_viewer.py` | ViewerClash, ClashViewerResponse, ViewerConfigResponse |
