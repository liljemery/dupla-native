# Auditoría Técnica del Pipeline de Presupuestos — Dupla (sin APS)

> **Nota de stack (corrección obligatoria).** El prompt original asume **NestJS/TypeScript**. El backend real de Dupla es **Python**: extracción CAD local en `motor/` (LibreDWG + `ezdxf`), procesamiento y presupuesto en `processor/` (FastAPI + worker), y solo el `frontend/` es TypeScript. Todas las instrucciones de este blueprint se expresan contra el código Python real (módulos, funciones, dataclasses), no contra DTOs de NestJS. Codex debe trabajar sobre los archivos citados.

---

## Diagnóstico de la Arquitectura Actual

Flujo real (sin APS):

```
DWG/DXF ──► motor/coordination/extraction/local_cad_pipeline.py ──► cad_facts (inventory_hints)
PDF→PNG ──► processor/agents/vision_agent.py (gpt-5.1 Vision) ──► simple JSON ──► LevelInventory
                                   │
        cad_facts + LevelInventory ▼
        processor/core/inventory_builder.build_level_inventory  (merge CAD + visión)
                                   ▼
        processor/agents/quantifier_agent.quantify_inventory  (takeoffs deterministas)
                                   ▼
        processor/knowledge/schedule_authority  (cuadros = autoridad → despiece real de acero)
                                   ▼
        processor/budget/composer.compose_budget  (capítulos + líneas + precio)
            ├─ pricing/resolver.PriceResolver  (crosswalk → APU cliente → ConstruCosto → pending)
            └─ pricing/apu_matcher.APUMatcher  (keyword → embedding → ConstruCosto)  [legacy]
                                   ▼
        budget/export_excel + budget/consolidator  (xlsx multi-disciplina)
```

### Fortalezas confirmadas en código
- **Trazabilidad fuerte.** Cada `QuantityTakeoff` lleva `formula`, `inputs`, `assumptions`, `source_refs`, `trace`, `confidence` y `requiere_revision` (`quantifier_agent._make_takeoff`, `_derive_confidence_and_review_flag`). Esto es excelente y debe preservarse.
- **Anti-alucinación en Visión.** El prompt (`vision_agent._SIMPLE_SYSTEM_PROMPT`, reglas 13–15) obliga a `reinforcement_visible` y `missing_detail_sheets`; el adaptador no inventa acero cuando el armado no es visible (`_simple_to_level_inventory`).
- **Cuadros como autoridad.** `schedule_authority` reemplaza el acero estimado por ratio con despiece real parseado por `disciplines/estructura/rebar.py` (catálogo ASTM, perímetro de estribo, recubrimiento) → `quantity_source="cuadro"`.
- **Guard de familia de unidad.** `composer._unit_family_compatible` impide que un takeoff en `kg` (acero) tome un precio en `m3` (hormigón) — este guard ya corrigió un sobrecosto histórico.
- **Jerarquía de fuentes correcta.** `PriceResolver` prioriza el APU del cliente (relational) y usa ConstruCosto solo como fallback.

### Fallos y limitaciones (motores de las tareas de refactorización)

