# Refactor Log — coordination/ package

Fecha: 2026-05-10
Rama: rerefactor

## Archivos movidos

### core → coordination/core/

| Origen | Destino |
|--------|---------|
| `core/coordination/clash.py` | `coordination/core/clash.py` |
| `core/coordination/clash_element_mapper.py` | `coordination/core/clash_element_mapper.py` |
| `core/coordination/models_25d.py` | `coordination/core/models_25d.py` |
| `core/coordination/units.py` | `coordination/core/units.py` |
| `core/coordination/registry.py` | `coordination/core/registry.py` |
| `core/coordination/nasas_paths.py` | `coordination/core/nasas_paths.py` |

### core → coordination/extraction/

| Origen | Destino |
|--------|---------|
| `core/coordination/from_dwg_accore.py` | `coordination/extraction/from_dwg_accore.py` |
| `core/coordination/from_dwg_aps.py` | `coordination/extraction/from_dwg_aps.py` |
| `core/coordination/from_dwg_com.py` | `coordination/extraction/from_dwg_com.py` |
| `core/coordination/from_dwg_ezdxf.py` | `coordination/extraction/from_dwg_ezdxf.py` |
| `core/coordination/from_pdf_vector.py` | `coordination/extraction/from_pdf_vector.py` |
| `core/coordination/from_raster_image.py` | `coordination/extraction/from_raster_image.py` |
| `core/coordination/from_autodesk_properties.py` | `coordination/extraction/from_autodesk_properties.py` |
| `core/coordination/from_aps_viewer_dump.py` | `coordination/extraction/from_aps_viewer_dump.py` |
| `core/coordination/aps_cache.py` | `coordination/extraction/aps_cache.py` |

### core → coordination/selection/

| Origen | Destino |
|--------|---------|
| `core/coordination/source_selection.py` | `coordination/selection/source_selection.py` |
| `core/coordination/fast_compare.py` | `coordination/selection/fast_compare.py` |
| `core/coordination/coordinate_audit.py` | `coordination/selection/coordinate_audit.py` |
| `core/coordination/level_inference.py` | `coordination/selection/level_inference.py` |

### core → coordination/semantic/

| Origen | Destino |
|--------|---------|
| `core/coordination/semantic_elements.py` | `coordination/semantic/semantic_elements.py` |

### core → coordination/reporting/

| Origen | Destino |
|--------|---------|
| `core/coordination/reporting.py` | `coordination/reporting/reporting.py` |

### scripts → coordination/scripts/

| Origen | Destino |
|--------|---------|
| `scripts/run_nasas09_project_coordination.py` | `coordination/scripts/run_nasas09_project_coordination.py` |
| `scripts/run_nasas_coordination_autodesk_raw.py` | `coordination/scripts/run_nasas_coordination_autodesk_raw.py` |
| `scripts/render_coordination_report.py` | `coordination/scripts/render_coordination_report.py` |
| `scripts/render_coordination_delivery_pack.py` | `coordination/scripts/render_coordination_delivery_pack.py` |
| `scripts/render_coordination_portfolio_pack.py` | `coordination/scripts/render_coordination_portfolio_pack.py` |
| `scripts/demo_coordination_nasas.py` | `coordination/scripts/demo_coordination_nasas.py` |

### tests → coordination/tests/

| Origen | Destino |
|--------|---------|
| `tests/test_coordination.py` | `coordination/tests/test_coordination.py` |
| `tests/test_clash_element_mapper.py` | `coordination/tests/test_clash_element_mapper.py` |
| `tests/test_coordinate_audit.py` | `coordination/tests/test_coordinate_audit.py` |
| `tests/test_fast_compare.py` | `coordination/tests/test_fast_compare.py` |
| `tests/test_source_selection.py` | `coordination/tests/test_source_selection.py` |
| `tests/test_from_autodesk_properties.py` | `coordination/tests/test_from_autodesk_properties.py` |
| `tests/test_pdf_vector_extractor.py` | `coordination/tests/test_pdf_vector_extractor.py` |
| `tests/test_dwg_accore_parser.py` | `coordination/tests/test_dwg_accore_parser.py` |
| `tests/test_dwg_com_extractor.py` | `coordination/tests/test_dwg_com_extractor.py` |
| `tests/test_dxf_support.py` | `coordination/tests/test_dxf_support.py` |
| `tests/test_aps_viewer_dump.py` | `coordination/tests/test_aps_viewer_dump.py` |
| `tests/test_level_inference.py` | `coordination/tests/test_level_inference.py` |
| `tests/test_coordination_reporting.py` | `coordination/tests/test_coordination_reporting.py` |
| `tests/test_coordination_reporting_semantic.py` | `coordination/tests/test_coordination_reporting_semantic.py` |
| `tests/test_semantic_elements.py` | `coordination/tests/test_semantic_elements.py` |
| `tests/test_serena_support.py` | `coordination/tests/test_serena_support.py` |

### raíz → coordination/docs/

| Origen | Destino |
|--------|---------|
| `GUIA_FLUJO_CLASHES.md` | `coordination/docs/GUIA_FLUJO_CLASHES.md` |
| `PLANTILLA_INFORME_COORDINACION.md` | `coordination/docs/PLANTILLA_INFORME_COORDINACION.md` |

---

## Imports actualizados por archivo

