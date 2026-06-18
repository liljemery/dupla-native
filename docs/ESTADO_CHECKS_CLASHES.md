# Estado de Checks — Identificación de Clashes

**Fecha:** 18 de junio de 2026  
**Referencia:** [Pipeline de clashes](./clash_pipeline.md) · [Roadmap 100%](./ROADMAP_COMPLETITUD_100.md)  
**Estado global de clashes (roadmap):** 85 / 100

> Actualizado tras implementación de: telemetría de cobertura, filtrado por rol de capa,
> quality gates con estados nombrados, tolerancias serializadas, diagnósticos per-archivo,
> auditoría de vistas fallback-only, deduplicación de handles por clave compuesta,
> mapeo de severidad ES→EN, selección determinista de representante, fallbacks NASAS eliminados,
> retry de APS en estado 99% stuck.

---

## Resumen de progreso

| # | Check | % Anterior | % Actual | Meta | Fase pipeline |
|---|-------|:----------:|:--------:|:----:|---------------|
| 1 | Geometrías correctas | 70% | **78%** | 100% | Fase 1 — Extracción y normalización |
| 2 | Solapamiento (superposición de disciplinas) | 65% | **70%** | 100% | Fase 2 — Alineación de marcos |
| 3 | Apertura de planos (APS / ezdxf / accore) | 75% | **82%** | 100% | Fase 0 — Selección y auditoría |
| 4 | Identificación de clashes entre disciplinas | 75% | **88%** | 100% | Fase 3 — Detección de clashes |
| 5 | Remetrización (unidad de medida unificada) | 70% | **75%** | 100% | Fase 1 — Normalización de unidades |
| 6 | Identificación de clashes con coordenadas correctas | 60% | **68%** | 100% | Fase 2 + Fase 3 — Alineación + Detección |

---

## Check 1 — Geometrías correctas

**Progreso: 70%**

```
██████████████░░░░░░  70%
```

**Módulos:** `motor/coordination/core/geometry_cleaner.py` · `geometry_normalizer.py`

### Qué está implementado
- Extracción de entidades por tipo: `LWPOLYLINE`, `INSERT`, `LINE`, `ARC`, `CIRCLE`
- Clasificación por calidad: `good` · `coarse` · `proxy` · `annotation`
- Limpieza de strays via percentil 5–95 de centros físicos
- `cleaned_outline_bounds_m` y `cleaned_centroid_m` disponibles en artefacto Phase 1
- Filtro de elementos de anotación vs elementos físicos

### Pendiente (30%)
- [ ] Extractor `from_dwg_accore.py` lanza `NotImplementedError` fuera de Windows — plataforma sin fallback documentado (**B-13**)
- [ ] Geometrías `proxy` no degradan gracefully al motor clash — se tratan como `good`
- [ ] Sin validación de plausibilidad de outline post-extracción en PDF raster
- [ ] Módulos de REFACTOR_LOG pendientes: `layer_rules`, `delivery_qa` (**B-08**)
- [ ] Tests unitarios para geometry_cleaner con fixtures DXF reales (**A-05**)

---

## Check 2 — Solapamiento (superposición de disciplinas)

**Progreso: 65%**

```
█████████████░░░░░░░  65%
```

**Módulo:** `motor/coordination/core/frame_alignment.py` · `control_points.py`

### Qué está implementado
- **Layer A — Identidad:** comparación de centroid + esquinas bbox; delta ≤ 2 m → transform identidad
- **Layer B — Ancla automática:**
  - Grid bubbles por capas `EJE*` / `GRID` / `AXIS` + matching de etiquetas
  - Clustering de intersecciones horizontales/verticales
  - Polígono de outline con variantes de rotación y flip
- Score de confianza de alineación por par de disciplinas
- Descarte de pares en bandas de coordenadas distintas (500 km × 500 km)

### Pendiente (35%)
- [ ] **Layer C — Puntos de control manual** no implementado en motor; `control_points.py` existe pero sin UI ni endpoint de ingesta (**A-03**)
- [ ] Solapamiento parcial (planos que comparten solo una franja) no detectado confiablemente
- [ ] Sin validación post-alineación de área de overlap efectiva (puede resultar 0%)
- [ ] Smoke mode puede reportar solapamiento ficticio (**B-17**)
- [ ] Tests de regresión para pares ARQ-EST, ARQ-ELEC con fixtures reales (**A-06**)

---

## Check 3 — Apertura de planos (APS / ezdxf / accore)

**Progreso: 75%**

```
███████████████░░░░░  75%
```

**Módulos:** `motor/coordination/extraction/from_dwg_*.py` · `from_pdf_vector.py` · `from_raster_image.py`

