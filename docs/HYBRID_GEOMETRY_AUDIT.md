# Hybrid Geometry Audit

Fecha: 18 de junio de 2026

Esta guia define como operar la auditoria del pipeline hibrido DXF + APS usado por el flujo de clashes. El objetivo del audit es distinguir una corrida geometricamente confiable de una corrida que produjo artefactos, pero con vistas debiles o dependientes de fallback.

## Artefactos

El orquestador hibrido escribe estos archivos bajo `hybrid_geometry/`:

| Archivo | Uso |
| --- | --- |
| `plan_geometry.hybrid.json` | Geometria final en `sheet_paper_units` para visualizacion, checklist y reportes. |
| `hybrid_geometry_manifest.json` | Manifiesto tecnico con fuentes, matching, alineaciones y resumen de registros. |
| `hybrid_geometry_audit.json` | Resultado machine-readable de calidad: `ok`, `warn` o `fail`. |
| `hybrid_geometry_audit.md` | Resumen humano para soporte, QA y revision manual. |

El wrapper expone los paths como artifacts:

| Artifact | Valor |
| --- | --- |
| `plan_geometry_hybrid` | Path a `plan_geometry.hybrid.json`. |
| `hybrid_geometry_manifest` | Path a `hybrid_geometry_manifest.json`. |
| `hybrid_geometry_audit` | Path a `hybrid_geometry_audit.json`. |
| `hybrid_geometry_audit_md` | Path a `hybrid_geometry_audit.md`. |
| `hybrid_geometry_audit_status` | `ok`, `warn` o `fail`. |
| `hybrid_geometry_audit_gate` | JSON con `mode`, `status` y `blocked`. |

El `StructuralAnalysisReport` tambien expone un campo `geometry_audit` para consumo directo de UI/API:

```json
{
  "geometry_audit": {
    "status": "warn",
    "summary": {
      "views_warn": 1,
      "issues_warn": 1
    },
    "gate": {
      "mode": "report_only",
      "status": "warn",
      "blocked": false
    }
  }
}
```

Cuando no hay geometria hibrida disponible, `geometry_audit` queda en `null`.

## Estados

| Estado | Significado | Uso recomendado |
| --- | --- | --- |
| `ok` | Las vistas alinean con suficientes pares/inliers y sin ratios criticos. | Entregar sin advertencia especial. |
| `warn` | La corrida es usable, pero hay vistas con baja confianza o mucho fallback/coarse. | Entregar con advertencia visible y revision sugerida. |
| `fail` | Hay vistas insuficientes o metricas por encima de umbrales criticos. | No usar como garantia geometrica sin revision manual. |

## Gate de produccion

La variable `COORDINATION_HYBRID_GEOMETRY_AUDIT_GATE` controla si el audit bloquea la corrida.

| Valor | Comportamiento |
| --- | --- |
| unset / `report_only` | No bloquea. Solo reporta audit y artifacts. Valor por defecto. |
| `fail` | Bloquea si `hybrid_geometry_audit.status == "fail"` o si el audit falta (`missing`). |
| `strict` | Bloquea si el audit queda en `warn`, `fail` o falta (`missing`). |
| `off`, `false`, `0`, `no` | Equivalente a `report_only`. |

Recomendacion actual: usar `report_only` en produccion inicial. Activar `fail` solo cuando tengamos mas fixtures reales calibrados por proyecto/disciplina.

## DWG a DXF

El pipeline hibrido necesita DXF para extraer geometria fisica con `ezdxf`. Si el usuario sube DWG y no hay DXF staged, el wrapper intenta una conversion best-effort antes de omitir la geometria hibrida.

Variables:

| Variable | Uso |
| --- | --- |
| `ODA_FILE_CONVERTER` | Path explicito al ejecutable `ODAFileConverter`. |
| `ODA_DXF_VERSION` | Version DXF de salida. Default: `ACAD2018`. |
| `COORDINATION_DWG_TO_DXF_TIMEOUT_SECONDS` | Timeout de conversion DWG→DXF. Default: `900`. |

En macOS local tambien se intenta `/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter`. Si no hay conversor disponible, la corrida no falla por defecto; se registra skip y el gate reporta `missing` si se evalua en modo bloqueante.

## Codigos de issues

| Codigo | Severidad tipica | Significado |
| --- | --- | --- |
| `alignment_insufficient` | `fail` | La vista tiene menos pares que el minimo para resolver transform confiable. |
| `alignment_too_few_pairs` | `fail` | La vista reporta `ok`, pero tiene menos pares que el minimo configurado. |
| `alignment_too_few_inliers` | `fail` | La vista tiene muy pocos inliers utiles. |
| `alignment_low_inliers` | `warn` | La vista supera el minimo, pero queda bajo el recomendado. |
| `alignment_high_outlier_ratio` | `warn` o `fail` | Muchos pares DXF/APS fueron rechazados por RANSAC. |
| `alignment_high_rms_error` | `warn` o `fail` | Error RMS de alineacion alto en unidades de hoja. |
| `alignment_high_max_error` | `warn` o `fail` | Error maximo de alineacion alto en unidades de hoja. |
| `hybrid_no_records` | `fail` | No se produjo geometria hibrida. |
| `hybrid_high_fallback_ratio` | `warn` o `fail` | Demasiados registros vienen de fallback APS en vez de DXF transformado. |
| `hybrid_high_coarse_ratio` | `warn` o `fail` | Demasiados registros tienen calidad `coarse`. |

## Umbrales actuales

| Umbral | Valor |
| --- | ---: |
| `min_alignment_pairs` | 3 |
| `min_alignment_inliers` | 3 |
| `warn_low_inliers` | 10 |
| `warn_outlier_ratio` | 0.50 |
| `fail_outlier_ratio` | 0.85 |
| `warn_rms_error_sheet` | 0.35 |
| `fail_rms_error_sheet` | 0.75 |
| `warn_max_error_sheet` | 1.0 |
| `fail_max_error_sheet` | 2.0 |
| `warn_fallback_ratio` | 0.50 |
| `fail_fallback_ratio` | 0.80 |
| `warn_coarse_ratio` | 0.50 |
| `fail_coarse_ratio` | 0.80 |

Estos umbrales son deliberadamente conservadores. Deben recalibrarse con mas corridas reales antes de activar `strict`.

## Estado real LAS NASAS

La corrida real de LAS NASAS produjo:

| Metrica | Valor |
| --- | ---: |
| Fuentes | 2 |
| Vistas ok | 10 |
| Vistas warn | 7 |
| Vistas fail | 3 |
| Registros totales | 22,988 |
| Registros good | 9,741 |
| Registros coarse | 13,247 |

El status global es `fail` por:

- `A-1.5.1`: alineacion insuficiente.
- `E-1`: alineacion insuficiente.
- `E-2`: outlier ratio critico.

## Limites actuales

El pipeline hibrido no reemplaza todavia la deteccion HARD de clashes. La geometria esta en `sheet_paper_units`; el motor HARD actual espera `Element25D` con unidades en mm, nivel/Z y footprints en marco de proyecto. Por eso el uso actual recomendado es:

- visualizacion,
- conteo/enriquecimiento de documentos,
- checklist/reporte,
- trazabilidad de geometria,
- QA de alineacion.

Para usarlo como motor de deteccion HARD faltan conversion estable a proyecto/mm, asignacion de nivel/Z y validacion E2E con fixtures reales.