| # | Severidad | Hallazgo | Evidencia |
|---|-----------|----------|-----------|
| D1 | **Alta** | **Insumos sin precio NO se estiman.** El requisito de negocio dice: si no hay precio, *flag pero asume/estima*. Hoy el sistema retorna `unit_price=None` / `"PRECIO_PENDIENTE"` y la partida queda sin valorar. | `pricing/resolver.py:179-183` (rama `pending`); `budget/composer.py:271` (`return None, "PRECIO_PENDIENTE"`) |
| D2 | **Alta** | **Dos motores de precio coexisten** (`PriceResolver` vs `APUMatcher`) con lógicas de fallback distintas. Riesgo de divergencia y doble mantenimiento; el guard de unidad solo existe en una rama. | `composer.compose_budget_rows:798-889` |
| D3 | **Media** | **Encofrado: solo área de contacto, sin TIPO.** El requisito pide identificar tipo de encofrado (formaleta de madera/metálica vs. molde perdido de bloque). Hoy `*_formwork_area_hint` calcula solo m² de contacto. | `quantifier_agent._structural_formwork_payload:550-622` |
| D4 | **Media** | **Clasificación de capa solo por prefijo NCS.** Capas dominicanas/GEBSA sin prefijo (`COLUMNAS`, `VIGAS`, `MUROS`) caen a `UNKNOWN`. | `config/layer_mapping.classify_layer:135-174` |
| D5 | **Media** | **Visión de una sola pasada por página.** No hay recorte/zoom dedicado a cuadros de columnas/vigas; `OPENAI_VISION_REASONING_EFFORT` default `low`. Tablas densas o cotas pequeñas se pierden. | `vision_agent._analyze_plan_uncached`; `_vision_reasoning_effort:103-104` |
| D6 | **Media** | **`h` y secciones por defecto silenciosas en volumen.** Cuando faltan, se aplican defaults (`0.30×0.50` viga, `0.40×0.40` columna, losa `0.20`). Se marcan en `assumptions`/`confidence`, pero el volumen entra al total igual. | `quantifier_agent._DEFAULT_*`, `_apply_structural_defaults:1479-1537` |
| D7 | **Baja** | **DWG 2D no aporta Z.** La altura/profundidad real no sale del CAD (`DEFAULT_Z_THICKNESS_MM=250`); depende de Visión/cuadro. Si ambos faltan, se usa default sin advertencia explícita de "Z ausente". | `local_cad_pipeline.py:31` |
| D8 | **Baja** | **Moneda mixta no resuelta en la rama legacy.** `price_currency="?"` cuando el precio viene de BC3/ConstruCosto en la rama `APUMatcher`. | `composer.py:894-896` |

---

## Lógica de Dominio (Ingeniería Civil)

### 1. Extracción de la sección transversal y la altura (`h`)
Fuente de verdad por orden de prioridad (regla a implementar/consolidar):

1. **Cuadro/tabla** (`schedule_row_text`, `spec_source="schedule_table"`) → autoridad absoluta de sección y despiece.
2. **Cota anotada en la misma hoja** (`spec_source="dimension_on_plan"`).
3. **Default normativo** (solo si 1 y 2 faltan) → marcar `requiere_revision=true` **y excluir del subtotal "en firme"** (ver T3).

Notación de sección estándar a normalizar: `0.30x0.60`, `30x60`, `Ø0.40` (circular). Ya cubierto parcialmente por `apu_matcher.normalize_section` y `_circular_section_descriptor`.

### 2. Fórmulas de cubicación (revisadas)

| Elemento | Volumen de hormigón | Estado en código |
|----------|---------------------|------------------|
| Viga / columna rectangular | `L · b · h` | OK — `_structural_volume_payload:514-530` |
| Columna circular | `L · π · (Ø/2)²` | OK — `_structural_volume_payload:492-512` |
| Losa | `Área · espesor` | OK — `:532-545` |
| Zapata | `B · L · h` (no usar `area·h` si faltan B,L) | **Falta fórmula explícita de zapata; revisar** |
| Excavación | Prismoidal `(A₁+A₂+4·Aₘ)·L/6`, simple `A·prof` | OK — `_excavation_takeoffs:2034-2156` |

**Encofrado (área de contacto) — fórmulas actuales correctas, falta el TIPO:**
- Viga: `(2h + b) · L` (excluye cara superior). `:564-565`
- Columna rectangular: `2(b+h) · L`. `:600-601`
- Columna circular: `π · Ø · L`. `:585-586`
- Losa: `Área` (solo cara inferior). `:612-620`

**Heurística de TIPO de encofrado a añadir (D3):**
```
si material_hint == "concrete" y element_type in {beam, column, slab, footing}:
    encofrado = "formaleta"  (madera/metálica, se descuenta del APU si reusable)
si muro: material_hint == "masonry" (bloque):
    encofrado = "ninguno"    (el bloque ES el molde; NO generar partida de encofrado)
si muro de hormigón armado (shear wall):
    encofrado = "formaleta_doble_cara"
```

### 3. Despiece de acero (APU)
- **Con cuadro:** `schedule_authority._steel_kg_for_row` → `rebar.parse_main_bars` + `parse_stirrups` + `calculate_main_bar_weight`/`calculate_stirrup_weight` (catálogo `REBAR_CATALOG`, perímetro `2·((b-2r)+(h-2r))+gancho`, recubrimiento 0.04 m). Es la ruta correcta.
- **Sin cuadro (fallback):** ratio `kg/m³` (`_REBAR_KG_PER_M3`: viga 100, columna 120, losa 80, zapata 60). Marcar siempre `quantity_source="ratio_estimate"` y `requiere_revision=true` (ya se hace, `_rebar_takeoffs:1574`).
- **Regla anti-duplicidad:** cuando `schedule_authority` produce el `*_reinforcement_kg` desde cuadro, debe **eliminar** el takeoff por ratio del mismo `item_key` (no sumar ambos).