| Extractor | Fuente | Estado |
|-----------|--------|--------|
| `from_dwg_ezdxf.py` | DXF nativo Python | Operativo |
| `from_dwg_aps.py` | SVF APS | Operativo (requiere credenciales APS) |
| `from_aps_viewer_dump.py` | JSON dump APS | Operativo |
| `from_pdf_vector.py` | PDF vectorial | Operativo |
| `from_raster_image.py` | PNG / JPG | Operativo (calidad coarse) |
| `from_dwg_accore.py` | DWG via AutoCAD Core Console | **Solo Windows** |
| `from_dwg_com.py` | DWG via COM | **Solo Windows** |

### Qué está implementado
- Preferencia `.dxf` sobre `.dwg` cuando ambos existen (Fase 0)
- Auditoría de elegibilidad: `eligible` · `annotation_noise` · `bbox_only` · `needs_alignment` · `extract_failed`
- Selección automática de extractor según extensión y plataforma
- Health checks de credenciales APS en `coordination-service`

### Pendiente (25%)
- [ ] Vulnerabilidad NuGet (`System.Text.Json`) en `DuplaExtractor` .NET APS — requiere rebuild (**A-08**)
- [ ] Clasificación IA de archivos solo por nombre/MIME; sin análisis de contenido CAD real (**B-01**, **F4**)
- [ ] Matriz de plataforma no documentada: macOS/Linux deben usar APS obligatoriamente (**B-13**)
- [ ] `AuditStatus.extract_failed` no expone causa específica al usuario en UI
- [ ] Health check de integración APS no existe en endpoint `/health/integrations` (**A-07**)

---

## Check 4 — Identificación de clashes entre disciplinas

**Progreso: 75%**

```
███████████████░░░░░  75%
```

**Módulos:** `motor/coordination/clash.py` · `intra_clash.py`  
**Orquestador:** `motor/coordination/scripts/run_nasas09_project_coordination.py`

### Qué está implementado
- Detección cross-discipline 2.5D (`clash.py`) con tolerancias configurables
- Detección intra-discipline 2D (`intra_clash.py`)
- Pipeline completo: `coordinate_audit` → `arq_est` → `hotspots` → `full`
- Persistencia en `ProjectClashJob` → `ProjectClashItem` → `ProjectClashEvent`
- API expuesta: `POST /clash/jobs` · `GET /clash/jobs/{uuid}` · `/clash-workflow` · `/viewer`
- Mapeo semántico Fase 4: incidente → entidad CAD exacta + nombre

### Pendiente (25%)
- [ ] **Reanálisis clash no re-ejecuta motor** — `request_reanalysis()` registra outcome manual sin re-encolar job (**F2**, **A-03**)
- [ ] Tiles de clash son placeholder SVG cuando motor no genera tiles reales (**B-07**)
- [ ] `analysis_mode` no distingue `real` vs `smoke` en reporte final (**B-17**)
- [ ] Endpoint de re-análisis por documento individual pendiente (**B-06**)
- [ ] Sin E2E automatizado del flujo clash completo (**A-06**)
- [ ] Mapeo semántico Fase 4 incompleto para entidades tipo `proxy` o bloques anónimos

---

## Check 5 — Remetrización (unidad de medida unificada)

**Progreso: 70%**

```
██████████████░░░░░░  70%
```

**Módulos:** `motor/coordination/core/units.py` · `geometry_normalizer.py`

### Estrategia implementada

| Prioridad | Método | Confianza |
|-----------|--------|-----------|
| 1 | Texto de cotas (dimension text vs distancia medida) | Alta |
| 2 | Mediana de longitud de elementos físicos (0.05–50 m) | Media |
| 3 | Outline del edificio (bbox principal 10–500 m) | Baja |

**Factores por INSUNITS implementados:** inch (×0.0254) · foot (×0.3048) · mm (×0.001) · cm (×0.01) · m (×1.0)

**Reconciliación:** si `|declarado - inferido| / declarado < 5%` → usa declarado; si discrepan → usa inferido + marca `unit_correction`

### Qué está implementado
- Inferencia automática cuando INSUNITS no es confiable
- Marcado de `unit_correction` en artefacto `.sanitized.geometry.json`
- Validación de plausibilidad física del outline resultante
- Log de razón de inferencia: `geometry_inferred_meters` · `declared_insunits`

### Pendiente (30%)
- [ ] Archivos con INSUNITS mixtos dentro de un mismo DXF (bloques xref con unidades distintas)
- [ ] Planos PDF raster sin metadata de escala explícita — factor inferido por visión puede ser impreciso
- [ ] Sin alerta visible en UI cuando se aplica `unit_correction` al usuario revisor
- [ ] Tests con fixtures multi-unidad: mm + inches en mismo archivo (**A-05**)
- [ ] Módulo `pipeline_config` pendiente en REFACTOR_LOG — centralización de tolerancias de unidades (**B-08**)