### coordination/core/
- **clash.py**: `core.coordination.models_25d` → `coordination.core.models_25d`; `core.coordination.registry` → `coordination.core.registry`
- **clash_element_mapper.py**: `core.coordination.semantic_elements` → `coordination.semantic.semantic_elements`
- **models_25d.py**: `core.coordination.units` → `coordination.core.units`
- **nasas_paths.py**: `core.coordination.models_25d` → `coordination.core.models_25d`
- **registry.py**: `core.coordination.models_25d` → `coordination.core.models_25d`
- **units.py**: sin imports internos, sin cambios
- **clash_element_mapper.py**: sin imports internos adicionales

### coordination/extraction/
- **from_dwg_accore.py**: `core.coordination.from_dwg_com` → `coordination.extraction.from_dwg_com`; `core.coordination.models_25d` → `coordination.core.models_25d`; `core.coordination.nasas_paths` → `coordination.core.nasas_paths`
- **from_dwg_aps.py**: todos `core.coordination.*` → rutas correctas en `coordination.*`
- **from_dwg_com.py**: `core.coordination.models_25d` → `coordination.core.models_25d`; `core.coordination.nasas_paths` → `coordination.core.nasas_paths`
- **from_dwg_ezdxf.py**: `core.coordination.models_25d` → `coordination.core.models_25d`; `core.coordination.nasas_paths` → `coordination.core.nasas_paths`
- **from_pdf_vector.py**: `core.coordination.level_inference` → `coordination.selection.level_inference`; resto a `coordination.core.*`
- **from_raster_image.py**: mismo patrón que from_pdf_vector
- **from_autodesk_properties.py**: `core.coordination.models_25d` → `coordination.core.models_25d`; `core.coordination.units` → `coordination.core.units`
- **from_aps_viewer_dump.py**: todos los `core.coordination.*` actualizados a sus nuevas rutas
- **aps_cache.py**: sin imports internos, sin cambios

### coordination/selection/
- **coordinate_audit.py**: `core.coordination.fast_compare` → `coordination.selection.fast_compare`; `core.coordination.models_25d` → `coordination.core.models_25d`
- **fast_compare.py**: todos los 5 imports de `core.coordination.*` actualizados
- **level_inference.py**: `core.coordination.registry` → `coordination.core.registry`; `core.coordination.source_selection` → `coordination.selection.source_selection`
- **source_selection.py**: `core.coordination.registry` → `coordination.core.registry`

### coordination/semantic/
- **semantic_elements.py**: `core.coordination.models_25d` → `coordination.core.models_25d`

### coordination/reporting/
- **reporting.py**: sin imports internos de coordinación, sin cambios

### coordination/scripts/
- **run_nasas09_project_coordination.py**: todos los imports de `core.coordination.*` actualizados; `REPO_ROOT` corregido a `parents[2]`
- **run_nasas_coordination_autodesk_raw.py**: `core.coordination.*` → `coordination.*`; `REPO_ROOT` corregido
- **render_coordination_report.py**: `core.coordination.*` → `coordination.*`; `REPO_ROOT` corregido
- **render_coordination_delivery_pack.py**: `REPO_ROOT` corregido a `parents[2]`
- **render_coordination_portfolio_pack.py**: `REPO_ROOT` corregido a `parents[2]`
- **demo_coordination_nasas.py**: `core.coordination.*` → `coordination.*`; `REPO_ROOT` corregido

### coordination/tests/
- Todos los tests: `core.coordination.*` → `coordination.*` con las rutas correctas por subpaquete
- **test_fast_compare.py**: `scripts.run_nasas09_project_coordination` → `coordination.scripts.run_nasas09_project_coordination`

---

## Archivos no encontrados (TODO)

Los siguientes archivos estaban listados en la especificación del refactor pero **no existen** en el repositorio. No fueron creados:

### coordination/core/ (esperados, no existentes)
- `pipeline_config.py` — no existe en `core/coordination/`

### coordination/selection/ (esperados, no existentes)
- `layer_rules.py` — no existe en `core/coordination/`

### coordination/semantic/ (esperados, no existentes)
- `semantic_grouping.py` — no existe en `core/coordination/`
- `semantic_naming.py` — no existe en `core/coordination/`
- `mapping_payload_validation.py` — no existe en `core/coordination/`

### coordination/reporting/ (esperados, no existentes)
- `delivery_qa.py` — no existe en `core/coordination/`
- `architecture_review.py` — no existe en `core/coordination/`
- `budget_readiness.py` — no existe en `core/coordination/`

### coordination/scripts/ (esperados, no existentes)
- `run_delivery_qa.py` — no existe en `scripts/`

### coordination/tests/ (esperados, no existentes)
- `test_layer_rules.py`
- `test_mapping_payload_validation.py`
- `test_semantic_grouping.py`
- `test_semantic_naming.py`
- `test_delivery_qa.py`
- `test_architecture_review.py`
- `test_budget_readiness.py`
- `test_pipeline_config.py`
- `test_run_nasas09_registry_resolution.py`

### coordination/docs/ (esperados, no existentes)
- `COORDINATION_PIPELINE.md` — no existía en `docs/` (no hay directorio docs/)
- `PHASE_5_6_PROGRESS.md` — no existía
- `RUNBOOK_SERENA18.md` — no existía
- `docs/examples/sanitized_coordination_report_human.md` — no existía

---

## Backward compatibility

`core/coordination/__init__.py` fue reemplazado con re-exports desde `coordination.*` para que cualquier import legacy `from core.coordination import X` siga funcionando sin cambios. Ver el archivo para la lista completa.

## Verificación de imports huérfanos

Ejecutado: `grep -rn "from core.coordination|import core.coordination" . --include="*.py"` (excluyendo `core/coordination/__init__.py`)
→ **0 resultados**: ningún import huérfano fuera del archivo de backward compat.