### 4. APU y bases de datos — jerarquía de verdad
1. **BD del cliente (relational / workbook curado)** = verdad absoluta → `PriceResolver` paso 1 (crosswalk → `relational.apus`).
2. **EXCLUDE** = costo ya incluido en otro APU → precio 0, sin doble conteo (`resolver.py:145-150`). *Mecanismo de prevención de duplicidad #1.*
3. **ConstruCosto (Punta Cana, DOP)** = fallback solo si el catálogo del cliente no tiene precio.
4. **Estimación obligatoria (NUEVO, D1):** si 1–3 fallan → estimar por (a) APU análogo del mismo capítulo/unidad, o (b) índice de inflación sobre el precio histórico más cercano; emitir `price_estimated=true` + `requiere_revision=true`. **Nunca dejar la partida sin valor.**

**Prevención de duplicidad (consolidada):**
- EXCLUDE de crosswalk (bundling).
- `budget_filter_sets` / `concrete_volume_prefixes` evita cobrar volumen genérico + volumen de hormigón del mismo elemento (`composer.py:301-313, 363-365`).
- Guard de familia de unidad evita doble cobro acero(kg)/hormigón(m³).
- Regla acero: cuadro reemplaza ratio (sección 3).

---

## Tareas de Refactorización para Codex

> Ejecutar en orden. Cada tarea cita archivo y símbolo reales. Mantener siempre el contrato de trazabilidad (`assumptions`, `confidence`, `requiere_revision`, `trace.metadata`).

### T1 — Estimador de precio para insumos sin precio (cierra D1) — **prioridad máxima**
- **Archivo:** `processor/pricing/resolver.py`.
- Añadir un paso **3.5** antes de `pending`: método `PriceResolver._estimate_price(item_type, inputs, unit, description)` que:
  1. busca el APU análogo más cercano por embedding/keyword dentro del mismo capítulo y misma familia de unidad;
  2. si no hay análogo, aplica un `inflation_index` (config nueva, default p.ej. desde precio histórico) sobre el precio base más parecido.
- Extender `PriceResolution` con `estimated: bool = False` y `estimate_basis: str | None`.
- La rama final solo retorna `pending` si la estimación también falla (caso límite real, p.ej. catálogo vacío).
- **Espejo en la rama legacy:** `composer._extract_unit_price` debe invocar el mismo estimador antes de devolver `"PRECIO_PENDIENTE"`.

### T2 — Consolidar a un solo motor de precio (cierra D2)
- Hacer `PriceResolver` el único camino en `composer.compose_budget_rows`. Mover la fuerza del keyword/embedding de `APUMatcher` **dentro** del crosswalk/relational del resolver (como estrategia de matching), de modo que `apu_matcher=` quede deprecado.
- Garantizar que el `_unit_family_compatible` se aplica en TODAS las resoluciones (hoy solo en algunas ramas).
- Marcar `apu_matcher` param como deprecado con `DeprecationWarning`; no romper firmas públicas (`compose_budget` mantiene kwargs).

### T3 — Subtotal "en firme" vs "preliminar" (cierra D6/D7)
- En `composer.compose_budget_rows`, separar líneas con `requiere_revision=true` o `quantity_source in {default_estimate, ratio_estimate}` en una sección/columna "PRELIMINAR".
- En `consolidator._write_summary_sheet`, añadir columna "Subtotal en firme" vs "Subtotal con estimados".
- Cuando el volumen use sección/`h` por default, añadir `assumption` explícita `"Z/altura ausente en DWG y plano: usar cota real antes de cerrar"`.

### T4 — Clasificación de encofrado por tipo (cierra D3)
- **Archivo:** `processor/agents/quantifier_agent.py`, `_structural_formwork_payload`.
- Añadir a `inputs` del takeoff `formwork_type` según la heurística de la sección Dominio 2.
- Para muros de bloque (`material_hint=="masonry"`), **no** emitir `formwork_area_hint`.
- El crosswalk/APU debe poder mapear `formwork_type` a la partida de encofrado correcta.

