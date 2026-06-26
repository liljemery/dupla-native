"""
Vision agent for normalized building inventory extraction.

Two-step approach:
1. The configured vision model (default: gpt-5.1 via OPENAI_VISION_MODEL) returns a simple flat count of visible elements.
2. Python adapter converts that simple inventory to the full LevelInventory schema.

This avoids asking the model to fill a complex 15-field schema, which causes it to
return mostly null/empty data. The simpler prompt produces useful counts.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import random
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from core.api_key_manager import APIKeyManager
from core.confidence_rubric import score_vision_entity
from core.schemas import LevelInventory, level_inventory_from_dict

load_dotenv(Path(__file__).parent.parent / ".env")

# Vision Chat Completions (.env overrides):
#   OPENAI_VISION_MODEL — default gpt-5.1 (e.g. gpt-5.1-2025-11-13 for a snapshot)
#   OPENAI_VISION_MAX_OUTPUT — max output tokens (default 4096)
#   OPENAI_VISION_REASONING_EFFORT — gpt-5.x only: none | low | medium | high (default none)
#   OPENAI_VISION_TEMPERATURE — gpt-4 family only (default 0.1)

logger = logging.getLogger("dupla.vision")

_REPO_ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_VISION_MODEL = "gpt-5.1"

# Bump when the system / user prompt structure changes; invalidates cache.
VISION_PROMPT_VERSION = "v3-structural-tables"

try:
    from openai import OpenAI

    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

_KEY_MANAGER: APIKeyManager | None = None
_KEY_LOCK = threading.Lock()


def _get_key_manager() -> APIKeyManager:
    global _KEY_MANAGER
    if _KEY_MANAGER is None:
        with _KEY_LOCK:
            if _KEY_MANAGER is None:
                _KEY_MANAGER = APIKeyManager()
    return _KEY_MANAGER


def _get_client_with_key() -> tuple["OpenAI", str]:
    if not HAS_OPENAI:
        raise ImportError("openai is not installed.")
    api_key = _get_key_manager().next_key()
    return OpenAI(api_key=api_key), api_key


def get_client() -> "OpenAI":
    if not HAS_OPENAI:
        raise ImportError("openai is not installed.")

    client, _ = _get_client_with_key()
    return client


def vision_model_id(explicit: str | None = None) -> str:
    """Resolved vision model id (OPENAI_VISION_MODEL or default gpt-5.1)."""
    if explicit is not None:
        s = explicit.strip()
        return s or _DEFAULT_VISION_MODEL
    raw = (os.getenv("OPENAI_VISION_MODEL") or "").strip()
    return raw or _DEFAULT_VISION_MODEL


def _vision_max_output_tokens() -> int:
    raw = (os.getenv("OPENAI_VISION_MAX_OUTPUT") or "4096").strip()
    try:
        n = int(raw)
    except ValueError:
        return 4096
    return max(256, min(n, 128_000))


def _vision_reasoning_effort() -> str:
    return (os.getenv("OPENAI_VISION_REASONING_EFFORT") or "low").strip() or "low"


def _vision_concurrency() -> int:
    raw = (os.getenv("DUPLA_VISION_CONCURRENCY") or "30").strip()
    try:
        return max(1, min(int(raw), 60))
    except ValueError:
        return 30


def _vision_max_retries() -> int:
    raw = (os.getenv("OPENAI_VISION_MAX_RETRIES") or "4").strip()
    try:
        return max(1, int(raw or "4"))
    except ValueError:
        return 4


def _vision_retry_base_seconds() -> float:
    raw = (os.getenv("OPENAI_VISION_RETRY_BASE_SECONDS") or "0.75").strip()
    try:
        return max(0.0, float(raw or "0.75"))
    except ValueError:
        return 0.75


def _exception_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    try:
        return int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        return None


def _uses_gpt5_completion_params(model: str) -> bool:
    return model.lower().startswith("gpt-5")


def _vision_chat_completion(
    client: "OpenAI",
    *,
    model: str,
    messages: list[dict[str, Any]],
    reasoning_effort: str | None = None,
) -> Any:
    """Chat Completions with kwargs compatible with GPT-5.x vs GPT-4 family."""
    max_out = _vision_max_output_tokens()
    if _uses_gpt5_completion_params(model):
        return client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_out,
            reasoning_effort=reasoning_effort or _vision_reasoning_effort(),
        )
    try:
        temp = float((os.getenv("OPENAI_VISION_TEMPERATURE") or "0.1").strip() or "0.1")
    except ValueError:
        temp = 0.1
    return client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_out,
        temperature=temp,
    )


def encode_image(image_path: Path) -> str:
    with open(image_path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("utf-8")


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    import re

    fenced = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    if start >= 0:
        depth = 0
        for index in range(start, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : index + 1])
                    except json.JSONDecodeError:
                        break

    return {"raw_text": text, "parse_error": True}


# ---------------------------------------------------------------------------
# Step 1: Simple prompt — vision model counts visible elements
# ---------------------------------------------------------------------------

_MAX_OFFICE_METHODOLOGY_CHARS = 12000


_SIMPLE_SYSTEM_PROMPT = """Eres un ingeniero presupuestista senior dominicano con 20+ años de experiencia en cuantificación de obras.
Analizas planos de construcción (plantas, cortes, elevaciones, detalles) para extraer TODOS los elementos constructivos con sus dimensiones exactas para presupuesto.

Si el usuario incluye un bloque "METODOLOGÍA DE OFICINA", aplícalo como criterio de prioridad para
interpretar notaciones y desgloses, sin contradecir el formato JSON ni inventar cantidades no visibles.

REGLAS OBLIGATORIAS:
1. BUSCA ACTIVAMENTE en toda la imagen: cuadros de resumen, leyendas, notaciones, cotas, secciones anotadas, detalles constructivos.
2. NO devuelvas null si el dato es visible o deducible. Si ves "V-1 0.30x0.60" eso son section_width_m=0.30 y section_height_m=0.60.
3. Si ves "B-6" o "bloque 6" = espesor 0.15m (6 pulgadas). "B-8" = 0.20m. "B-4" = 0.10m.
4. Notaciones tipo "e=0.20" o "esp. 0.15" = espesor en metros.
5. Si ves cotas entre líneas de nivel (NPT+0.00, NPT+2.80) = altura de entrepiso.
6. CADA tipo diferente de elemento va en una entrada separada. No agrupes bloques de 6 con bloques de 8. Para MUROS: una fila en `walls` por combinación distinta de wall_typology / espesor / material (ej. C1 bloque 6" vs C2 bloque 4"); no fusiones áreas de tipos distintos en un solo objeto.
7. En planos ARQUITECTÓNICOS prioriza: albañilería, acabados, carpintería, pisos, cielos. En planos ESTRUCTURALES prioriza: structural_elements (rotulos C1/V1, tablas, secciones) y NO diluyas el JSON con muros de acabado salvo que estén cotados en esa misma hoja.
8. Para baños: cuenta CADA pieza sanitaria (inodoro, lavamanos, ducha, bañera, bidet, gabinete).
9. Para cocinas: identifica gabinetes, fregaderos, conexiones de gas si son visibles.
10. Para instalaciones eléctricas: tomacorrientes, interruptores, luminarias, paneles, salidas especiales.
11. Para instalaciones sanitarias: tuberías visibles, registros, trampas, válvulas, puntos de agua.
12. Identifica el TIPO DE PLANO: arquitectónico, estructural, eléctrico, sanitario, corte, elevación, detalle.
13. PLANO ARQUITECTÓNICO: NO cuantifiques volúmenes de hormigón, peso de acero ni encofrado. Si ves rotulos C1/V1 en planta, puedes listarlos en structural_elements como referencia ligera (sección si está cotada en esa misma hoja), pero NO inventes armados ni tablas que no aparezcan.
14. PLANO ESTRUCTURAL (o hoja de cuadro de columnas/vigas): prioridad ABSOLUTA a structural_elements. Copia el ROTULO exacto del plano (C1, C2, V1…). Lee sección (0.30x0.60, etc.) y f'c / hormigón SOLO si aparece en esta imagen o en una tabla visible. Si el armado o el despiece NO está en esta hoja, pon reinforcement_visible=false y missing_detail_sheets=true; NO inventes estribos ni diámetros.
15. Si una celda de tabla está ilegible o recortada, deja el campo en null y explica en annotations_and_notes.

