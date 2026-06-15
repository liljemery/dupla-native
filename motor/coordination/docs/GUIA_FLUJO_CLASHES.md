# Guia de Flujo de Clashes

## Que es este documento

Esto no es solo un resumen. Es un handoff tecnico para que otro programador entienda:

1. donde vive el sistema de clashes
2. cual es el flujo correcto de corrida
3. que aprendimos en los analisis ya ejecutados
4. como distinguir una corrida util de una corrida con ruido

El objetivo practico es evitar que alguien vuelva a correr "todo contra todo" y tome como valido un reporte que en realidad estaba mezclando entregas, niveles o sistemas de coordenadas.

## Idea fuerza

La leccion principal del workstream es esta:

- el problema de clashes no se resuelve solo con mejor deteccion
- primero hay que asegurar comparabilidad
- despues se programa el clash
- y solo al final se publican incidencias primarias

En este repo, el flujo correcto ya no es:

`extraer todo -> clash`

Ahora es:

`seleccionar fuentes -> agrupar por entrega -> validar niveles -> auditar coordenadas -> programar pares -> extraer solo lo programado -> generar primary/debug/hotspots`

## Donde vive cada pieza

| Pieza | Archivo | Rol |
| --- | --- | --- |
| Runner principal | `scripts/run_nasas09_project_coordination.py` | Entry point de corridas standard y `fast_compare` |
| Motor de clash 2.5D | `core/coordination/clash.py` | Interseccion en planta + overlap vertical + agrupacion en incidentes |
| Modelos base | `core/coordination/models_25d.py` | `Element25D`, `ZInterval`, `ProjectLevel`, `Discipline` |
| Registro de niveles | `core/coordination/registry.py` | Carga offsets, aliases y reglas de niveles |
| Seleccion de fuentes | `core/coordination/source_selection.py` | Escaneo y exclusion de overlays, revisiones derivadas, PDF images, etc. |
| Cohortes / comparabilidad | `core/coordination/fast_compare.py` | `readiness`, `cohort_id`, manifests, suppression, normalizacion |
| Audit y scheduler | `core/coordination/coordinate_audit.py` | `eligible`, `needs_alignment`, `pair_schedule` |
| Reglas NASAS de issue/disciplina | `core/coordination/nasas_paths.py` | `coordination_issue_key`, disciplina por ruta, traslaciones por archivo |
| Extractor DWG principal | `core/coordination/from_dwg_accore.py` | Geometria primaria desde AutoCAD Core Console |
| Fallback DWG | `core/coordination/from_dwg_com.py` | Bounding boxes via COM |
| Fallback DXF | `core/coordination/from_dwg_ezdxf.py` | Lectura local DXF / algunos CAD legibles |
| PDF vectorial | `core/coordination/from_pdf_vector.py` | Extraccion desde PDF cuando aplica |
| Raster | `core/coordination/from_raster_image.py` | Baja confianza; no es la ruta principal |
| Tests clave | `tests/test_coordination.py`, `tests/test_fast_compare.py` | Casos de cohorte, niveles, scheduler, primary/debug |

## Registros y configuracion por proyecto

Registros encontrados en el repo:

- NASAS: `aps_integration/NASAS 09/coordination/sample_project_levels.json`
- SERENA: `repositorios/SERENA 18/coordination/serena18_project_levels.json`

Cada registro define:

- `levels`
- `level_aliases`
- `view_level_patterns`
- `source_exclude_patterns`

Sin un registro razonable de niveles, el clash vertical pierde valor aunque la huella 2D este bien.

## Flujo real del pipeline

## 1. Scan y filtro de fuentes

`collect_coordination_media()` recorre el proyecto y aplica exclusiones duras:

- archivos fuera de `PLANOS RECIBIDOS`
- overlays tipo `solapado`
- `vision_merge_*`
- `PDF Images`
- review material que no debe entrar como fuente primaria

Esto evita comparar contra derivados visuales o material de revision que solo contamina el clash.

## 2. Inferencia de disciplina, entrega y nivel

Para cada archivo se calcula:

- disciplina, desde la ruta (`discipline_from_nasas_relative_path`)
- `issue_key`, desde fecha en el nombre o carpeta `REV. n` (`coordination_issue_key`)
- `level_id`, desde patrones del registro (`infer_level_from_view_name`)