### T5 — Fallback de clasificación de capa por palabra clave (cierra D4)
- **Archivo:** `processor/config/layer_mapping.py`, `classify_layer`.
- Tras fallar prefijo y alias, buscar tokens en el nombre completo: `{columna|column, viga|beam, zapata|footing, muro|wall, losa|slab}` → disciplina/elemento.
- Reusar la lógica de `motor/coordination/core/layer_role_mapper.py` y `selection/file_discipline_inference.py` si ya cubren esto (evitar duplicar).

### T6 — Pasada de Visión dedicada a cuadros/tablas (cierra D5)
- **Archivo:** `processor/agents/vision_agent.py`.
- Cuando `_cad_suggests_structural` o `upload_discipline_id=="estructura"`: hacer una **segunda llamada** con `reasoning_effort="high"` enfocada solo en cuadros (`structural_elements` + `schedule_row_text`), y fusionar con la pasada general (additivo, autoridad del cuadro).
- Considerar recorte/zoom de la región de tabla si el detector la localiza; mantener `detail:"high"`.
- Bump de `VISION_PROMPT_VERSION` para invalidar caché.

### T7 — Garantizar no-duplicidad acero ratio vs cuadro (refuerza Dominio 3)
- En `schedule_authority`, al inyectar `*_reinforcement_kg` desde cuadro, eliminar el takeoff homónimo con `quantity_source="ratio_estimate"` por `item_key`. Añadir test de regresión.

### T8 — DTOs/dataclasses a actualizar (`processor/core/schemas.py`)
- `QuantityTakeoff.inputs`: documentar claves nuevas `formwork_type`, `price_estimated`, `estimate_basis`.
- `StructuralElement`: confirmar campos `section_diameter_m` / `cross_section_shape` como first-class (hoy se leen de `inputs.raw`).
- `PriceResolution` (resolver): campos `estimated`, `estimate_basis` (T1).

### T9 — Prompts de OpenAI a cambiar
- `vision_agent._SIMPLE_SCHEMA_HINT`: añadir en `structural_elements` el campo `formwork_hint` ("ninguno|formaleta|molde_bloque") y en `walls` `is_concrete_shear_wall`.
- Reforzar regla: para zapatas pedir `B`, `L`, `h` explícitos (no solo `area_m2`).

---

## Casos de Prueba (Edge Cases)

1. **DWG sin Z / solo 2D.** `local_cad_pipeline` usa `DEFAULT_Z_THICKNESS_MM`. Test: confirmar que el volumen resultante lleva `assumption` de Z ausente y entra en subtotal "preliminar" (T3), nunca en firme.
2. **Sección presente pero `h` ausente.** `_apply_structural_defaults` rellena con default → verificar `requiere_revision=true` y `confidence < 1.0`.
3. **Cuadro de columnas con armado + plano arquitectónico del mismo elemento.** Verificar que el acero del cuadro (T7) reemplaza al ratio y que no se duplica la columna entre disciplinas.
4. **Insumo sin precio en cliente ni en ConstruCosto.** (T1) Debe producir precio estimado + `price_estimated=true` + flag, **no** `PRECIO_PENDIENTE`. Solo si el estimador también falla → `pending`.
5. **Matching falla en ConstruCosto (score < min_score=0.45).** `find_best_price` retorna None → cae a estimador (T1). Verificar que no rompe el pipeline (`resolver.py:160` ya captura excepción).
6. **Muro de bloque.** No debe generar partida de encofrado (T4); se presupuesta por área (`composer.takeoff_budget_eligibility:396-398` ya excluye `wall_volume`/`wall_length` de mampostería).
7. **Columna circular.** Volumen `π(Ø/2)²·L` y encofrado `πØ·L` (ya cubierto; añadir test si no existe — ver `tests/test_circular_column_and_excavation.py`).
8. **Capa `COLUMNAS` sin prefijo NCS.** (T5) Debe clasificar a Estructural, no `UNKNOWN`.
9. **Visión devuelve JSON inválido.** `_extract_json` → `parse_error`; el nivel se omite con warning sin abortar la corrida (`_run_full_vision_analysis_async.guarded`).
10. **Unidad incompatible APU.** Takeoff `kg` no debe aceptar APU `m3` (guard activo); test de regresión del sobrecosto de acero.
11. **Excavación con 1 solo perfil.** Cae a fórmula simple `A·prof`; con `area`/`depth` nulos o ≤0 se omite la línea (`_excavation_takeoffs:2104-2119`).
12. **Multi-nivel con IDs repetidos.** `quantify_inventory` prefija `level_id:` para evitar colisión de `item_key` (`:2187-2195`) — test de unicidad.
