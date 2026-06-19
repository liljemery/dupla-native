"""
Inventory merge helpers for the active APS/JSON-first pipeline.

Includes GPT-4o-assisted layer classification when token-based heuristics
cannot identify a layer's construction discipline.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import fields
from typing import Any, Iterable, Mapping, TypeVar

logger = logging.getLogger("dupla.inventory_builder")

from core.schemas import (
    Door,
    Fixture,
    InventoryEntity,
    InventorySource,
    Kitchen,
    LevelInventory,
    Opening,
    Stair,
    StructuralElement,
    Wall,
    WetArea,
    Window,
    level_inventory_from_dict,
)

EntityT = TypeVar("EntityT", bound=InventoryEntity)

_WALL_TOKENS = ("wall", "muro")
_FLOOR_TOKENS = ("floor", "flor", "piso", "slab", "losa")
_CEILING_TOKENS = ("ceiling", "clng", "cielo")
_DOOR_TOKENS = ("door", "puert")
_WINDOW_TOKENS = ("window", "vent", "glaz")
_BEAM_TOKENS = ("beam", "viga")
_COLUMN_TOKENS = ("column", "colum", "columna", "pillar", "pil")
_SLAB_TOKENS = ("slab", "losa")
_FOOTING_TOKENS = ("footing", "zapata", "foundation")
_STRUCTURAL_TOKENS = ("struct", "estruct", "load", "bearing", "portant")
_INTERIOR_TOKENS = ("interior", "int", "inside")
_EXTERIOR_TOKENS = ("exterior", "ext", "facade", "fachada", "outside")
_FINISH_TOKENS = ("finish", "acab", "paint", "tile", "rev")
_CONCRETE_TOKENS = ("concrete", "conc", "horm", "rc", "reinforced concrete")
_STEEL_TOKENS = ("steel", "acero", "metal", "stl")
_MASONRY_TOKENS = ("masonry", "block", "brick", "cmu", "ladr", "mamp")
_DRYWALL_TOKENS = ("drywall", "gypsum", "tablaroca", "yeso")
_WOOD_TOKENS = ("wood", "madera", "timber")

# Tokens that indicate a CAD layer is definitely NOT a wall.
# Used by the geometry fallback to prevent misclassification.
_NON_WALL_EXCLUDE_TOKENS = (
    # Electrical / MEP
    "cable", "cobre", "luces", "luz", "luminaria", "tomacorriente", "interruptor",
    "monofasica", "trifasica", "electric", "circuito", "panel", "tablero",
    "acometida", "telefono", "telefon", "data", "cctv", "sonido",
    # Plumbing / sanitary
    "agua", "sanitar", "plomer", "desague", "drenaje", "tuberia", "tubo",
    "bomba", "cisterna", "glp", "gas",
    # Annotations / text / symbols
    "texto", "text", "anndtobj", "anndttext", "annobj", "simbologia",
    "simbolo", "referencia", "tarjeta", "cartograf", "magenta",
    "detalles", "titulo", "cajetin", "leyenda", "nota", "cota", "dim",
    # Structural (already handled by structural builder)
    "viga", "beam", "columna", "column", "losa", "slab", "zapata", "footing",
    "cimiento", "fundacion", "foundation", "estribo", "acero",
    "est_secciones", "estructura", "estructur",
    # Furniture / fixtures / non-wall elements
    "closet", "mueble", "furn", "cocina", "kitchen", "escaler",
    "ascensor", "elevador", "elev-",
    # Site / landscape
    "solar", "solares", "vuelo", "relleno", "piso", "pisos",
    "borde", "topograf", "curva", "terreno", "mverde",
    # Fire / emergency
    "incendio", "emergencia", "evacuacion", "extintor",
    # Miscellaneous non-wall
    "misc", "hath", "grdutiy", "layer5", "tornillo", "soporte",
    "union", "cristal", "vidrio", "intermitente", "lineas tc",
    "cable-cobre", "cascaron", "david", "mb3", "mb",
    "din-sant", "_35", "w",
)

_SPACE_TYPE_TOKENS: dict[str, tuple[str, ...]] = {
    "bathroom": ("bath", "bano", "baño", "wc", "toilet"),
    "kitchen": ("kitchen", "cocina"),
    "bedroom": ("bedroom", "dorm", "habit"),
    "living_room": ("living", "estar", "sala"),
    "corridor": ("corridor", "hall", "pasillo", "circulation"),
    "laundry": ("laundry", "lavander", "lavado"),
    "office": ("office", "oficina"),
    "stair": ("stair", "escal"),
}


def _contains_token(value: str, tokens: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in tokens)


def _joined_hint_text(*values: Any) -> str:
    return " ".join(str(value).strip() for value in values if value).lower()


def _infer_material_hint(*values: Any) -> str | None:
    hint_text = _joined_hint_text(*values)
    if not hint_text:
        return None
    if _contains_token(hint_text, _CONCRETE_TOKENS):
        return "concrete"
    if _contains_token(hint_text, _STEEL_TOKENS):
        return "steel"
    if _contains_token(hint_text, _MASONRY_TOKENS):
        return "masonry"
    if _contains_token(hint_text, _DRYWALL_TOKENS):
        return "drywall"
    if _contains_token(hint_text, _WOOD_TOKENS):
        return "wood"
    return None


def _infer_wall_system_hint(*values: Any) -> str | None:
    hint_text = _joined_hint_text(*values)
    if not hint_text:
        return None
    if _contains_token(hint_text, _DRYWALL_TOKENS):
        return "drywall_partition"
    if _contains_token(hint_text, _MASONRY_TOKENS):
        return "masonry_wall"
    if _contains_token(hint_text, _CONCRETE_TOKENS):
        return "concrete_wall"
    if _contains_token(hint_text, _STEEL_TOKENS) and _contains_token(hint_text, _WALL_TOKENS):
        return "steel_stud_wall"
    return None


def _infer_interior_exterior_hint(*values: Any) -> str | None:
    hint_text = _joined_hint_text(*values)
    if not hint_text:
        return None
    if _contains_token(hint_text, _INTERIOR_TOKENS):
        return "interior"
    if _contains_token(hint_text, _EXTERIOR_TOKENS):
        return "exterior"
    return None


def _infer_finish_required(*values: Any) -> bool | None:
    hint_text = _joined_hint_text(*values)
    if not hint_text:
        return None
    if _contains_token(hint_text, _FINISH_TOKENS):
        return True
    return None


def _infer_load_bearing_hint(*values: Any) -> bool | None:
    hint_text = _joined_hint_text(*values)
    if not hint_text:
        return None
    if _contains_token(hint_text, _STRUCTURAL_TOKENS):
        return True
    return None


def _infer_reinforcement_hint(*values: Any) -> str | None:
    hint_text = _joined_hint_text(*values)
    if not hint_text:
        return None
    if "rebar" in hint_text or "armad" in hint_text or "reinf" in hint_text or "rc" in hint_text:
        return "reinforced"
    return None


def _infer_concrete_grade_hint(*values: Any) -> str | None:
    import re

    hint_text = _joined_hint_text(*values)
    if not hint_text:
        return None

    patterns = (
        r"\b(?:h|c)\s*[-/]?\s*(\d{2,3}(?:/\d{2})?)\b",
        r"\bf[' ]?c\s*[-/]?\s*(\d{2,3})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, hint_text, flags=re.IGNORECASE)
        if match:
            return match.group(0).upper().replace(" ", "")
    return None


def _infer_steel_grade_hint(*values: Any) -> str | None:
    import re

    hint_text = _joined_hint_text(*values)
    if not hint_text:
        return None

    patterns = (
        r"\bfy\s*[-/]?\s*(\d{3,4})\b",
        r"\ba\s*(36|572|992)\b",
        r"\bs\s*(275|355)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, hint_text, flags=re.IGNORECASE)
        if match:
            return match.group(0).upper().replace(" ", "")
    return None


def _infer_structural_element_type(*values: Any) -> str | None:
    hint_text = _joined_hint_text(*values)
    if not hint_text:
        return None
    if _contains_token(hint_text, _BEAM_TOKENS):
        return "beam"
    if _contains_token(hint_text, _COLUMN_TOKENS):
        return "column"
    if _contains_token(hint_text, _SLAB_TOKENS):
        return "slab"
    if _contains_token(hint_text, _FOOTING_TOKENS):
        return "footing"
    if _contains_token(hint_text, _WALL_TOKENS) and _contains_token(hint_text, _STRUCTURAL_TOKENS):
        return "wall"
    return None


def _extract_space_types(cad_facts: dict[str, Any]) -> list[str]:
    texts = cad_facts.get("cad_facts", {}).get("texts", [])
    detected: list[str] = []
    for text in texts:
        content = str(text.get("content", ""))
        for space_type, tokens in _SPACE_TYPE_TOKENS.items():
            if _contains_token(content, tokens):
                detected.append(space_type)
    return _unique_strings(detected)


def _unique_strings(*groups: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for item in group:
            if item and item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


def _merge_inputs(json_inputs: dict[str, Any], vision_inputs: dict[str, Any]) -> dict[str, Any]:
    if json_inputs and vision_inputs:
        return {"json": dict(json_inputs), "vision": dict(vision_inputs)}
    if json_inputs:
        return dict(json_inputs)
    if vision_inputs:
        return dict(vision_inputs)
    return {}


_OCR_AUTHORITATIVE_DIMENSION_FIELDS: frozenset[str] = frozenset(
    {
        "length_m",
        "height_m",
        "width_m",
        "thickness_m",
        "area_m2",
        "volume_m3",
        "section_width_m",
        "section_height_m",
        "span_m",
    }
)


def _scalar_merge(
    field_name: str,
    json_value: Any,
    vision_value: Any,
    conflict_notes: list[str],
    *,
    prefer_vision: bool = False,
) -> Any:
    if json_value is None:
        return vision_value
    if vision_value is None:
        return json_value
    if json_value == vision_value:
        return json_value

    if field_name in _OCR_AUTHORITATIVE_DIMENSION_FIELDS:
        from core.ocr_reconciler import reconcile

        result = reconcile(
            geometric_value=json_value,
            ocr_value=vision_value,
            label=field_name,
            unit="m2" if field_name == "area_m2" else ("m3" if field_name == "volume_m3" else "m"),
        )
        if result.override_note:
            conflict_notes.append(result.override_note)
        elif result.value == vision_value and json_value != vision_value:
            conflict_notes.append(
                f"Conflict on {field_name}: OCR ({vision_value!r}) confirmó dentro de tolerancia "
                f"frente a geometría ({json_value!r})."
            )
        return result.value if result.value is not None else json_value

    if prefer_vision:
        conflict_notes.append(
            f"Conflict on {field_name}: kept Vision value {vision_value!r}, JSON suggested {json_value!r}."
        )
        return vision_value

    conflict_notes.append(
        f"Conflict on {field_name}: kept JSON value {json_value!r}, vision suggested {vision_value!r}."
    )
    return json_value


def _merge_entity(
    json_entity: EntityT,
    vision_entity: EntityT,
    *,
    vision_preferred_fields: frozenset[str] | None = None,
) -> EntityT:
    payload: dict[str, Any] = {}
    conflict_notes = _unique_strings(json_entity.conflict_notes, vision_entity.conflict_notes)
    _vision_fields = vision_preferred_fields or frozenset()

    for field_def in fields(json_entity):
        name = field_def.name
        json_value = getattr(json_entity, name)
        vision_value = getattr(vision_entity, name)

        if name == "id":
            payload[name] = json_entity.id
        elif name == "level_id":
            payload[name] = json_entity.level_id or vision_entity.level_id
        elif name == "source":
            payload[name] = "hybrid"
        elif name in {"source_refs", "assumptions", "evidence", "conflict_notes"}:
            payload[name] = _unique_strings(json_value, vision_value)
        elif name == "inputs":
            payload[name] = _merge_inputs(json_value, vision_value)
        elif isinstance(json_value, list) and isinstance(vision_value, list):
            payload[name] = _unique_strings(json_value, vision_value)
        elif isinstance(json_value, dict) and isinstance(vision_value, dict):
            payload[name] = _merge_inputs(json_value, vision_value)
        else:
            payload[name] = _scalar_merge(
                name, json_value, vision_value, conflict_notes,
                prefer_vision=(name in _vision_fields),
            )

    payload["conflict_notes"] = _unique_strings(conflict_notes)
    return type(json_entity)(**payload)


def _entity_signature(entity: InventoryEntity) -> tuple[Any, ...]:
    layer_tuple = tuple(sorted(getattr(entity, "source_layers", []) or []))
    return (
        entity.id,
        layer_tuple,
        getattr(entity, "type_hint", None),
        getattr(entity, "fixture_type", None),
        getattr(entity, "element_type", None),
        getattr(entity, "kind", None),
        getattr(entity, "wall_id", None),
    )


def _merge_entities(
    json_entities: list[EntityT],
    vision_entities: list[EntityT],
    *,
    vision_preferred_fields: frozenset[str] | None = None,
) -> list[EntityT]:
    merged: list[EntityT] = []
    unmatched_vision = vision_entities.copy()

    for json_entity in json_entities:
        match = next(
            (
                candidate
                for candidate in unmatched_vision
                if candidate.id == json_entity.id or _entity_signature(candidate) == _entity_signature(json_entity)
            ),
            None,
        )
        if match is None:
            merged.append(json_entity)
            continue

        unmatched_vision.remove(match)
        merged.append(_merge_entity(json_entity, match, vision_preferred_fields=vision_preferred_fields))

    merged.extend(unmatched_vision)
    return merged


# Layers that look like floor layers but are actually annotation/marker layers
# (e.g. floor-level-marker arrows). Exclude them from area sums.
_FLOOR_EXCLUDE_TOKENS = ("levl", "level", "marker", "nivel", "dims", "anno")


def _sum_hatch_area(cad_facts: dict[str, Any], tokens: tuple[str, ...]) -> tuple[float | None, list[str]]:
    hatches = cad_facts.get("cad_facts", {}).get("hatches", [])
    total = 0.0
    refs: list[str] = []
    for hatch in hatches:
        layer = str(hatch.get("layer", ""))
        area = hatch.get("area")
        if area is None or not _contains_token(layer, tokens):
            continue
        if _contains_token(layer, _FLOOR_EXCLUDE_TOKENS):
            continue
        total += float(area)
        refs.append(f"hatch:{hatch.get('handle') or layer}")

    return (total if refs else None, refs)


_MIN_WALL_LINE_LENGTH_M = 0.5
_MAX_WALL_LINE_LENGTH_M = 50.0


def _is_probable_wall_geometry(hint: dict[str, Any]) -> bool:
    """Heuristic: a geometry hint that looks like wall linework by its properties."""
    length = hint.get("length")
    if length is None:
        return False
    length = float(length)
    if length < _MIN_WALL_LINE_LENGTH_M or length > _MAX_WALL_LINE_LENGTH_M:
        return False
    entity_type = str(hint.get("entity_type", "")).lower()
    if entity_type in {"line", "polyline", "lwpolyline", "arc", ""}:
        return True
    return False


_LAYER_GPT_CACHE: dict[str, dict[str, str]] = {}


def _layer_stats_for_gpt(cad_facts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    layers_payload = cad_facts.get("cad_facts", {}).get("layers", {}) or {}
    geometry_hints = cad_facts.get("cad_facts", {}).get("geometry_hints", []) or []
    per_layer_geom: dict[str, dict[str, Any]] = {}
    for hint in geometry_hints:
        layer = str(hint.get("layer", "") or "UNKNOWN")
        entry = per_layer_geom.setdefault(
            layer,
            {"geom_segments": 0, "total_length_m": 0.0, "entity_types": set()},
        )
        entry["geom_segments"] += 1
        if hint.get("length") is not None:
            entry["total_length_m"] += float(hint["length"])
        et = str(hint.get("entity_type", "") or "")
        if et:
            entry["entity_types"].add(et)

    out: dict[str, dict[str, Any]] = {}
    for layer_name, summary in layers_payload.items():
        if not isinstance(summary, dict):
            continue
        geom = per_layer_geom.get(layer_name, {})
        entity_types = geom.get("entity_types", set())
        out[layer_name] = {
            "object_count": summary.get("object_count", 0),
            "entity_types": dict(summary.get("entity_types", {})),
            "sample_names": list(summary.get("sample_names", []))[:5],
            "geom_segments": geom.get("geom_segments", 0),
            "geom_length_m": round(geom.get("total_length_m", 0.0), 3),
            "geom_entity_types": sorted(entity_types)[:8],
        }
    for layer_name, geom in per_layer_geom.items():
        if layer_name in out:
            continue
        out[layer_name] = {
            "object_count": 0,
            "entity_types": {},
            "sample_names": [],
            "geom_segments": geom.get("geom_segments", 0),
            "geom_length_m": round(geom.get("total_length_m", 0.0), 3),
            "geom_entity_types": sorted(geom.get("entity_types", set()))[:8],
        }
    return out


def _gpt_classify_cad_layers(cad_facts: dict[str, Any]) -> dict[str, str]:
    """
    Batch-classify CAD layer names using GPT-4o when OPENAI_API_KEY is set.
    Returns mapping layer_name -> role token used by wall/structural builders.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}

    stats = _layer_stats_for_gpt(cad_facts)
    if not stats:
        return {}

    import hashlib

    cache_key = hashlib.sha256(
        json.dumps(sorted(stats.items()), ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:20]
    if cache_key in _LAYER_GPT_CACHE:
        return dict(_LAYER_GPT_CACHE[cache_key])

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai not installed; skipping GPT layer classification")
        return {}

    layers_for_prompt = list(stats.items())[:80]
    payload = [
        {
            "layer": name,
            "object_count": data["object_count"],
            "cad_entity_types": data["entity_types"],
            "sample_block_or_object_names": data["sample_names"],
            "geometry_segments": data["geom_segments"],
            "geometry_length_m": data["geom_length_m"],
            "geometry_entity_types": data["geom_entity_types"],
        }
        for name, data in layers_for_prompt
    ]

    client = OpenAI(api_key=api_key)
    prompt = (
        "Eres un ingeniero BIM/presupuestista. Clasifica CADA capa CAD para cuantificación de obra.\n"
        "Devuelve SOLO JSON válido: {\"classifications\":[{\"layer\":\"...\",\"role\":\"...\",\"confidence\":0.0-1.0}]}\n\n"
        "Valores permitidos para role (elige el MÁS ESPECÍFICO que aplique):\n"
        "- wall_masonry — muros de bloque/concreto en planta\n"
        "- wall_partition — tabiques, drywall, divisiones ligeras\n"
        "- structural_beam — vigas (líneas estructurales)\n"
        "- structural_column — columnas\n"
        "- structural_slab — losas / forjados en planta\n"
        "- structural_footing — zapatas / cimentación\n"
        "- door_window_symbol — puertas/ventanas como bloques o símbolos\n"
        "- floor_ceiling — pisos, techos, acabados horizontales\n"
        "- electrical — instalación eléctrica\n"
        "- plumbing — instalación sanitaria / agua / desagüe\n"
        "- annotation_dimension — cotas, textos, ejes, mallas\n"
        "- titleblock_legend_noise — sellos, leyendas decorativas, marcos de plano\n"
        "- other_constructive — constructivo pero no encaja arriba\n"
        "- unknown — no hay suficiente señal\n\n"
        "REGLAS: No clasifiques como wall_masonry si es claramente electrical/plumbing/annotation/titleblock. "
        "Si geom_length_m es alto y entity_types incluyen Line/Polyline y el nombre sugiere muro, wall_masonry.\n\n"
        f"CAPAS (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.1,
            max_tokens=4096,
            messages=[
                {
                    "role": "system",
                    "content": "Respond ONLY with compact JSON. No markdown fences.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception:
        logger.warning("GPT layer classification failed", exc_info=True)
        return {}

    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                logger.warning("Could not parse GPT layer classification JSON")
                return {}

    rows = parsed.get("classifications") or parsed.get("layers") or []
    result: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        layer = str(row.get("layer") or row.get("name") or "").strip()
        role = str(row.get("role") or row.get("category") or "").strip()
        if not layer or not role:
            continue
        conf = row.get("confidence")
        try:
            conf_f = float(conf) if conf is not None else 0.5
        except (TypeError, ValueError):
            conf_f = 0.5
        if conf_f < 0.35 and role in {"wall_masonry", "wall_partition", "structural_beam", "structural_column"}:
            continue
        result[layer] = role

    _LAYER_GPT_CACHE[cache_key] = dict(result)
    logger.info("GPT classified %d CAD layers for inventory routing", len(result))
    return result


_PSEUDO_ELEMENT_LAYER_TOKENS: tuple[str, ...] = (
    "acero",
    "rebar",
    "armad",
    "textos",
    "texto",
    "leyenda",
    "dim",
    "dims",
    "dimens",
    "cota",
    "cotas",
    "perfil",
    "xref",
    "hatch",
    "detalle",
    "detalles",
    "anotac",
    "anndt",
    "annobj",
    "annotation",
    "label",
    "title",
    "marker",
    "simbol",
    "ref-",
)


def _is_pseudo_element_layer(*values: Any) -> bool:
    """True when the layer/name is a CAD annotation that should never be
    treated as a real construction element (acero/textos/dim/perfil/xref/hatch)."""
    blob = _joined_hint_text(*values)
    return _contains_token(blob, _PSEUDO_ELEMENT_LAYER_TOKENS)


def _gpt_role_to_wall(role: str) -> bool:
    return role in {"wall_masonry", "wall_partition"}


def _gpt_role_to_structural_type(role: str) -> str | None:
    return {
        "structural_beam": "beam",
        "structural_column": "column",
        "structural_slab": "slab",
        "structural_footing": "footing",
    }.get(role)


def _layer_excludes_wall_geometry_fallback(role: str | None) -> bool:
    if not role:
        return False
    return role in {
        "annotation_dimension",
        "titleblock_legend_noise",
        "electrical",
        "plumbing",
        "door_window_symbol",
        "floor_ceiling",
        "other_constructive",
        "unknown",
    }


def _structural_or_opening_layer_tokens(layer: str) -> bool:
    return _contains_token(
        layer,
        (
            *_BEAM_TOKENS,
            *_COLUMN_TOKENS,
            *_SLAB_TOKENS,
            *_FOOTING_TOKENS,
            *_DOOR_TOKENS,
            *_WINDOW_TOKENS,
            *_CEILING_TOKENS,
        ),
    )


def _canon_layer(layer: str) -> str:
    """Canonical bucket key for a CAD layer name.

    Why: cad_facts can ship the same logical layer under multiple spellings
    ("MUROS", "muros", "MUROS ") and downstream ids are formed as
    f"json-wall-{layer.lower()}" — without canonical bucketing two entries
    collide on the same id and crash `_assert_unique_takeoff_keys`.
    """
    return str(layer or "").strip().lower()


def _build_json_walls(
    level_id: str,
    cad_facts: dict[str, Any],
    *,
    gpt_layer_roles: dict[str, str] | None = None,
) -> list[Wall]:
    gpt_layer_roles = gpt_layer_roles or {}
    geometry_hints = cad_facts.get("cad_facts", {}).get("geometry_hints", [])
    wall_lengths: dict[str, float] = {}
    wall_refs: dict[str, list[str]] = {}
    token_wall_layers: set[str] = set()
    layer_display: dict[str, str] = {}

    for hint in geometry_hints:
        layer = str(hint.get("layer", ""))
        canon = _canon_layer(layer)
        if not canon:
            continue
        if _is_pseudo_element_layer(layer):
            continue
        if _contains_token(layer, _WALL_TOKENS):
            length = hint.get("length")
            if length is None:
                continue
            wall_lengths[canon] = wall_lengths.get(canon, 0.0) + float(length)
            wall_refs.setdefault(canon, []).append(f"geometry:{hint.get('handle') or layer}")
            token_wall_layers.add(canon)
            layer_display.setdefault(canon, layer)

    gpt_wall_lengths: dict[str, float] = {}
    gpt_wall_refs: dict[str, list[str]] = {}
    for hint in geometry_hints:
        layer = str(hint.get("layer", ""))
        canon = _canon_layer(layer)
        if not canon or canon in token_wall_layers:
            continue
        if _structural_or_opening_layer_tokens(layer):
            continue
        if _is_pseudo_element_layer(layer):
            continue
        role = gpt_layer_roles.get(layer) or gpt_layer_roles.get(canon)
        if not _gpt_role_to_wall(role):
            continue
        length = hint.get("length")
        if length is None:
            continue
        gpt_wall_lengths[canon] = gpt_wall_lengths.get(canon, 0.0) + float(length)
        gpt_wall_refs.setdefault(canon, []).append(f"geometry:{hint.get('handle') or layer}")
        layer_display.setdefault(canon, layer)

    gpt_wall_layers: set[str] = set()
    for canon, total in gpt_wall_lengths.items():
        wall_lengths[canon] = wall_lengths.get(canon, 0.0) + total
        wall_refs.setdefault(canon, []).extend(gpt_wall_refs.get(canon, []))
        gpt_wall_layers.add(canon)

    # -----------------------------------------------------------------------
    # GEOMETRY FALLBACK — DISABLED
    # Previously, any unclassified layer with linework >= 3m was treated as
    # a wall.  This caused massive budget inflation because layers for cables,
    # text, plumbing, structural elements, furniture, etc. were all counted
    # as walls.  Now we trust ONLY token matching ("wall", "muro") and GPT
    # classification to identify wall layers.
    # -----------------------------------------------------------------------
    classified_for_fallback: set[str] = set(token_wall_layers) | set(gpt_wall_layers)
    for hint in geometry_hints:
        layer = str(hint.get("layer", ""))
        canon = _canon_layer(layer)
        if not canon or canon in classified_for_fallback:
            continue
        if _structural_or_opening_layer_tokens(layer):
            continue
        role = gpt_layer_roles.get(layer) or gpt_layer_roles.get(canon)
        if _layer_excludes_wall_geometry_fallback(role):
            continue
        length = hint.get("length")
        if length is not None and _is_probable_wall_geometry(hint):
            # Log only — do NOT add to wall inventory
            logger.debug(
                "Geometry fallback SKIPPED layer '%s' (length=%.2fm) — "
                "not positively identified as wall by tokens or GPT.",
                layer,
                float(length),
            )

    geometry_fallback_layers: set[str] = set()
    # (No layers added by fallback — only token_wall_layers and gpt_wall_layers are used)

    walls: list[Wall] = []
    for canon, length in wall_lengths.items():
        display_layer = layer_display.get(canon, canon)
        material_hint = _infer_material_hint(display_layer)
        wall_system = _infer_wall_system_hint(display_layer)
        interior_exterior_hint = _infer_interior_exterior_hint(display_layer)
        finish_required = _infer_finish_required(display_layer)
        structural_hint = _infer_load_bearing_hint(display_layer)
        gpt_role = gpt_layer_roles.get(display_layer) or gpt_layer_roles.get(canon)
        if canon in token_wall_layers:
            detection = "layer_name_token"
            is_fallback = False
        elif canon in gpt_wall_layers:
            detection = "gpt_layer_role"
            is_fallback = False
        else:
            detection = "geometry_heuristic"
            is_fallback = True
        if gpt_role and canon in gpt_wall_layers:
            if gpt_role == "wall_partition":
                wall_system = wall_system or "drywall_partition"
            elif gpt_role == "wall_masonry":
                wall_system = wall_system or "masonry_wall"
        walls.append(
            Wall(
                id=f"json-wall-{canon}",
                level_id=level_id,
                source="json",
                source_layers=[display_layer],
                length_m=length,
                material_hint=material_hint,
                wall_system=wall_system,
                interior_exterior_hint=interior_exterior_hint,
                finish_required=finish_required,
                structural=structural_hint,
                source_refs=_unique_strings(wall_refs.get(canon, [])),
                inputs={
                    "json_layer": display_layer,
                    "json_length_m": length,
                    "detected_by_geometry": is_fallback,
                    "wall_detection": detection,
                    **({"gpt_layer_role": gpt_role} if gpt_role else {}),
                },
                assumptions=[
                    *(
                        [f"Layer '{display_layer}' classified as wall by geometry heuristic (total linework >= 3m)."]
                        if is_fallback
                        else []
                    ),
                    *(
                        [f"Layer '{display_layer}' classified as wall by GPT-4o role '{gpt_role}'."]
                        if canon in gpt_wall_layers and gpt_role
                        else []
                    ),
                ],
                evidence=[
                    f"Aggregated linework length from layer {display_layer}.",
                    *(
                        [f"Detected wall system hint '{wall_system}' from layer {display_layer}."]
                        if wall_system
                        else []
                    ),
                    *(
                        [f"Detected wall material hint '{material_hint}' from layer {display_layer}."]
                        if material_hint
                        else []
                    ),
                    *(
                        [f"Geometry fallback: layer '{display_layer}' had {length:.1f}m of linework matching wall-like geometry properties."]
                        if is_fallback
                        else []
                    ),
                    *(
                        [f"GPT layer classification: {gpt_role}."]
                        if canon in gpt_wall_layers and gpt_role
                        else []
                    ),
                ],
            )
        )
    return _dedupe_walls_by_id(walls)


def _dedupe_walls_by_id(walls: list[Wall]) -> list[Wall]:
    """Defense-in-depth: collapse same-id walls. Canonical bucketing should
    prevent collisions upstream, but downstream merges (`_merge_entities`)
    have no guard against duplicate ids inside the json list itself.
    """
    by_id: dict[str, Wall] = {}
    for wall in walls:
        existing = by_id.get(wall.id)
        if existing is None:
            by_id[wall.id] = wall
            continue
        if wall.length_m is not None:
            existing.length_m = (existing.length_m or 0.0) + wall.length_m
        existing.source_layers = _unique_strings(existing.source_layers, wall.source_layers)
        existing.source_refs = _unique_strings(existing.source_refs, wall.source_refs)
        existing.assumptions = _unique_strings(existing.assumptions, wall.assumptions)
        existing.evidence = _unique_strings(existing.evidence, wall.evidence)
        existing.conflict_notes = _unique_strings(
            existing.conflict_notes, wall.conflict_notes,
            [f"Merged duplicate wall id '{wall.id}' from layers {wall.source_layers}."],
        )
    return list(by_id.values())


def _build_json_structural_elements(
    level_id: str,
    cad_facts: dict[str, Any],
    *,
    gpt_layer_roles: dict[str, str] | None = None,
) -> list[StructuralElement]:
    gpt_layer_roles = gpt_layer_roles or {}
    geometry_hints = cad_facts.get("cad_facts", {}).get("geometry_hints", [])
    blocks = cad_facts.get("cad_facts", {}).get("blocks", [])
    hatches = cad_facts.get("cad_facts", {}).get("hatches", [])

    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    def ensure_group(element_type: str, layer: str, name_hint: str = "") -> dict[str, Any]:
        canon = _canon_layer(layer)
        key = (element_type, canon)
        if key not in grouped:
            hint_text = _joined_hint_text(layer, name_hint)
            mat = _infer_material_hint(hint_text)
            grouped[key] = {
                "id": f"json-{element_type}-{canon}",
                "level_id": level_id,
                "source": "json",
                "element_type": element_type,
                "count": 0,
                "length_m": None,
                "area_m2": None,
                "volume_m3": None,
                "material_hint": mat,
                "orientation": "vertical" if element_type == "column" else "horizontal",
                "load_bearing": True if element_type in {"beam", "column", "slab", "footing"} else _infer_load_bearing_hint(hint_text),
                "reinforcement_hint": _infer_reinforcement_hint(hint_text),
                "concrete_grade_hint": _infer_concrete_grade_hint(hint_text),
                "steel_grade_hint": _infer_steel_grade_hint(hint_text),
                "host_level": level_id,
                "adjacent_elements": [],
                "source_refs": [],
                "assumptions": [],
                "inputs": {"json_layer": layer, "json_name_hints": []},
                "conflict_notes": [],
                "evidence": [],
            }
        if name_hint and name_hint not in grouped[key]["inputs"]["json_name_hints"]:
            grouped[key]["inputs"]["json_name_hints"].append(name_hint)
        return grouped[key]

    def add_numeric(group: dict[str, Any], field_name: str, value: float | None) -> None:
        if value is None:
            return
        existing = group.get(field_name)
        group[field_name] = float(value) if existing is None else float(existing) + float(value)

    for hint in geometry_hints:
        layer = str(hint.get("layer", ""))
        canon = _canon_layer(layer)
        if not canon:
            continue
        name_hint = str(hint.get("name", ""))
        if _is_pseudo_element_layer(layer, name_hint):
            logger.debug(
                "Structural skip: pseudo-element layer '%s' (name=%r) is annotation, not a real element.",
                layer,
                name_hint,
            )
            continue
        entity_type_from_tokens = _infer_structural_element_type(layer, name_hint)
        gpt_role = gpt_layer_roles.get(layer) or gpt_layer_roles.get(canon)
        entity_type = entity_type_from_tokens or _gpt_role_to_structural_type(gpt_role or "")
        if not entity_type:
            continue

        group = ensure_group(entity_type, layer, name_hint)
        add_numeric(group, "length_m", hint.get("length"))
        add_numeric(group, "area_m2", hint.get("area"))
        if hint.get("handle"):
            group["source_refs"].append(f"geometry:{hint['handle']}")
        group["evidence"].append(
            f"Aggregated geometry hint for structural {entity_type} from layer {layer}."
        )
        if not entity_type_from_tokens and gpt_role:
            group["evidence"].append(f"GPT layer role: {gpt_role}.")
            group["inputs"]["gpt_layer_role"] = gpt_role

    for block in blocks:
        layer = str(block.get("layer", ""))
        canon = _canon_layer(layer)
        if not canon:
            continue
        block_name = str(block.get("block_name", ""))
        if _is_pseudo_element_layer(layer, block_name):
            continue
        element_type_from_tokens = _infer_structural_element_type(layer, block_name)
        gpt_role = gpt_layer_roles.get(layer) or gpt_layer_roles.get(canon)
        element_type = element_type_from_tokens or _gpt_role_to_structural_type(gpt_role or "")
        if not element_type:
            continue

        group = ensure_group(element_type, layer, block_name)
        group["count"] += 1
        if block.get("handle"):
            group["source_refs"].append(f"block:{block['handle']}")
        group["evidence"].append(
            f"Counted explicit structural block '{block_name}' on layer {layer}."
        )
        if not element_type_from_tokens and gpt_role:
            group["evidence"].append(f"GPT layer role: {gpt_role}.")
            group["inputs"]["gpt_layer_role"] = gpt_role

    for hatch in hatches:
        layer = str(hatch.get("layer", ""))
        canon = _canon_layer(layer)
        if not canon:
            continue
        pattern_name = str(hatch.get("pattern_name", ""))
        if _is_pseudo_element_layer(layer, pattern_name):
            continue
        entity_type_from_tokens = _infer_structural_element_type(layer, pattern_name)
        gpt_role = gpt_layer_roles.get(layer) or gpt_layer_roles.get(canon)
        element_type = entity_type_from_tokens or _gpt_role_to_structural_type(gpt_role or "")

        if element_type is None:
            if _contains_token(layer, _CONCRETE_TOKENS) or _contains_token(pattern_name, _CONCRETE_TOKENS):
                area = hatch.get("area")
                if area is not None and float(area) > 0.5:
                    element_type = "slab"

        if element_type not in {"slab", "footing"}:
            continue

        group = ensure_group(element_type, layer, pattern_name)
        add_numeric(group, "area_m2", hatch.get("area"))
        if hatch.get("handle"):
            group["source_refs"].append(f"hatch:{hatch['handle']}")
        group["evidence"].append(
            f"Aggregated {element_type} hatch area from layer {layer}."
        )
        if (
            not entity_type_from_tokens
            and gpt_role
            and _gpt_role_to_structural_type(gpt_role) == element_type
        ):
            group["evidence"].append(f"GPT layer role: {gpt_role}.")
            group["inputs"]["gpt_layer_role"] = gpt_role

    structural_elements: list[StructuralElement] = []
    for _, payload in sorted(grouped.items(), key=lambda item: item[0]):
        payload["count"] = max(int(payload["count"]), 1)
        payload["source_refs"] = _unique_strings(payload["source_refs"])
        payload["evidence"] = _unique_strings(payload["evidence"])
        structural_elements.append(StructuralElement(**payload))

    return structural_elements


def _build_json_openings(
    level_id: str,
    entities: list[Door] | list[Window],
    opening_type: str,
) -> list[Opening]:
    openings: list[Opening] = []
    for entity in entities:
        openings.append(
            Opening(
                id=f"{entity.id}:opening",
                level_id=level_id,
                source=entity.source,
                wall_id=getattr(entity, "wall_id", None),
                opening_type=opening_type,
                count=entity.count,
                width_m=getattr(entity, "width_m", None),
                height_m=getattr(entity, "height_m", None),
                source_layers=list(getattr(entity, "source_layers", [])),
                source_refs=list(entity.source_refs),
                assumptions=list(entity.assumptions),
                inputs=dict(entity.inputs),
                conflict_notes=list(entity.conflict_notes),
                evidence=list(entity.evidence),
                related_door_id=entity.id if opening_type == "door" else None,
                related_window_id=entity.id if opening_type == "window" else None,
            )
        )
    return openings


def _build_json_doors_or_windows(
    *,
    level_id: str,
    blocks: list[dict[str, Any]],
    token_set: tuple[str, ...],
    cls: type[Door] | type[Window],
    item_prefix: str,
) -> list[Door] | list[Window]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for block in blocks:
        block_name = str(block.get("block_name", ""))
        layer = str(block.get("layer", ""))
        if not (_contains_token(block_name, token_set) or _contains_token(layer, token_set)):
            continue
        grouped.setdefault((layer, block_name), []).append(block)

    entities: list[Door] | list[Window] = []
    for index, ((layer, block_name), items) in enumerate(grouped.items(), start=1):
        payload = dict(
            id=f"{item_prefix}-{index}",
            level_id=level_id,
            source="json",
            source_layers=[layer],
            count=len(items),
            source_refs=[f"block:{item.get('handle') or block_name}" for item in items],
            inputs={"json_layer": layer, "block_name": block_name, "json_count": len(items)},
            evidence=[f"Counted block references matching '{block_name or layer}'."],
        )
        if cls is Door:
            entities.append(Door(**payload))
        else:
            entities.append(Window(**payload))
    return entities


def build_json_inventory(
    cad_facts: dict[str, Any],
    *,
    level_id: str,
    level_name: str,
) -> LevelInventory:
    blocks = cad_facts.get("cad_facts", {}).get("blocks", [])
    floor_area_m2, floor_refs = _sum_hatch_area(cad_facts, _FLOOR_TOKENS)
    ceiling_area_m2, ceiling_refs = _sum_hatch_area(cad_facts, _CEILING_TOKENS)
    doors = _build_json_doors_or_windows(
        level_id=level_id,
        blocks=blocks,
        token_set=_DOOR_TOKENS,
        cls=Door,
        item_prefix="json-door",
    )
    windows = _build_json_doors_or_windows(
        level_id=level_id,
        blocks=blocks,
        token_set=_WINDOW_TOKENS,
        cls=Window,
        item_prefix="json-window",
    )
    gpt_layer_roles = _gpt_classify_cad_layers(cad_facts)
    walls = _build_json_walls(level_id, cad_facts, gpt_layer_roles=gpt_layer_roles)
    structural_elements = _build_json_structural_elements(
        level_id, cad_facts, gpt_layer_roles=gpt_layer_roles
    )
    space_types = _extract_space_types(cad_facts)
    structural_types = _unique_strings(
        element.element_type for element in structural_elements if element.element_type
    )
    material_hints = _unique_strings(
        [wall.material_hint for wall in walls if wall.material_hint],
        [element.material_hint for element in structural_elements if element.material_hint],
    )

    return LevelInventory(
        level_id=level_id,
        level_name=level_name,
        source="json",
        cad_hints={
            "material_hints": material_hints,
            "structural_types": structural_types,
            "space_types": space_types,
            **({"gpt_layer_roles": gpt_layer_roles} if gpt_layer_roles else {}),
        },
        source_refs=_unique_strings(
            floor_refs,
            ceiling_refs,
            *(element.source_refs for element in structural_elements),
        ),
        space_types=space_types,
        system_notes=[
            *(
                [
                    "CAD facts suggest probable material systems: "
                    + ", ".join(material_hints)
                    + "."
                ]
                if material_hints
                else []
            )
        ],
        structural_notes=[
            *(
                [
                    "Explicit structural CAD hints detected for: "
                    + ", ".join(structural_types)
                    + "."
                ]
                if structural_types
                else []
            )
        ],
        inputs={"cad_summary": cad_facts.get("project")},
        floor_area_m2=floor_area_m2,
        ceiling_area_m2=ceiling_area_m2,
        walls=walls,
        doors=list(doors),
        windows=list(windows),
        structural_elements=structural_elements,
        openings=_build_json_openings(level_id, list(doors), "door")
        + _build_json_openings(level_id, list(windows), "window"),
        notes=["Built from normalized CAD facts."],
    )


def _merge_level_scalar(
    field_name: str,
    json_value: Any,
    vision_value: Any,
    conflict_notes: list[str],
) -> Any:
    return _scalar_merge(field_name, json_value, vision_value, conflict_notes)


def _total_wall_area_m2(level: LevelInventory) -> float:
    """Rough enclosed wall area for a level (area_m2, else length x height)."""
    total = 0.0
    for wall in (level.walls or []):
        area = getattr(wall, "area_m2", None)
        if area:
            total += float(area)
            continue
        length = getattr(wall, "length_m", None)
        height = getattr(wall, "height_m", None) or 2.8
        if length:
            total += float(length) * float(height)
    return total


def build_level_inventory(
    cad_facts: dict[str, Any],
    vision_inventory: LevelInventory | Mapping[str, Any] | None = None,
    *,
    level_id: str | None = None,
    level_name: str | None = None,
) -> LevelInventory:
    """
    Merge normalized CAD facts with vision-derived inventory.

    JSON-derived values are preferred when explicit, vision fills gaps, and any
    disagreement is preserved as conflict notes instead of being silently overwritten.
    """
    if isinstance(vision_inventory, LevelInventory):
        vision_level = vision_inventory
    elif vision_inventory is not None:
        vision_level = level_inventory_from_dict(vision_inventory, default_source="vision")
    else:
        vision_level = None

    resolved_level_id = level_id or (vision_level.level_id if vision_level else "level")
    resolved_level_name = level_name or (vision_level.level_name if vision_level else resolved_level_id)
    json_level = build_json_inventory(cad_facts, level_id=resolved_level_id, level_name=resolved_level_name)

    if vision_level is None:
        return json_level

    conflict_notes = _unique_strings(json_level.conflict_notes, vision_level.conflict_notes)

    # floor_area_m2: prefer Vision — JSON sources only have annotation hatches (not real floor
    # areas) while Vision reads actual room polygons. JSON is used as fallback when Vision is None.
    floor_area_m2 = _scalar_merge(
        "floor_area_m2",
        json_level.floor_area_m2,
        vision_level.floor_area_m2,
        conflict_notes,
        prefer_vision=True,
    )
    # E2: reject an implausibly small floor area. Vision sometimes returns e.g.
    # 15 m2 while the level has thousands of m2 of wall; a wall/floor ratio far
    # above the physical range (~0.3-8) means the floor area is wrong and would
    # distort $/m2 + finish quantities. Prefer the CAD hatch area, else drop it.
    wall_area = _total_wall_area_m2(vision_level) or _total_wall_area_m2(json_level)
    if floor_area_m2 and wall_area and float(floor_area_m2) < wall_area * 0.05:
        json_fa = json_level.floor_area_m2
        if json_fa and float(json_fa) >= wall_area * 0.05:
            conflict_notes.append(
                f"floor_area_m2: Vision {floor_area_m2} implausible vs wall area "
                f"{wall_area:.0f} m2; using CAD {json_fa}."
            )
            floor_area_m2 = json_fa
        else:
            conflict_notes.append(
                f"floor_area_m2: {floor_area_m2} implausible vs wall area {wall_area:.0f} m2; "
                "dropped (needs measurement)."
            )
            floor_area_m2 = None
    ceiling_area_m2 = _merge_level_scalar(
        "ceiling_area_m2",
        json_level.ceiling_area_m2,
        vision_level.ceiling_area_m2,
        conflict_notes,
    )

    return LevelInventory(
        level_id=resolved_level_id,
        level_name=resolved_level_name,
        source="hybrid",
        source_image=vision_level.source_image,
        source_view=vision_level.source_view,
        cad_hints=_merge_inputs(json_level.cad_hints, vision_level.cad_hints),
        floor_area_m2=floor_area_m2,
        ceiling_area_m2=ceiling_area_m2,
        space_types=_unique_strings(json_level.space_types, vision_level.space_types),
        system_notes=_unique_strings(json_level.system_notes, vision_level.system_notes),
        structural_notes=_unique_strings(json_level.structural_notes, vision_level.structural_notes),
        source_refs=_unique_strings(json_level.source_refs, vision_level.source_refs),
        assumptions=_unique_strings(json_level.assumptions, vision_level.assumptions),
        inputs=_merge_inputs(json_level.inputs, vision_level.inputs),
        conflict_notes=conflict_notes,
        # Walls: prefer Vision for area_m2 — JSON walls have only length_m from linework,
        # never area_m2; Vision can estimate area from visible plan polygons.
        walls=_merge_entities(
            json_level.walls,
            vision_level.walls,
            vision_preferred_fields=frozenset({"area_m2"}),
        ),
        openings=_merge_entities(json_level.openings, vision_level.openings),
        doors=_merge_entities(json_level.doors, vision_level.doors),
        windows=_merge_entities(json_level.windows, vision_level.windows),
        wet_areas=_merge_entities(json_level.wet_areas, vision_level.wet_areas),
        kitchens=_merge_entities(json_level.kitchens, vision_level.kitchens),
        stairs=_merge_entities(json_level.stairs, vision_level.stairs),
        fixtures=_merge_entities(json_level.fixtures, vision_level.fixtures),
        structural_elements=_merge_entities(
            json_level.structural_elements,
            vision_level.structural_elements,
        ),
        notes=_unique_strings(json_level.notes, vision_level.notes),
        confidence=vision_level.confidence,
    )