Return ONLY valid JSON — no markdown, no explanation, no text."""
_SIMPLE_SCHEMA_HINT = """{
  "plan_type": "architectural|structural|electrical|plumbing|section|elevation|detail|site|combined",
  "floor_area_m2": <number or null>,
  "ceiling_height_m": <number or null>,
  "floor_to_floor_height_m": <number or null>,
  "walls": [
    {"id": "descriptive label (e.g. muro_ext_bloque8, muro_int_bloque6, muro_concreto)",
     "wall_typology": "<rotulo del plano si existe: C1, C2, PERIMETRO, etc.; null si no aplica>",
     "tipo": "<opcional: sinónimo de wall_typology si el plano usa solo \"tipo\"; null>",
     "ubicacion": "<ejes, niveles, zonas o null>",
     "material": "block_6in|block_8in|block_4in|concrete|drywall|wood|other",
     "location": "interior|exterior",
     "estimated_length_m": <number>,
     "estimated_area_m2": <number or null>,
     "height_m": <number or null>,
     "thickness_m": <number>,
     "finish_interior": "plaster|ceramic_tile|paint|none|null",
     "finish_exterior": "plaster|ceramic_tile|paint|exposed|none|null",
     "structural": true/false,
     "is_concrete_shear_wall": true/false,
     "count_segments": <integer>}
  ],
  "doors": [
    {"id": "descriptive (e.g. puerta_principal, puerta_interior_madera)",
     "label": "<texto en plano ej 'Polimetalica 0.90x2.10'; null si no>",
     "type": "main_entry|interior|service|bathroom|closet|garage|sliding|folding|other",
     "material": "wood|metal|aluminum|pvc|glass|other",
     "count": <integer>,
     "width_m": <number or null>,
     "height_m": <number or null>,
     "includes_frame": true/false,
     "includes_hardware": true/false}
  ],
  "windows": [
    {"id": "descriptive (e.g. ventana_corrediza_aluminio)",
     "label": "<texto en plano; null si no>",
     "type": "sliding|fixed|casement|jalousie|louver|awning|other",
     "material": "aluminum|wood|pvc|steel|other",
     "glazing": "clear|tinted|frosted|double|other",
     "count": <integer>,
     "width_m": <number or null>,
     "height_m": <number or null>}
  ],
  "wet_areas": [
    {"id": "descriptive (e.g. bano_principal, bano_servicio, lavanderia)",
     "kind": "full_bathroom|half_bathroom|service_bathroom|laundry|utility",
     "count": <integer>,
     "area_m2": <number or null>,
     "has_shower": true/false,
     "has_bathtub": true/false,
     "has_toilet": true/false,
     "has_sink": true/false,
     "has_bidet": true/false,
     "has_cabinet": true/false,
     "floor_finish": "ceramic|porcelain|other|null",
     "wall_finish": "ceramic|porcelain|paint|other|null",
     "waterproofing_required": true/false}
  ],
  "kitchens": [
    {"id": "descriptive",
     "count": <integer>,
     "area_m2": <number or null>,
     "has_upper_cabinets": true/false,
     "has_lower_cabinets": true/false,
     "has_countertop": true/false,
     "countertop_material": "granite|marble|quartz|other|null",
     "has_sink": true/false,
     "has_gas_connection": true/false,
     "floor_finish": "ceramic|porcelain|other|null",
     "wall_finish": "ceramic|porcelain|paint|other|null"}
  ],
  "stairs": [
    {"id": "descriptive",
     "count": <integer>,
     "flights": <integer or null>,
     "steps_per_flight": <integer or null>,
     "width_m": <number or null>,
     "material": "concrete|steel|wood|other",
     "has_railing": true/false,
     "railing_material": "metal|wood|glass|other|null"}
  ],
  "structural_elements": [
    {"id": "ROTULO exacto del plano (ej: C1, C-1, V3) — misma grafía que la cota/leyenda",
     "type": "column|beam|slab|footing|shear_wall|lintel|tie_beam",
     "count": <integer>,
     "section_width_m": <number or null>,
     "section_height_m": <number or null>,
     "section_diameter_m": <number or null>,
     "cross_section_shape": "rectangular|circular|other|null",
     "length_m": <number or null>,
     "area_m2": <number or null>,
     "span_m": <number or null>,
     "material": "concrete|steel|masonry|other",
     "concrete_grade": "fc_210|fc_250|fc_280|null",
     "has_reinforcement": true/false,
     "formwork_hint": "ninguno|formaleta|molde_bloque|null",
     "reinforcement_visible": <true si en ESTA imagen se ven barras/estribos o nota de armado; false si no>,
     "spec_source": "schedule_table|detail_callout|dimension_on_plan|legend_only|unknown",
     "schedule_row_text": "<texto literal de la fila de tabla si aplica, o null>",
     "missing_detail_sheets": <true si falta despiece/tablas para cuantificar acero>,
     "ubicacion": "<ejes/niveles/zonas o null>",
     "notes": "<breve nota de evidencia o null>"}
  ],
  "floor_finishes": [
    {"id": "descriptive (e.g. piso_porcelanato_sala, piso_ceramica_bano)",
     "type": "ceramic|porcelain|marble|granite|vinyl|concrete_polished|terrazo|other",
     "area_m2": <number or null>,
     "location": "description of where"}
  ],
  "ceiling_finishes": [
    {"id": "descriptive",
     "type": "plaster|drywall|exposed|suspended|wood|other",
     "area_m2": <number or null>,
     "location": "description"}
  ],
  "electrical": [
    {"id": "descriptive",
     "label": "<leyenda exacta si aparece (voltaje, fases); null si no>",
     "type": "outlet_110v|outlet_220v|switch_single|switch_double|switch_triple|switch_dimmer|luminaire_ceiling|luminaire_wall|luminaire_recessed|panel_breaker|intercom|doorbell|data_outlet|tv_outlet|phone_outlet|smoke_detector|emergency_light|fan_connection|ac_connection|other",
     "count": <integer>,
     "location": "description or null"}
  ],
  "plumbing": [
    {"id": "descriptive",
     "label": "<leyenda exacta si aparece; null si no>",
     "type": "water_supply_point|drain_point|vent_pipe|cleanout|floor_drain|water_heater_connection|washing_machine_connection|hose_bib|valve|water_meter|cistern|pump|other",
     "count": <integer>,
     "pipe_diameter_in": <number or null>,
     "material": "pvc|cpvc|copper|galvanized|other|null",
     "location": "description or null"}
  ],
  "fixtures": [
    {"id": "descriptive",
     "label": "<texto visible en plano o leyenda, ej 'Inodoro ECO', 'Salida tomacorriente doble 110V'; null si no hay>",
     "type": "toilet|sink|shower_base|bathtub|bidet|urinal|laundry_sink|kitchen_sink|water_heater|pump|other",
     "count": <integer>,
     "brand_or_quality": "standard|premium|economy|null"}
  ],
  "exterior_works": [
    {"id": "descriptive",
     "type": "sidewalk|driveway|garden_wall|fence|gate|parking_area|ramp|retaining_wall|drainage_channel|other",
     "quantity": <number or null>,
     "unit": "m2|m|unit",
     "material": "description or null"}
  ],
  "annotations_and_notes": [
    {"text": "exact text visible", "interpretation": "what it means for quantification"}
  ]
}"""


def _detect_view_type(image_path: Path) -> str:
    name = image_path.name.lower()
    if "elev" in name or "fach" in name or "alzado" in name:
        return "elevation"
    if "sitio" in name or "emplaza" in name or "site" in name:
        return "site"
    if "planta" in name or "floor" in name or "page" in name:
        return "plan"
    return "unknown"


# Cuando el runner ya sabe la disciplina (carpetas GEBSA: arquitectura, estructura, …),
# ese contexto manda sobre heurísticas de nombres de capa.
# CLI / metadata pueden usar nombres canónicos (-a); prompts y capas GEBSA usan -o/-ura.
_UPLOAD_DISCIPLINE_ALIASES: dict[str, str] = {
    "arquitectonica": "arquitectura",
    "estructural": "estructura",
    "electrica": "electrico",
    "sanitaria": "sanitario",
}


_UPLOAD_DISCIPLINE_PROMPT: dict[str, str] = {
    "arquitectura": (
        "CONTEXTO DE SUBIDA (prioridad): esta corrida es ARQUITECTURA / terminaciones. "
        "Usa plan_type=architectural si la hoja es planta arquitectónica, alzados, acabados o instalaciones "
        "dibujadas en arquitectura. No reclasifiques la disciplina solo por capas CAD que suenen "
        "estructurales (pueden ser XREF o fondo). structural_elements solo como referencia ligera según reglas."
    ),
    "estructura": (
        "CONTEXTO DE SUBIDA (prioridad): esta corrida es ESTRUCTURA. "
        "Prioriza structural_elements (rotulos C1, V1, tablas de columnas/vigas, secciones, f'c visible). "
        "Si falta armado en la imagen, missing_detail_sheets=true sin inventar."
    ),
    "electrico": (
        "CONTEXTO DE SUBIDA (prioridad): esta corrida es INSTALACIONES ELÉCTRICAS. "
        "Completa el array electrical con conteos; plan_type puede ser electrical."
    ),
    "sanitario": (
        "CONTEXTO DE SUBIDA (prioridad): esta corrida es INSTALACIONES SANITARIAS / plomería. "
        "Completa plumbing y fixtures; plan_type puede ser plumbing."
    ),
}


def _cad_suggests_structural(cad_summary: dict[str, Any]) -> bool:
    """True si capas o nombres del resumen CAD parecen plano estructural (Gebsa / genérico)."""
    hints = cad_summary.get("inventory_hints") or {}
    layers = [str(x).lower() for x in (hints.get("layer_names") or [])]
    blob = " ".join(layers)
    markers = (
        "colum", "column", "viga", "beam", "estruct", "struct", "concret", "hormig",
        "refuerz", "armad", "despiece", "detalle", "elev", "fund",
    )
    return any(m in blob for m in markers)


def format_cad_facts_for_prompt(cad_summary: dict[str, Any]) -> str:
    if not cad_summary:
        return "No CAD facts were provided."

    cad_facts = cad_summary.get("cad_facts", {})
    inventory_hints = cad_summary.get("inventory_hints", {})
    lines: list[str] = []

    layer_names = inventory_hints.get("layer_names", [])
    if layer_names:
        lines.append("Layer names:")
        lines.extend(f"- {layer_name}" for layer_name in layer_names[:40])

    dimensions = inventory_hints.get("scale_dimensions", [])
    if dimensions:
        lines.append("Scale and dimension hints:")
        for item in dimensions[:12]:
            lines.append(
                f"- layer={item.get('layer')} measurement={item.get('measurement')} text={item.get('text')}"
            )

    block_frequency = inventory_hints.get("block_frequency", [])
    if block_frequency:
        lines.append("Block frequency hints:")
        for item in block_frequency[:12]:
            lines.append(f"- {item.get('block_name')}: {item.get('count')}")

    hatches = cad_facts.get("hatches", [])
    if hatches:
        lines.append("Hatch hints:")
        for hatch in hatches[:10]:
            lines.append(
                f"- layer={hatch.get('layer')} area={hatch.get('area')} pattern={hatch.get('pattern_name')}"
            )

    texts = cad_facts.get("texts", [])
    if texts:
        lines.append("Text markers:")
        for text in texts[:12]:
            lines.append(f"- layer={text.get('layer')} content={text.get('content')}")

    return "\n".join(lines)


_COERCIBLE_VISION_LIST_KEYS: tuple[str, ...] = (
    "walls",
    "doors",
    "windows",
    "structural_elements",
    "wet_areas",
    "kitchens",
    "stairs",
    "electrical",
    "plumbing",
    "fixtures",
    "floor_finishes",
    "ceiling_finishes",
    "exterior_works",
    "annotations_and_notes",
)


def _coerce_vision_list(value: Any) -> list[Any]:
    """Vision sometimes nests lists as {\"items\": [...]}; normalize to a flat list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "tipos", "types", "rows", "elements", "entries"):
            inner = value.get(key)
            if isinstance(inner, list):
                return inner
        return [value]
    return []


def _normalize_simple_inventory_lists(simple: dict[str, Any]) -> dict[str, Any]:
    out = dict(simple)
    for key in _COERCIBLE_VISION_LIST_KEYS:
        if key in out:
            out[key] = _coerce_vision_list(out[key])
    return out


def _should_run_structural_table_focus(
    cad_summary: dict[str, Any],
    upload_discipline_id: str | None,
) -> bool:
    uid_raw = (upload_discipline_id or "").strip().lower()
    uid = _UPLOAD_DISCIPLINE_ALIASES.get(uid_raw, uid_raw)
    return uid == "estructura" or _cad_suggests_structural(cad_summary)


def _merge_structural_focus_payload(
    base_payload: dict[str, Any],
    focused_payload: dict[str, Any],
) -> dict[str, Any]:
    if not focused_payload or focused_payload.get("parse_error"):
        return base_payload
    merged = _normalize_simple_inventory_lists(base_payload)
    focused = _normalize_simple_inventory_lists(focused_payload)
    existing_rows = merged.setdefault("structural_elements", [])
    existing_keys = {
        (
            str(row.get("id") or "").strip().lower(),
            str(row.get("type") or "").strip().lower(),
            str(row.get("schedule_row_text") or "").strip().lower(),
        )
        for row in existing_rows
        if isinstance(row, dict)
    }
    additions = []
    for row in focused.get("structural_elements") or []:
        if not isinstance(row, dict):
            continue
        key = (
            str(row.get("id") or "").strip().lower(),
            str(row.get("type") or "").strip().lower(),
            str(row.get("schedule_row_text") or "").strip().lower(),
        )
        if key in existing_keys:
            continue
        additions.append(row)
        existing_keys.add(key)
    if additions:
        existing_rows.extend(additions)
        notes = merged.setdefault("annotations_and_notes", [])
        notes.append({
            "text": "structural_table_focus",
            "interpretation": f"{len(additions)} structural schedule rows merged from high-reasoning focus pass.",
        })
    return merged


def _analyze_structural_table_focus(
    *,
    image_path: Path,
    image_b64: str,
    mime: str,
    cad_summary: dict[str, Any],
    level_name: str,
    model: str,
) -> dict[str, Any]:
    cad_hints = format_cad_facts_for_prompt(cad_summary)
    prompt = f"""Lee SOLO cuadros, tablas y detalles estructurales visibles en esta hoja para presupuesto.

Nivel: {level_name}

CAD hints:
{cad_hints}

Devuelve JSON valido con esta forma minima:
{{
  "plan_type": "structural|detail|combined",
  "structural_elements": [
    {{
      "id": "rotulo exacto C1/V1/Z1/etc",
      "type": "column|beam|slab|footing|shear_wall|lintel|tie_beam",
      "count": <integer>,
      "section_width_m": <number or null>,
      "section_height_m": <number or null>,
      "section_diameter_m": <number or null>,
      "cross_section_shape": "rectangular|circular|other|null",
      "length_m": <number or null>,
      "area_m2": <number or null>,
      "material": "concrete|steel|masonry|other",
      "has_reinforcement": true/false,
      "formwork_hint": "ninguno|formaleta|molde_bloque|null",
      "reinforcement_visible": true/false,
      "spec_source": "schedule_table|detail_callout|dimension_on_plan|legend_only|unknown",
      "schedule_row_text": "<texto literal de la fila de tabla si aplica, o null>",
      "missing_detail_sheets": true/false,
      "notes": "<evidencia breve o null>"
    }}
  ],
  "annotations_and_notes": []
}}

Para zapatas usa section_width_m=B, length_m=L y section_height_m=h. No inventes acero: si el armado no es visible, reinforcement_visible=false y missing_detail_sheets=true.
Return ONLY valid JSON."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SIMPLE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{image_b64}",
                        "detail": "high",
                    },
                },
            ],
        },
    ]
    retryable_statuses = {408, 409, 429, 500, 502, 503, 504}
    max_retries = _vision_max_retries()
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        client, api_key = _get_client_with_key()
        try:
            response = _vision_chat_completion(
                client,
                model=model,
                messages=messages,
                reasoning_effort="high",
            )
            return _extract_json(response.choices[0].message.content or "")
        except Exception as exc:
            last_exc = exc
            status_code = _exception_status_code(exc)
            if status_code == 429:
                _get_key_manager().mark_rate_limited(api_key)
            is_retryable = status_code in retryable_statuses or status_code is None
            if attempt >= max_retries or not is_retryable:
                logger.warning("Structural table focus pass failed for %s: %s", image_path.name, exc)
                return {"error": str(exc), "file": image_path.name}
            delay = min(
                20.0,
                _vision_retry_base_seconds() * (2 ** (attempt - 1)) + random.random(),
            )
            logger.warning(
                "Structural table focus retry %d/%d in %.2fs (image=%s status=%s)",
                attempt,
                max_retries,
                delay,
                image_path.name,
                status_code or "unknown",
            )
            time.sleep(delay)
    return {"error": str(last_exc), "file": image_path.name}


def _substitute_discipline_prompt_placeholders(
    template: str,
    *,
    view_type: str,
    level_name: str,
    methodology_block: str,
    cad_hints: str,
    upload_block: str,
    schema_text: str,
) -> str:
    """Replace {placeholders} in user_prompt.md without interpreting JSON braces in schema."""
    text = template.replace("{view_type}", view_type)
    text = text.replace("{level_name}", level_name)
    text = text.replace("{methodology_block}", methodology_block)
    text = text.replace("{upload_block}", upload_block)
    text = text.replace("{cad_hints}", cad_hints)
    text = text.replace("{schema}", schema_text)
    return text


def _discipline_prompt_md_path(upload_discipline_id: str | None) -> Path | None:
    uid_raw = (upload_discipline_id or "").strip().lower()
    if not uid_raw:
        return None
    uid = _UPLOAD_DISCIPLINE_ALIASES.get(uid_raw, uid_raw)
    path = _REPO_ROOT / "knowledge" / "prompts" / uid / "user_prompt.md"
    return path if path.is_file() else None


def _build_simple_user_prompt(
    image_path: Path,
    level_name: str,
    cad_summary: dict[str, Any],
    *,
    office_methodology: str | None = None,
    upload_discipline_id: str | None = None,
) -> str:
    view_type = _detect_view_type(image_path)
    cad_hints = format_cad_facts_for_prompt(cad_summary)
    methodology_block = ""
    if office_methodology and office_methodology.strip():
        trimmed = office_methodology.strip()
        if len(trimmed) > _MAX_OFFICE_METHODOLOGY_CHARS:
            logger.warning(
                "Office methodology truncated: %d → %d chars",
                len(trimmed),
                _MAX_OFFICE_METHODOLOGY_CHARS,
            )
            trimmed = trimmed[:_MAX_OFFICE_METHODOLOGY_CHARS] + "\n\n[... texto truncado por límite ...]"
        methodology_block = f"""METODOLOGÍA DE OFICINA (criterio del presupuestista — prioridad al interpretar notas y desgloses):
{trimmed}

---

"""

    upload_block = ""
    uid_raw = (upload_discipline_id or "").strip().lower()
    uid = _UPLOAD_DISCIPLINE_ALIASES.get(uid_raw, uid_raw)
    if uid:
        hint = _UPLOAD_DISCIPLINE_PROMPT.get(uid, "")
        if hint:
            upload_block = f"{hint}\n\n"

    structural_cad_hint = ""
    # Solo sugerimos estructura por capas si el usuario NO fijó ya una disciplina distinta.
    if uid not in {"arquitectura", "electrico", "sanitario"} and _cad_suggests_structural(cad_summary):
        structural_cad_hint = (
            "\nNOTA (CAD): el resumen de capas sugiere contenido estructural — prioriza CUADROS/TABLAS, "
            "rotulos (C1, V1…) y leyendas de hormigón si encajan con lo visible en la imagen.\n"
        )

    cad_hints_combined = cad_hints + structural_cad_hint

    md_path = _discipline_prompt_md_path(upload_discipline_id)
    if md_path is not None:
        try:
            template = md_path.read_text(encoding="utf-8")
            if template.strip():
                logger.info("Vision user prompt: using discipline template %s", md_path)
                return _substitute_discipline_prompt_placeholders(
                    template,
                    view_type=view_type,
                    level_name=level_name,
                    methodology_block=methodology_block,
                    cad_hints=cad_hints_combined,
                    upload_block=upload_block,
                    schema_text=_SIMPLE_SCHEMA_HINT,
                ).strip()
        except OSError as exc:
            logger.warning("Could not read discipline prompt %s: %s — using built-in prompt.", md_path, exc)

    return f"""ANALIZA este plano ({view_type}) del nivel: {level_name}

{methodology_block}{upload_block}DATOS DEL CAD (úsalos para verificar y complementar lo que ves):
{cad_hints_combined}
INSTRUCCIONES DE EXTRACCIÓN EXHAUSTIVA:

1. ESTRUCTURA: Si el plano es ARQUITECTÓNICO, las columnas/vigas visibles van en structural_elements solo como referencia (sección si está en la hoja); no inventes armados. Si el plano es ESTRUCTURAL o un CUADRO/TABLA de columnas-vigas, llena structural_elements con máximo detalle: id = rotulo del dibujo (C1, C-1…), spec_source, schedule_row_text si hay tabla, reinforcement_visible según lo que veas; si falta despiece de acero, missing_detail_sheets=true.

2. MUROS: Diferencia CADA tipo: bloque 6" (B-6, 0.15m), bloque 8" (B-8, 0.20m), 
   concreto armado (muro cortante), drywall. Mide longitudes de las cotas o estima 
   por escala. Indica interior/exterior.

3. ACABADOS DE MUROS: Si ves notas de "pañete", "empañete", "fraguache", "repello" = 
   plaster. Si ves "cerámica" o "azulejo" = ceramic_tile. Indica ambas caras si aplica.

4. PUERTAS: CADA tipo por separado (principal, interiores, baño, servicio, closet). 
   Lee dimensiones de las cotas (ancho x alto). Material si visible.

5. VENTANAS: CADA tipo (corrediza, fija, celosía, proyectante). Dimensiones de cotas.

6. BAÑOS: Para CADA baño cuenta: inodoro, lavamanos, ducha/tina, gabinete, espejo, 
   accesorios. Nota acabados (cerámica piso, cerámica pared, pintura).

7. COCINA: Gabinetes superiores e inferiores, tope, fregadero, conexión gas.

8. PISOS: Tipo de acabado por zona (porcelanato sala, cerámica baño, etc.). Área si 
   hay cotas.

9. CIELOS: Tipo (yeso, suspendido, expuesto) por zona.

10. ELÉCTRICO: Cuenta CADA punto: tomacorrientes 110V, 220V, interruptores (sencillo, 
    doble, triple), luminarias (techo, pared, empotradas), salidas de datos, TV, 
    teléfono, panel de breakers, timbres, detectores de humo, abanicos, A/C.

11. SANITARIO/PLOMERÍA: Puntos de agua, desagües, ventilaciones, registros, válvulas, 
    conexión calentador, conexión lavadora, llaves de paso, medidor, cisterna, bomba.

12. ESCALERAS: Tipo, material, ancho, número de peldaños, barandas.

13. EXTERIORES: Aceras, rampas, muros de contención, cercas, portones, estacionamiento.

14. ANOTACIONES: Lee TODAS las notas y textos relevantes del plano. Interpreta su 
    significado para cuantificación.

15. ZAPATAS: extrae B, L y h explicitos. Usa section_width_m=B, length_m=L y
    section_height_m=h; no reemplaces B y L por solo area_m2.

Devuelve este JSON EXACTO (sin texto adicional):
{_SIMPLE_SCHEMA_HINT}"""


# ---------------------------------------------------------------------------
# Step 2: Python adapter — simple dict → LevelInventory-compatible dict
# ---------------------------------------------------------------------------

def _simple_to_level_inventory(
    simple: dict[str, Any],
    level_name: str,
    level_id: str,
    image_name: str,
) -> dict[str, Any]:
    """Convert simple vision JSON inventory to a LevelInventory-compatible dict."""
    simple = _normalize_simple_inventory_lists(simple)
    page_slug = Path(image_name).stem  # e.g. "page_0001"

    _BLOCK_THICKNESS: dict[str, float] = {
        "block_6in": 0.15, "block_8in": 0.20, "block_4in": 0.10,
    }

    walls: list[dict[str, Any]] = []
    for i, w in enumerate(simple.get("walls") or [], 1):
        raw_material = w.get("material") or "other"
        thickness = w.get("thickness_m")
        if thickness is None:
            thickness = _BLOCK_THICKNESS.get(raw_material)

        material_hint = raw_material
        if raw_material.startswith("block_"):
            material_hint = "masonry"

        wall_system = None
        if raw_material.startswith("block_"):
            wall_system = "masonry_wall"
        elif raw_material == "concrete":
            wall_system = "concrete_wall"
        elif raw_material == "drywall":
            wall_system = "drywall_partition"

        wall_id = w.get("id") or f"vis-wall-{i:02d}"
        wall_typology = (
            (w.get("wall_typology") or w.get("tipo") or w.get("type_label") or "").strip() or None
        )
        walls.append(
            {
                "id": wall_id,
                "source": "vision",
                "source_layers": [],
                "source_refs": [f"vision:{image_name}:wall_{i}"],
                "assumptions": ["Dimensions extracted from plan analysis."],
                "inputs": {
                    "raw": w,
                    "wall_typology": wall_typology,
                    "finish_interior": w.get("finish_interior"),
                    "finish_exterior": w.get("finish_exterior"),
                    "original_material_code": raw_material,
                    "is_concrete_shear_wall": bool(w.get("is_concrete_shear_wall")),
                },
                "conflict_notes": [],
                "length_m": w.get("estimated_length_m"),
                "height_m": w.get("height_m"),
                "thickness_m": thickness,
                "area_m2": w.get("estimated_area_m2"),
                "material_hint": material_hint,
                "wall_system": wall_system,
                "interior_exterior_hint": (
                    w.get("location") if w.get("location") in {"interior", "exterior"} else None
                ),
                "structural": w.get("structural") or False,
                "finish_required": True,
                "confidence": score_vision_entity(w).score,
                "evidence": [
                    f"Wall identified: material={raw_material}, location={w.get('location')}, "
                    f"thickness={thickness}m, length={w.get('estimated_length_m')}m."
                ],
            }
        )

    doors: list[dict[str, Any]] = []
    for i, d in enumerate(simple.get("doors") or [], 1):
        count = d.get("count")
        door_id_raw = str(d.get("id") or "").strip()
        door_id = (
            door_id_raw
            if door_id_raw and not door_id_raw.lower().startswith("vis-door-")
            else f"vis-door-{i:02d}"
        )
        doors.append(
            {
                "id": door_id,
                "source": "vision",
                "source_layers": [],
                "source_refs": [f"vision:{image_name}:door_{i}"],
                "assumptions": [],
                "inputs": {
                    "raw": d,
                    "door_label": (d.get("label") or "").strip() or None,
                },
                "conflict_notes": [],
                "count": int(count) if count is not None else 1,
                "width_m": d.get("width_m"),
                "height_m": d.get("height_m"),
                "type_hint": d.get("type"),
                "material_hint": d.get("material"),
                "confidence": score_vision_entity(d).score,
                "evidence": [
                    f"Counted from plan image: type={d.get('type')}, count={d.get('count')}."
                ],
            }
        )

    windows: list[dict[str, Any]] = []
    for i, w in enumerate(simple.get("windows") or [], 1):
        count = w.get("count")
        win_id_raw = str(w.get("id") or "").strip()
        win_id = (
            win_id_raw
            if win_id_raw and not win_id_raw.lower().startswith("vis-window-")
            else f"vis-window-{i:02d}"
        )
        windows.append(
            {
                "id": win_id,
                "source": "vision",
                "source_layers": [],
                "source_refs": [f"vision:{image_name}:window_{i}"],
                "assumptions": [],
                "inputs": {
                    "raw": w,
                    "window_label": (w.get("label") or "").strip() or None,
                },
                "conflict_notes": [],
                "count": int(count) if count is not None else 1,
                "width_m": w.get("width_m"),
                "height_m": w.get("height_m"),
                "type_hint": w.get("type"),
                "confidence": score_vision_entity(w).score,
                "evidence": [
                    f"Counted from plan image: type={w.get('type')}, count={w.get('count')}."
                ],
            }
        )

    wet_areas: list[dict[str, Any]] = []
    for i, a in enumerate(simple.get("wet_areas") or [], 1):
        count = a.get("count")
        wet_areas.append(
            {
                "id": f"vis-wetarea-{i:02d}",
                "source": "vision",
                "source_refs": [f"vision:{image_name}:wetarea_{i}"],
                "assumptions": [],
                "inputs": {"raw": a},
                "conflict_notes": [],
                "kind": a.get("kind") or "bathroom",
                "count": int(count) if count is not None else 1,
                "estimated_area_m2": a.get("area_m2"),
                "confidence": score_vision_entity(a).score,
                "evidence": [
                    f"Identified from plan image: kind={a.get('kind')}, count={a.get('count')}."
                ],
            }
        )

    kitchens: list[dict[str, Any]] = []
    for i, k in enumerate(simple.get("kitchens") or [], 1):
        count = k.get("count")
        kitchens.append(
            {
                "id": f"vis-kitchen-{i:02d}",
                "source": "vision",
                "source_refs": [f"vision:{image_name}:kitchen_{i}"],
                "assumptions": [],
                "inputs": {"raw": k},
                "conflict_notes": [],
                "count": int(count) if count is not None else 1,
                "estimated_area_m2": k.get("area_m2"),
                "confidence": score_vision_entity(k).score,
                "evidence": ["Kitchen identified from plan image."],
            }
        )

    stairs: list[dict[str, Any]] = []
    for i, s in enumerate(simple.get("stairs") or [], 1):
        count = s.get("count")
        stairs.append(
            {
                "id": f"vis-stair-{i:02d}",
                "source": "vision",
                "source_refs": [f"vision:{image_name}:stair_{i}"],
                "assumptions": [],
                "inputs": {"raw": s},
                "conflict_notes": [],
                "count": int(count) if count is not None else 1,
                "flights": s.get("flights"),
                "width_m": s.get("width_m"),
                "confidence": score_vision_entity(s).score,
                "evidence": ["Stair identified from plan image."],
            }
        )

    structural_elements: list[dict[str, Any]] = []
    for i, e in enumerate(simple.get("structural_elements") or [], 1):
        etype = e.get("type") or "other"
        raw_count = e.get("count")
        material = e.get("material") or ("concrete" if etype in {"column", "beam", "slab", "footing", "shear_wall", "lintel", "tie_beam"} else None)
        notation = str(e.get("id") or e.get("tipo") or e.get("label") or "").strip()
        elem_id = notation if notation and not notation.lower().startswith("vis-") else f"vis-{etype}-{i:02d}"

        concrete_grade = e.get("concrete_grade")
        concrete_grade_hint = None
        if concrete_grade and concrete_grade != "null":
            concrete_grade_hint = concrete_grade.replace("fc_", "fc'=").replace("_", " ")

        reinf_visible = e.get("reinforcement_visible")
        missing_sheets = bool(e.get("missing_detail_sheets"))
        assumptions: list[str] = []
        if missing_sheets:
            assumptions.append(
                "Armado o despiece no visible en esta imagen: no inferir acero desde Vision sola."
            )
        if reinf_visible is False and (e.get("has_reinforcement") or material == "concrete"):
            assumptions.append(
                "Hormigón/refuerzo asumido por tipo de elemento; detalle de armado no legible en la hoja."
            )

        structural_elements.append(
            {
                "id": elem_id,
                "source": "vision",
                "source_refs": [f"vision:{image_name}:{etype}_{i}"],
                "assumptions": assumptions,
                "inputs": {
                    "raw": e,
                    "notation": notation,
                    "structural_label": notation or None,
                    "concrete_grade_raw": concrete_grade,
                    "spec_source": e.get("spec_source"),
                    "schedule_row_text": e.get("schedule_row_text"),
                    "formwork_hint": e.get("formwork_hint"),
                    "reinforcement_visible": reinf_visible,
                    "missing_detail_sheets": missing_sheets,
                    "notes": e.get("notes"),
                },
                "conflict_notes": [],
                "element_type": etype if etype not in {"shear_wall", "lintel", "tie_beam"} else "other",
                "count": int(raw_count) if raw_count is not None else 1,
                "area_m2": e.get("area_m2"),
                "length_m": e.get("length_m"),
                "span_m": e.get("span_m"),
                "cross_section_shape": e.get("cross_section_shape"),
                "section_diameter_m": e.get("section_diameter_m"),
                "section_width_m": e.get("section_width_m"),
                "section_height_m": e.get("section_height_m"),
                "material_hint": material,
                "reinforcement_hint": "reinforced" if material == "concrete" or e.get("has_reinforcement") else None,
                "concrete_grade_hint": concrete_grade_hint,
                "confidence": score_vision_entity(e).score,
                "evidence": [
                    f"Structural element from plan: notation={notation}, type={etype}, "
                    f"section={e.get('section_width_m')}x{e.get('section_height_m')}m, "
                    f"material={material}, count={raw_count}, "
                    f"spec_source={e.get('spec_source')}, reinforcement_visible={reinf_visible}."
                ],
            }
        )

    fixtures: list[dict[str, Any]] = []
    for i, f_item in enumerate(simple.get("fixtures") or [], 1):
        count = f_item.get("count")
        fixtures.append(
            {
                "id": f"{page_slug}-fixture-{i:02d}",
                "source": "vision",
                "source_refs": [f"vision:{image_name}:fixture_{i}"],
                "assumptions": [],
                "inputs": {
                    "raw": f_item,
                    "fixture_label": (f_item.get("label") or "").strip() or None,
                },
                "conflict_notes": [],
                "fixture_type": f_item.get("type") or "other",
                "count": int(count) if count is not None else 1,
                "unit": "unit",
                "evidence": [f"Counted from plan image: type={f_item.get('type')}."],
            }
        )

    extra_fixtures: list[dict[str, Any]] = []

    for i, e in enumerate(simple.get("electrical") or [], 1):
        count = e.get("count")
        extra_fixtures.append(
            {
                "id": f"{page_slug}-elec-{i:02d}",
                "source": "vision",
                "source_refs": [f"vision:{image_name}:elec_{i}"],
                "assumptions": [],
                "inputs": {
                    "raw": e,
                    "discipline": "electrical",
                    "fixture_label": (e.get("label") or "").strip() or None,
                },
                "conflict_notes": [],
                "fixture_type": e.get("type") or "electrical_other",
                "count": int(count) if count is not None else 1,
                "unit": "unit",
                "location_hint": e.get("location"),
                "evidence": [f"Electrical element from plan: type={e.get('type')}, count={count}."],
            }
        )

    for i, p in enumerate(simple.get("plumbing") or [], 1):
        count = p.get("count")
        extra_fixtures.append(
            {
                "id": f"{page_slug}-plumb-{i:02d}",
                "source": "vision",
                "source_refs": [f"vision:{image_name}:plumb_{i}"],
                "assumptions": [],
                "inputs": {
                    "raw": p,
                    "discipline": "plumbing",
                    "fixture_label": (p.get("label") or "").strip() or None,
                    "pipe_diameter_in": p.get("pipe_diameter_in"),
                    "pipe_material": p.get("material"),
                },
                "conflict_notes": [],
                "fixture_type": p.get("type") or "plumbing_other",
                "count": int(count) if count is not None else 1,
                "unit": "unit",
                "location_hint": p.get("location"),
                "evidence": [f"Plumbing element from plan: type={p.get('type')}, count={count}."],
            }
        )

    for i, ext in enumerate(simple.get("exterior_works") or [], 1):
        qty = ext.get("quantity")
        extra_fixtures.append(
            {
                "id": f"{page_slug}-ext-{i:02d}",
                "source": "vision",
                "source_refs": [f"vision:{image_name}:ext_{i}"],
                "assumptions": [],
                "inputs": {
                    "raw": ext,
                    "discipline": "exterior",
                    "ext_unit": ext.get("unit"),
                    "ext_material": ext.get("material"),
                },
                "conflict_notes": [],
                "fixture_type": ext.get("type") or "exterior_other",
                "count": int(qty) if qty is not None else 1,
                "unit": ext.get("unit") or "unit",
                "location_hint": ext.get("id"),
                "evidence": [f"Exterior work from plan: type={ext.get('type')}."],
            }
        )

    all_fixtures = fixtures + extra_fixtures

    plan_type = simple.get("plan_type", "unknown")
    annotations = simple.get("annotations_and_notes") or []
    floor_finishes = simple.get("floor_finishes") or []
    ceiling_finishes = simple.get("ceiling_finishes") or []

    notes = [
        f"Plan type detected: {plan_type}.",
        "Exhaustive vision extraction — Python-adapted to LevelInventory schema.",
    ]
    for ann in annotations[:10]:
        text = ann.get("text", "")
        interp = ann.get("interpretation", "")
        if text:
            notes.append(f"Annotation: '{text}' → {interp}")

    system_notes: list[str] = []
    if floor_finishes:
        for ff in floor_finishes:
            system_notes.append(
                f"Floor finish: {ff.get('type', 'unknown')} at {ff.get('location', 'unknown')}"
                f" ({ff.get('area_m2', '?')} m2)"
            )
    if ceiling_finishes:
        for cf in ceiling_finishes:
            system_notes.append(
                f"Ceiling finish: {cf.get('type', 'unknown')} at {cf.get('location', 'unknown')}"
                f" ({cf.get('area_m2', '?')} m2)"
            )

    return {
        "level_id": level_id,
        "level_name": level_name,
        "source": "vision",
        "source_image": image_name,
        "source_view": plan_type,
        "floor_area_m2": simple.get("floor_area_m2"),
        "ceiling_area_m2": simple.get("floor_area_m2"),
        "walls": walls,
        "doors": doors,
        "windows": windows,
        "wet_areas": wet_areas,
        "kitchens": kitchens,
        "stairs": stairs,
        "structural_elements": structural_elements,
        "fixtures": all_fixtures,
        "openings": [],
        "conflict_notes": [],
        "source_refs": [f"vision:{image_name}"],
        "assumptions": ["Quantities extracted from exhaustive visual plan analysis."],
        "inputs": {
            "image": image_name,
            "plan_type": plan_type,
            "floor_finishes": floor_finishes,
            "ceiling_finishes": ceiling_finishes,
            "annotations": annotations,
        },
        "system_notes": system_notes,
        "notes": notes,
    }


def _build_cross_checks(level_inventory: LevelInventory, cad_summary: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    block_frequency = {
        item["block_name"].lower(): item["count"]
        for item in cad_summary.get("inventory_hints", {}).get("block_frequency", [])
        if item.get("block_name")
    }

    if level_inventory.doors:
        door_count = sum(max(door.count, 0) for door in level_inventory.doors)
        block_hint = sum(
            count for name, count in block_frequency.items() if "door" in name or "puert" in name
        )
        checks.append(
            {
                "check": "door_inventory_vs_block_hints",
                "vision_count": door_count,
                "cad_block_hint": block_hint,
                "status": "info",
            }
        )

    if level_inventory.windows:
        window_count = sum(max(window.count, 0) for window in level_inventory.windows)
        block_hint = sum(
            count
            for name, count in block_frequency.items()
            if "window" in name or "vent" in name
        )
        checks.append(
            {
                "check": "window_inventory_vs_block_hints",
                "vision_count": window_count,
                "cad_block_hint": block_hint,
                "status": "info",
            }
        )

    return checks


def analyze_plan(
    image_path: Path,
    cad_summary: dict[str, Any],
    level_name: str,
    *,
    office_methodology: str | None = None,
    upload_discipline_id: str | None = None,
) -> dict[str, Any]:
    """Cached wrapper around the vision call.

    Cache key fingerprints the things that change the model output:
    image bytes, model id, prompt version, discipline, and a short hash of the
    methodology block. CAD summary is intentionally excluded because it only
    feeds prompt context for cross-checks — those are rebuilt post-cache.
    """
    from core.stage_cache import cached_stage, compose_key, sha256_bytes, sha256_json

    image_path = Path(image_path).resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    image_bytes = image_path.read_bytes()
    # All variable-length user data (level names, methodology blocks, free-form
    # CAD-derived strings) MUST be hashed before being added to the cache key.
    # The composed key is also hashed before becoming an on-disk filename, but
    # callers should not rely on that — keep variable segments short here so the
    # composed key stays diagnosable in logs.
    cache_key = compose_key(
        sha256_bytes(image_bytes),
        vision_model_id(),
        VISION_PROMPT_VERSION,
        upload_discipline_id or "any",
        sha256_json(office_methodology or "")[:16],
        sha256_json(level_name or "")[:16],
    )

    def _compute() -> dict[str, Any]:
        return _analyze_plan_uncached(
            image_path,
            cad_summary,
            level_name,
            office_methodology=office_methodology,
            upload_discipline_id=upload_discipline_id,
        )

    return cached_stage("vision_analyze_plan", cache_key, _compute)


def detect_level_marker(cad_summary: dict[str, Any]) -> str | None:
    """Resolve the first real CAD level marker, when normalized CAD exposes one."""
    markers = cad_summary.get("inventory_hints", {}).get("level_markers", [])
    for marker in markers:
        if isinstance(marker, dict):
            value = marker.get("content") or marker.get("label") or marker.get("text")
        else:
            value = marker
        text = str(value or "").strip()
        if text:
            return text
    return None


_LEVEL_LABEL_PATTERN = re.compile(
    r"^(n[+\-]?\d|nivel|level|piso|planta|sotano|techo|cubierta)",
    re.IGNORECASE,
)


def _is_acceptable_level_label(text: str) -> bool:
    """True when text looks like a level label (e.g. "Nivel 1", "N+0.00"), not a
    free-form CAD annotation that just happened to land in the level_markers
    list. Annotations like "El nivel de desplante sera de 0.80m..." used to leak
    in and blow past NAME_MAX once concatenated into the cache key."""
    if not text or len(text) > 40:
        return False
    return _LEVEL_LABEL_PATTERN.match(text) is not None


def _resolve_vision_level_name(cad_summary: dict[str, Any]) -> str:
    markers = cad_summary.get("inventory_hints", {}).get("level_markers", [])
    for marker in markers:
        if isinstance(marker, dict):
            value = marker.get("content") or marker.get("label") or marker.get("text")
        else:
            value = marker
        text = str(value or "").strip()
        if _is_acceptable_level_label(text):
            return text
    return "level_01"


async def analyze_plan_async(
    image_path: Path,
    cad_summary: dict[str, Any],
    level_name: str,
    *,
    office_methodology: str | None = None,
    upload_discipline_id: str | None = None,
) -> dict[str, Any]:
    """Async wrapper for the sync OpenAI client path."""
    return await asyncio.to_thread(
        analyze_plan,
        image_path,
        cad_summary,
        level_name,
        office_methodology=office_methodology,
        upload_discipline_id=upload_discipline_id,
    )


def _analyze_plan_uncached(
    image_path: Path,
    cad_summary: dict[str, Any],
    level_name: str,
    *,
    office_methodology: str | None = None,
    upload_discipline_id: str | None = None,
) -> dict[str, Any]:
    image_path = Path(image_path).resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    image_b64 = encode_image(image_path)
    extension = image_path.suffix.lower().replace(".", "")
    mime = f"image/{extension}" if extension in {"png", "jpg", "jpeg", "webp"} else "image/png"

    model = vision_model_id()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SIMPLE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": _build_simple_user_prompt(
                        image_path,
                        level_name,
                        cad_summary,
                        office_methodology=office_methodology,
                        upload_discipline_id=upload_discipline_id,
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{image_b64}",
                        "detail": "high",
                    },
                },
            ],
        },
    ]
    retryable_statuses = {408, 409, 429, 500, 502, 503, 504}
    max_retries = _vision_max_retries()
    last_exc: Exception | None = None
    response = None

    for attempt in range(1, max_retries + 1):
        client, api_key = _get_client_with_key()
        try:
            response = _vision_chat_completion(client, model=model, messages=messages)
            break
        except Exception as exc:
            last_exc = exc
            status_code = _exception_status_code(exc)
            if status_code == 429:
                _get_key_manager().mark_rate_limited(api_key)

            is_retryable = status_code in retryable_statuses or status_code is None
            if attempt >= max_retries or not is_retryable:
                raise

            delay = min(
                20.0,
                _vision_retry_base_seconds() * (2 ** (attempt - 1)) + random.random(),
            )
            logger.warning(
                "Vision retry %d/%d in %.2fs (image=%s status=%s)",
                attempt,
                max_retries,
                delay,
                image_path.name,
                status_code or "unknown",
            )
            time.sleep(delay)

    if response is None:
        raise RuntimeError("Vision completion failed without a response") from last_exc

    raw_text = response.choices[0].message.content or ""
    simple_payload = _extract_json(raw_text)

    if simple_payload.get("parse_error"):
        return {
            "parse_error": True,
            "raw_text": raw_text,
            "_metadata": {
                "file": image_path.name,
                "timestamp": datetime.now().isoformat(),
                "model": model,
            },
        }

    # Step 2: Python adapter converts simple dict → full LevelInventory dict
    if _should_run_structural_table_focus(cad_summary, upload_discipline_id):
        focused_payload = _analyze_structural_table_focus(
            image_path=image_path,
            image_b64=image_b64,
            mime=mime,
            cad_summary=cad_summary,
            level_name=level_name,
            model=model,
        )
        simple_payload = _merge_structural_focus_payload(simple_payload, focused_payload)

    level_id = level_name.lower().replace(" ", "_")
    adapted = _simple_to_level_inventory(simple_payload, level_name, level_id, image_path.name)

    level_inventory = level_inventory_from_dict(adapted, default_source="vision")
    result = level_inventory.to_dict()
    result["cad_cross_checks"] = _build_cross_checks(level_inventory, cad_summary)
    result["_raw_response"] = raw_text
    result["_simple_payload"] = simple_payload
    result["_metadata"] = {
        "file": image_path.name,
        "timestamp": datetime.now().isoformat(),
        "office_methodology_chars": len(office_methodology or ""),
        "model": model,
        "upload_discipline_id": upload_discipline_id,
    }
    return result


def run_full_vision_analysis(
    pages_dir: str,
    cad_summary: dict[str, Any],
    *,
    office_methodology: str | None = None,
    upload_discipline_id: str | None = None,
) -> list[dict[str, Any]]:
    return asyncio.run(
        _run_full_vision_analysis_async(
            pages_dir,
            cad_summary,
            office_methodology=office_methodology,
            upload_discipline_id=upload_discipline_id,
        )
    )


async def _run_full_vision_analysis_async(
    pages_dir: str,
    cad_summary: dict[str, Any],
    *,
    office_methodology: str | None = None,
    upload_discipline_id: str | None = None,
) -> list[dict[str, Any]]:
    pages_path = Path(pages_dir)
    images = sorted(
        path for path in pages_path.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    level_name = _resolve_vision_level_name(cad_summary)
    semaphore = asyncio.Semaphore(_vision_concurrency())

    async def analyze_image(image_path: Path) -> dict[str, Any]:
        async with semaphore:
            logger.info(
                "Vision analyzing %s as level=%s discipline=%s",
                image_path.name,
                level_name,
                upload_discipline_id or "any",
            )
            return await analyze_plan_async(
                image_path,
                cad_summary,
                level_name,
                office_methodology=office_methodology,
                upload_discipline_id=upload_discipline_id,
            )

    async def guarded(image_path: Path) -> dict[str, Any]:
        try:
            return await analyze_image(image_path)
        except Exception as exc:  # pragma: no cover - depends on external API/runtime
            logger.warning("Vision failed for %s: %s", image_path.name, exc, exc_info=True)
            return {"error": str(exc), "file": image_path.name}

    return await asyncio.gather(*(guarded(image_path) for image_path in images))


if __name__ == "__main__":
    json_path = Path("resumen_procesado.json") if Path("resumen_procesado.json").exists() else Path("../resumen_procesado.json")
    image_path = Path("vision_test_image.png")

    cad_summary: dict[str, Any] = {}
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as handle:
            cad_summary = json.load(handle)

    if image_path.exists():
        result = analyze_plan(
            image_path,
            cad_summary,
            level_name=image_path.stem,
            office_methodology=None,
            upload_discipline_id=None,
        )
        output_path = Path("vision_inventory_result.json")
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, ensure_ascii=False)
        print(f"Vision inventory written to {output_path}")
    else:
        print("Place a test image at ./vision_test_image.png to run the module directly.")