Regla operativa:

- no mezclar entregas distintas salvo modo diagnostico
- no comparar archivos de niveles distintos como si fueran el mismo plano

## 3. Perfil `fast_compare`: readiness antes de extraer

`compute_readiness_payload()` responde una pregunta previa:

"Existe al menos una cohorte comparable con las disciplinas requeridas y niveles compartidos?"

Si la respuesta es no:

- no tiene sentido seguir a clash formal
- primero hay que armar cohorte manual o resolver alineacion

Artefacto:

- `comparison_readiness_report.json`
- `comparison_readiness_report.md`

## 4. Coordinate audit

`build_source_audit()` perfila cada archivo con:

- banda de coordenadas
- centroide / bounds
- conteo crudo de entidades
- conteo de geometria primaria
- ruido de anotaciones
- status de elegibilidad

Estados mas importantes:

- `eligible`
- `needs_alignment`
- `annotation_noise`
- `bbox_only`
- `extract_failed`

El gating duro aparece en `apply_coordinate_band_gating()`:

- si un archivo cae fuera de la banda dominante, se marca `needs_alignment`
- eso bloquea el par antes del clash

Esta fue la mejora metodologica mas importante respecto a las corridas masivas iniciales.

## 5. Pair schedule

`build_pair_schedule()` solo programa pares cuando se cumplen estas condiciones:

- misma cohorte (`cohort_id`)
- disciplinas requeridas
- ambos archivos `eligible`
- misma banda de coordenadas
- mismo `level_id`

Si esto falla, el sistema escribe el bloqueo en `pair_schedule.json` en vez de inventar clashes.

## 6. Extraccion de geometria solo para archivos programados

El runner ya no extrae todo indiscriminadamente en `fast_compare`.

Orden real para DWG:

- APS si se pide `--dwg-via-aps`
- si no, `accore`
- si falla, COM
- si es DXF o formato legible, `ezdxf`

En `fast_compare`, la meta no es volumen; la meta es comparabilidad con bajo ruido.

## 7. Normalizacion y suppression

`normalize_fast_compare_element()` agrega metadata util:

- `file_level_id`
- `cohort_id`
- `geometry_role`
- `level_assignment_source`

Tambien hace clamp cuando la Z o el espesor vienen absurdos para un run 2.5D:

- si la cota esta fuera del rango esperado, fuerza una envolvente simple por nivel
- el elemento queda trazable como `clamped_2d_default`

Regla importante:

- `primary` = puede entrar al reporte defendible
- `suppressed` = queda fuera del primario pero se conserva para debug

## 8. Clash primario vs clash debug

El motor real esta en `clash_pairs()`:

- interseccion de poligonos en planta
- area minima
- overlap vertical real
- nunca compara misma disciplina

En `fast_compare` hay dos salidas distintas:

### Primario

`_build_fast_compare_primary_conflicts()` solo toma:

- elementos `primary`
- misma cohorte
- mismo `file_level_id`
- disciplinas requeridas presentes

Esto es lo mas cercano a un reporte "presentable".

### Debug

`_build_fast_compare_debug_conflicts()` sirve para entender:

- cruces entre niveles
- dependencias de `bbox`
- geometria suprimida
- ruido que no debe llegar al primario

No debe venderse como clash final.

## 9. Agrupacion en incidentes

`group_conflicts_into_incidents()` agrupa conflictos vecinos por:

- par de archivos
- nivel
- celda espacial

Esto evita entregar miles de choques atomicos cuando en realidad el revisor necesita hotspots o incidencias agrupadas.

## 10. Artefactos de salida

Cuando una corrida `fast_compare` sale bien, deja este paquete:

- `summary.json`
- `comparison_readiness_report.json/md`
- `coordinate_audit.json/md`
- `pair_schedule.json`
- `primary_incidents.json/md`
- `debug_candidates.json`
- `hotspot_incidents.json/md` si hay suficientes casos
- `technical_coordination_report.md`
- `coordination_report_context.json`
- `alignment_manifest.json` si hubo alineacion manual

Lectura rapida:

- `summary.json`: estado global y metricas
- `comparison_readiness_report.md`: si habia cohorte comparable desde el inicio
- `coordinate_audit.md`: que archivos son confiables o no
- `pair_schedule.json`: que pares realmente entraron
- `primary_incidents.md`: registro defendible de incidencias primarias
- `technical_coordination_report.md`: resumen ejecutivo + lectura por perfil + prioridades
- `debug_candidates.json`: por que todavia hay ruido o supresiones

## 11. Capa de presentacion para revision real

Desde esta rama, el pipeline ya no se queda solo en listados tecnicos.
Ahora genera una capa de presentacion pensada para mesa de coordinacion:

- resumen ejecutivo
- hallazgos defendibles
- hallazgos que requieren validacion manual
- secciones por perfil:
  - arquitectura
  - electrico
  - sanitario
- separacion explicita entre:
  - incidencias primarias
  - ruido tecnico
  - hotspots
  - bloqueos de audit o schedule

La logica nueva vive en:

- `core/coordination/reporting.py`
- `scripts/render_coordination_report.py`

## 12. Criterio editorial del informe

### Hallazgo defendible

Se publica como defendible solo si viene de `primary_incidents` y conserva:

- par comparable
- mismo nivel
- geometria primaria
- confianza de reporte distinta de `low`

### Ruido tecnico

Se mantiene fuera del resumen ejecutivo cuando cae en alguno de estos grupos:

- `debug_conflicts`
- elementos `suppressed`
- geometria `bbox` o señal debil
- `default_level` o fallback que baja la confianza
- pares bloqueados por `coordinate_band_mismatch`, `level_mismatch` o status de audit

### Severidad, prioridad y confianza

El render ahora calcula tres ejes distintos:

- `severity`
  - `critical`, `high`, `medium`, `low`
- `priority`
  - `P1`, `P2`, `P3`
- `report_confidence`
  - `high`, `medium`, `low`

Regla practica:

- `severity` estima impacto tecnico
- `priority` ordena la revision
- `report_confidence` dice que tan defendible es el hallazgo con la extraccion actual

## 13. Re-render desde outputs existentes

No hace falta relanzar todo el pipeline para mejorar el informe.
Se puede regenerar desde una carpeta de outputs ya creada:

```powershell
python scripts/render_coordination_report.py --run-dir analysis_output/serena18_analysis_05_NPT_P1 --refresh-supporting-md
```

Eso vuelve a escribir:

- `technical_coordination_report.md`
- `coordination_report_context.json`
- y opcionalmente refresca `primary_incidents.md`, `coordinate_audit.md`, `hotspot_incidents.md`

## Reglas de negocio que ya quedaron claras

- No mezclar entregas distintas por defecto.
- No comparar `ARQ` vs `EST` si la banda de coordenadas no coincide.
- No publicar clashes primarios nacidos de `bbox` suelto si existe mejor geometria.
- No usar PDF como respaldo si ya existe CAD comparable para esa misma cohorte/nivel.
- Si `scheduled_pair_count = 0`, el problema no es el threshold de clash: el problema es comparabilidad.
- Un volumen alto de `debug` no invalida la corrida, pero si indica que todavia hay trabajo de limpieza o suppression.

## Timeline tecnico de analisis ya ejecutados

Este resumen prioriza los analisis que cambiaron la metodologia o produjeron señal util.

## NASAS 09

### Analisis 01

Archivo:

- `analysis_output/nasas09_analysis_01/2026-04-23_analisis_01_NASAS_09_rev_20260320.md`

Hallazgo:

- la cohorte correcta era la entrega `20.03.2026`
- metodologicamente, la seleccion por entrega estaba bien
- operativamente, el pipeline no pudo ingerir los DWG en ese entorno

Resultado:

- APS: `403 ProductAccessRequiresCapacity`
- local DXF/ezdxf: `0 elementos / 0 clashes`

Leccion:

- el cuello de botella no era la logica de cohorte sino la extraccion geometrica

### Analisis 01 provisional PDF

Archivo:

- `analysis_output/nasas09_analysis_01_provisional_pdf/2026-04-23_analisis_01_NASAS_09_provisional_pdf_rev_20260320.md`

Hallazgo:

- produjo una señal provisional
- util para orientacion humana
- no defendible como clash CAD fino

Leccion:

- PDF-only sirve para screening, no para cierre tecnico

### Analisis 02 DWG directo

Archivo:

- `analysis_output/nasas09_analysis_02_dwg_direct/2026-04-23_analisis_02_NASAS_09_rev_20260320_dwg_direct.md`

Resultado:

- `744` elementos
- `193` clashes HARD
- confianza global `medium`

Lectura:

- ya hubo clash CAD real
- la mayor señal quedo en `ELECTRICO vs ESTRUCTURA`
- arquitectura quedo subrepresentada por filtrado/cobertura parcial

Leccion:

- COM desbloqueo valor real, pero con bounding boxes y cobertura incompleta

## SERENA 18

### Analisis 02 core mixed native

Referencia:

- `analysis_output/serena18_analysis_03_coordinate_audit_arq_est/2026-04-24_comparacion_analysis_02_vs_03_SERENA_18.md`

Resultado resumido:

- `4,760` clashes
- corrida masiva, multi-entrega, multi-fuente

Lectura:

- sirvio como radar
- no servia como conteo final defendible

Leccion:

- demasiada mezcla de cohortes y sistemas de coordenadas

### Analisis 03 coordinate audit ARQ/EST

Archivo:

- `analysis_output/serena18_analysis_03_coordinate_audit_arq_est/2026-04-24_comparacion_analysis_02_vs_03_SERENA_18.md`

Resultado:

- `0` incidencias primarias

Pero ojo:

- no fue un fracaso de deteccion
- fue un exito de control de calidad

Leccion:

- el audit detecto que la base ARQ y la estructura no compartian banda de coordenadas
- bloquear todos los pares fue la decision correcta

### Analisis 04 dominant cluster

Archivo:

- `analysis_output/serena18_analysis_04_dominant_cluster/2026-04-25_analysis_04_resultado.md`

Resultado:

- `0` pares programados
- `0` incidencias primarias

Leccion:

- el problema no era un bbox global contaminado
- la desalineacion era real
- habia que pasar a alineacion manual

### Analisis 05

Indice:

- `analysis_output/serena18_analysis_05_runs/README.md`

Este grupo ya es el punto de madurez mas alto del workstream.

#### NPT_P1

Archivo:

- `analysis_output/serena18_analysis_05_runs/analysis_05_NPT_P1/2026-04-25_analysis_05_NPT_P1_resultado.md`

Resultado:

- alineacion manual aplicada
- `53` incidencias primarias
- `179` debug
- confianza dominante `medium`

Lectura:

- comparabilidad desbloqueada
- señal util para revision dirigida

#### NPT_P2

Archivo:

- `analysis_output/serena18_analysis_05_runs/analysis_05_NPT_P2/2026-04-25_analysis_05_NPT_P2_resultado.md`

Resultado:

- `66` incidencias primarias
- `769` debug
- confianza primaria `high`
- domina `polyline/polyline`

Lectura:

- es una de las mejores corridas del repo para `ARQ vs EST`

#### CIMENTACION

Archivo:

- `analysis_output/serena18_analysis_05_runs/analysis_05_CIMENTACION/2026-04-25_analysis_05_CIMENTACION_resultado.md`

Resultado:

- `1` incidencia primaria
- `706` debug

Lectura:

- valida comparabilidad
- aun no cierra el nivel como entregable fuerte

#### SOTANO

Archivo:

- `analysis_output/serena18_analysis_05_runs/analysis_05_SOTANO/2026-04-25_analysis_05_SOTANO_resultado.md`

Resultado:

- `0` incidencias primarias
- `429` debug

Lectura:

- el scheduler ya paso
- la señal defendible todavia no aparece

#### TECHO

Archivo:

- `analysis_output/serena18_analysis_05_runs/analysis_05_TECHO/2026-04-25_analysis_05_TECHO_resultado.md`

Resultado:

- `108` incidencias primarias
- `842` debug
- confianza `high`

Lectura:

- junto con `NPT_P2`, es de las mejores corridas presentables

## Como correr una nueva corrida sin romper la metodologia

## Caso A: corrida standard

Usar cuando se quiere explorar mas libremente o correr NASAS sin el pipeline estricto de `fast_compare`.

Ejemplo base:

```powershell
& '.\.venv\Scripts\python.exe' scripts\run_nasas09_project_coordination.py `
  --nasas-root "aps_integration\NASAS 09" `
  --registry "aps_integration\NASAS 09\coordination\sample_project_levels.json" `
  --skip-pdf `
  --strict-levels `
  --output "analysis_output\mi_run\clash_project_report.json"
```

Notas:

- `--dwg-via-aps` solo si la cuenta APS realmente tiene capacidad
- si no, el camino mas util hoy es `accore`, con COM como fallback

## Caso B: corrida `fast_compare`

Usar cuando el objetivo es producir un reporte defendible para `ARQ vs EST`.

Ejemplo base:

```powershell
& '.\.venv\Scripts\python.exe' scripts\run_nasas09_project_coordination.py `
  --analysis-profile fast_compare `
  --stage full `
  --nasas-root "repositorios\SERENA 18" `
  --registry "repositorios\SERENA 18\coordination\serena18_project_levels.json" `
  --cohort-manifest "analysis_output\mi_run\cohort_manifest.json" `
  --alignment-manifest "analysis_output\mi_run\alignment_manifest.json" `
  --skip-pdf `
  --strict-levels `
  --output "analysis_output\mi_run\summary.json"
```

## Formato esperado del `cohort_manifest.json`

```json
{
  "cohort_name": "analysis_06_arq_est_manual",
  "source_files": [
    "PLANOS RECIBIDOS/ARQUITECTONICOS/...",
    "PLANOS RECIBIDOS/TECNICOS/ESTRUCTURAL/..."
  ]
}
```

## Formato esperado del `alignment_manifest.json`

```json
{
  "entries": [
    {
      "source_file": "PLANOS RECIBIDOS/ARQUITECTONICOS/06. JUNIO 2024/Serena 18 -PLANTA PISOS 10-10-2022.dwg",
      "translate_mm": [-4871358.9623, 500416.0999],
      "note": "Alineacion manual basada en centroides dominantes"
    }
  ]
}
```

## Checklist de validacion antes de publicar resultados

1. `comparison_readiness_report` muestra cohorte comparable o la cohorte fue forzada conscientemente por manifest.
2. `coordinate_audit` deja los archivos relevantes como `eligible`.
3. `pair_schedule` tiene pares realmente programados.
4. `primary_incidents` no depende de `bbox` contaminado como fuente dominante.
5. La mayoria de la señal util esta en `polyline/polyline` o `polyline/line`, no en proxies pobres.
6. El nivel del run esta claro: `NPT_P1`, `NPT_P2`, `CIMENTACION`, `SOTANO`, `TECHO`, etc.
7. Si la confianza queda en `medium`, explicar por que. Si queda en `high`, dejar evidencia de la geometria usada.

## Que no debe hacer el siguiente programador

- No volver a mezclar entregas por fecha solo para "obtener mas clashes".
- No forzar `mix_issues` como solucion de cobertura.
- No publicar `debug_conflicts` como si fueran hallazgos finales.
- No relajar el scheduler si el problema real es alineacion.
- No usar PDFs superpuestos o archivos de revision como fuente primaria.

## Que si vale la pena hacer despues

- consolidar esta metodologia en un runner menos NASAS-centric de nombre
- separar mejor `standard screening` de `defensible clash review`
- persistir manifests por nivel/proyecto en una carpeta estable
- bajar el volumen de `debug` con mejores reglas de suppression
- mejorar la apertura ARQ en NASAS, donde la cobertura aun es inferior a `EST/ELEC`

## Veredicto de estado actual

El proyecto ya no esta en fase de "probar si clash funciona".

Ya hay una metodologia clara:

- NASAS dejo resuelto el criterio correcto de cohorte y mostro los limites de APS/COM/ezdxf
- SERENA dejo resuelto el flujo metodologico correcto
- `analysis_05` demostro que con cohorte manual + alineacion manual + `fast_compare`, si se pueden producir incidencias primarias utiles

Si otro programador toma este workstream hoy, su punto de partida correcto no es `analysis_02`.
Su punto de partida correcto es:

- runner `fast_compare`
- manifests de cohorte/alineacion
- audit y scheduler como compuertas obligatorias
- `primary_incidents` como salida defendible