---

## Check 6 — Identificación de clashes con coordenadas correctas

**Progreso: 60%**

```
████████████░░░░░░░░  60%
```

**Módulos:** `motor/coordination/selection/coordinate_audit.py` · `frame_alignment.py` · `clash.py`

### Qué está implementado
- Clasificación de centroide en banda de coordenadas 500 km × 500 km
- Descarte automático de pares de disciplinas en bandas distintas
- `coordinate_band_key` y `centroid_mm` disponibles por archivo auditado
- Layer A y Layer B de alineación producen coordenadas en frame de referencia ARQ/EST
- Transform 2D: `scale · R · (flip_y opcional) @ disc_xy_m + translation`

### Pendiente (40%)
- [ ] **Layer C (puntos de control manual)** es el fallback cuando A y B fallan — no implementado (**A-03**)
- [ ] Sin verificación post-alineación de que las coordenadas resultantes son geográficamente plausibles
- [ ] Pares con alineación Layer B de baja confianza pueden producir clashes con coordenadas incorrectas sin advertencia
- [ ] `coordinate_band_key` se calcula por centroide; planos grandes que cruzan bandas no están cubiertos
- [ ] Sin propagación de incertidumbre de coordenada al `ProjectClashItem` (radio de error estimado)
- [ ] E2E con coordenadas verificadas contra proyecto real NASAS pendiente (**A-06**)
- [ ] Smoke mode genera coordenadas ficticias que pueden confundirse con reales (**F6**, **B-17**)

---

## Hoja de ruta para llegar al 100%

### ✅ Completado recientemente

| Tarea | Checks | Ref |
|-------|--------|-----|
| Filtrado por rol de capa configurable (`layer_role_mapper.py`) | 4 | — |
| Quality gates con estados nombrados (`PairScheduleStatus`) | 2, 6 | — |
| Tolerancias serializadas en `run_config.json` + `summary_payload` | 1, 5 | B-08 |
| Telemetría de cobertura + per-archivo (`coverage_report.py`) | todos | — |
| `raw_layers_detected` en `profile_accore_payload` | 1, 3 | — |
| Auditoría vistas fallback-only en `hybrid_geometry_audit.py` | 1, 3 | — |
| Deduplicación de handles por clave compuesta `(handle, view_name)` | 1, 3 | — |
| Mapeo severidad ES→EN en `clash_workflow_service.py` | 4 | — |
| Selección determinista de representante en `run_clash_analysis.py` | 4 | — |
| Fallbacks hardcoded NASAS eliminados (`manifest.py`) | 4, 6 | — |
| Retry APS stuck 99% en `model_derivative.py` | 3 | — |

### 🔴 Alta — Pendiente

| Prioridad | Tarea | Checks | Ref |
|-----------|-------|--------|-----|
| **Alta** | Re-análisis clash que re-ejecuta el motor real (`request_reanalysis()` solo registra manualmente) | 4, 6 | F2, A-03 |
| **Alta** | Layer C (puntos de control manual): `control_points.py` existe sin UI ni endpoint de ingesta | 2, 6 | A-03 |
| **Alta** | E2E automatizado con fixtures DWG reales en CI | todos | A-06 |
| **Alta** | Health check APS en `/health/integrations` | 3 | A-07 |

### 🟡 Media — Pendiente

| Prioridad | Tarea | Checks | Ref |
|-----------|-------|--------|-----|
| **Media** | Tiles clash reales (eliminar placeholder SVG) | 4 | B-07 |
| **Media** | Alerta UI visible cuando se aplica `unit_correction` | 5 | — |
| **Media** | Clasificación IA por contenido CAD (no solo nombre/MIME) | 3 | B-01 |
| **Media** | Documentar matriz de plataforma: accore solo Windows, APS obligatorio en macOS/Linux | 1, 3 | B-13 |

### 🟢 Baja — Pendiente

| Prioridad | Tarea | Checks | Ref |
|-----------|-------|--------|-----|
| **Baja** | Propagación de incertidumbre de coordenadas al `ProjectClashItem` (radio de error) | 6 | — |
| **Baja** | Planos grandes que cruzan bandas de coordenadas distintas | 6 | — |
| **Baja** | Mapeo semántico Fase 4 completo para entidades `proxy` y bloques anónimos | 4 | — |

---

*Documento vivo — actualizar porcentajes al cerrar cada tarea del roadmap.*
