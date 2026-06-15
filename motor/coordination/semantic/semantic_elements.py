"""Conservative semantic wrappers for coordination elements.

Rules:
- preserve geometry and source traceability first
- do not invent human-friendly names
- classify semantic type only when local CAD evidence is usable
- keep exact CAD entity evidence independent from semantic typing
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from disciplines.domain_rules import DomainRules, load_domain_rules_for_discipline
from coordination.core.models_25d import Discipline, Element25D

_ANNOTATION_HINT_TOKENS = (
    "TITULOS",
    "ESCALA_HUMANA",
    "SIMBOLOS",
    "TEXT",
    "ANNO",
    "DIM",
    "LABEL",
    "DETALLE",
    "DETALLES",
)

_ARCH_SEMANTIC_TOKENS: dict[str, tuple[str, ...]] = {
    "door": ("DOOR", "PUERTA", "PUERTAS"),
    "window": ("WINDOW", "VENTANA", "VENTANAS"),
    "stair": ("STAIR", "ESCALERA", "ESCALERAS"),
    "kitchen": ("KITCHEN", "COCINA", "COCINAS"),
    "wet_area": ("BANO", "BAÑO", "BANO", "WC", "LAV", "LAVAND", "DUCHA", "SHOWER"),
    "ceiling_finish": ("CEILING", "CIELO", "PLAFON", "YESO"),
    "floor_finish": ("FLOOR", "PISO", "PORCELANATO", "CERAMICA"),
    "fixture": ("LUMIN", "LIGHT", "TOMA", "OUTLET", "SWITCH", "FIXTURE", "SANIT"),
    "wall_masonry": ("WALL", "MURO", "MUROS", "BLOQUE", "BLOCK", "MAMPOST"),
}

_STRUCT_SEMANTIC_TOKENS: dict[str, tuple[str, ...]] = {
    "beam": ("BEAM", "VIGA", "VIGAS", "S-BEAM", "EJE DE VIGA"),
    "column": ("COLUMN", "COLUMNA", "COLUMNAS", "COL", "COLS", "S-COLS"),
    "slab": ("SLAB", "LOSA", "LOSAS", "ENTREPISO"),
    "footing": ("FOOTING", "ZAPATA", "ZAPATAS", "CIMIENTO", "CIMIENTOS"),
    "shear_wall": ("SHEAR", "CORTE"),
    "stair": ("STAIR", "ESCALERA", "ESCALERAS"),
}

_PLUMBING_SEMANTIC_TOKENS: dict[str, tuple[str, ...]] = {
    "pipe": ("PIPE", "TUB", "TUBERIA", "TUBERIAS", "SANIT", "DRENAJE", "AGUA"),
    "fixture": ("WC", "LAV", "DUCHA", "FREGADERO", "SANITARIO"),
}

_HVAC_SEMANTIC_TOKENS: dict[str, tuple[str, ...]] = {
    "duct": ("DUCT", "DUCTO", "DUCTOS", "RETORNO", "SUMINISTRO"),
    "fixture": ("GRILLA", "REJILLA", "DIFFUSER", "DIFUSOR"),
}

_ELEC_SEMANTIC_TOKENS: dict[str, tuple[str, ...]] = {
    "fixture": ("LIGHT", "LUMIN", "OUTLET", "TOMA", "SWITCH", "TABLERO", "PANEL"),
}


class SemanticElement25D(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_element_id: str
    source_element_id: str
    source_file: str
    source_rel_path: str | None = None
    file_name: str
    discipline: str
    level_id: str
    layer: str
    cad_handle: str | None = None
    entity_type: str | None = None
    block_name: str | None = None
    element_type: str
    element_name: str | None = None
    bbox_mm: tuple[float, float, float, float] | None = None
    centroid_mm: tuple[float, float] | None = None
    footprint_coords_mm: list[tuple[float, float]] = Field(default_factory=list)
    geometry_source: str = "unknown"
    geometry_role: str = "primary"
    geometry_confidence: str = "medium"
    semantic_type_confidence: str = "unknown"
    semantic_type_reason: str = "no_semantic_evidence"
    classification_signals: list[str] = Field(default_factory=list)
    name_confidence: str = "low"
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_semantic_elements_from_accore_payload(
    *,
    raw_elements: list[Element25D],
    source_file: Path,
    source_rel_path: str | None = None,
    payload: dict[str, Any] | None = None,
) -> list[SemanticElement25D]:
    entity_lookup = _payload_entity_lookup(payload)
    domain_rules = _load_rules_for_element_set(raw_elements)
    semantic_elements: list[SemanticElement25D] = []
    for element in raw_elements:
        metadata = dict(element.metadata)
        handle = str(metadata.get("cad_handle") or metadata.get("handle") or _handle_from_source_ref(element.source_ref) or "")
        payload_entity = entity_lookup.get(handle)
        payload_block_name = None
        payload_entity_type = None
        if payload_entity:
            payload_block_name = str(payload_entity.get("Name") or payload_entity.get("BlockName") or "").strip() or None
            payload_entity_type = str(payload_entity.get("Type") or "").strip() or None
        element_type, type_confidence, type_reason, type_signals = _classify_semantic_type(
            element=element,
            metadata=metadata,
            payload_entity=payload_entity,
            payload_block_name=payload_block_name,
            payload_entity_type=payload_entity_type,
            domain_rules=domain_rules,
        )
        element_name, name_confidence = _resolve_publishable_name(
            block_name=str(metadata.get("block_name") or payload_block_name or "") or None,
            semantic_type_confidence=type_confidence,
            nearby_texts=list(metadata.get("nearby_texts") or []),
        )

        semantic_elements.append(
            SemanticElement25D(
                semantic_element_id=f"semantic_{element.id}",
                source_element_id=element.id,
                source_file=str(metadata.get("source_file") or source_file.as_posix()),
                source_rel_path=str(metadata.get("source_rel_path") or source_rel_path) if (metadata.get("source_rel_path") or source_rel_path) else None,
                file_name=str(metadata.get("file") or source_file.name),
                discipline=element.discipline.value,
                level_id=str(metadata.get("file_level_id") or metadata.get("level_id") or element.z_data.level_id),
                layer=str(metadata.get("layer") or _layer_from_source_ref(element.source_ref) or "0"),
                cad_handle=handle or None,
                entity_type=str(metadata.get("entity_type") or payload_entity_type or _entity_from_source_ref(element.source_ref) or "") or None,
                block_name=str(metadata.get("block_name") or payload_block_name or "") or None,
                element_type=element_type,
                element_name=element_name,
                bbox_mm=_bbox_from_element(element),
                centroid_mm=_centroid_from_element(element),
                footprint_coords_mm=list(element.footprint_coords_mm),
                geometry_source=str(metadata.get("geometry_source") or "unknown"),
                geometry_role=str(metadata.get("geometry_role") or "primary"),
                geometry_confidence=str(metadata.get("geometry_confidence") or _confidence_from_quality(metadata.get("geometry_quality"))),
                semantic_type_confidence=type_confidence,
                semantic_type_reason=type_reason,
                classification_signals=type_signals,
                name_confidence=name_confidence,
                metadata={
                    "category": element.category,
                    "source_ref": element.source_ref,
                    "nearby_texts": list(metadata.get("nearby_texts") or []),
                    "suppression_reason": metadata.get("suppression_reason"),
                    "sheet_or_view_name": metadata.get("sheet_or_view_name"),
                },
            )
        )
    return semantic_elements


def export_elements_by_dwg_json(
    *,
    generated_at: str,
    project_name: str,
    run_label: str,
    semantic_elements: list[SemanticElement25D],
) -> dict[str, Any]:
    files: dict[str, list[SemanticElement25D]] = {}
    for element in semantic_elements:
        files.setdefault(element.source_file, []).append(element)

    file_payloads: list[dict[str, Any]] = []
    type_counter: Counter[str] = Counter()
    confidence_counter: Counter[str] = Counter()
    for source_file, elements in sorted(files.items()):
        first = elements[0]
        for element in elements:
            type_counter[element.element_type] += 1
            confidence_counter[element.semantic_type_confidence] += 1
        file_payloads.append(
            {
                "source_file": source_file,
                "source_rel_path": first.source_rel_path,
                "file_name": first.file_name,
                "discipline": first.discipline,
                "level_id": first.level_id,
                "element_count": len(elements),
                "semantic_type_confidence_mix": dict(Counter(item.semantic_type_confidence for item in elements)),
                "elements": [element.model_dump() for element in elements],
            }
        )

    return {
        "generated_at": generated_at,
        "project_name": project_name,
        "run_label": run_label,
        "file_count": len(file_payloads),
        "element_count": len(semantic_elements),
        "element_type_mix": dict(type_counter),
        "semantic_type_confidence_mix": dict(confidence_counter),
        "files": file_payloads,
    }


def _payload_entity_lookup(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for entity in (payload or {}).get("Entities") or []:
        if not isinstance(entity, dict):
            continue
        handle = str(entity.get("Handle") or "").strip()
        if not handle:
            continue
        lookup[handle] = entity
    return lookup


def _unknown_element_type(discipline: Discipline) -> str:
    return {
        Discipline.ARCH: "unknown_architecture",
        Discipline.STRUC: "unknown_structure",
        Discipline.MEP_PLUMBING: "unknown_mep_plumbing",
        Discipline.MEP_HVAC: "unknown_mep_hvac",
        Discipline.MEP_ELEC: "unknown_mep_electrical",
    }.get(discipline, "unknown_generic")


def _load_rules_for_element_set(raw_elements: list[Element25D]) -> DomainRules | None:
    if not raw_elements:
        return None
    discipline = raw_elements[0].discipline
    discipline_id = {
        Discipline.ARCH: "arquitectura",
        Discipline.STRUC: "estructura",
        Discipline.MEP_PLUMBING: "hidrosanitarios",
        Discipline.MEP_HVAC: "climatizacion",
        Discipline.MEP_ELEC: "electricidad",
    }.get(discipline)
    if not discipline_id:
        return None
    try:
        return load_domain_rules_for_discipline(discipline_id)
    except Exception:
        return None


def _classify_semantic_type(
    *,
    element: Element25D,
    metadata: dict[str, Any],
    payload_entity: dict[str, Any] | None,
    payload_block_name: str | None,
    payload_entity_type: str | None,
    domain_rules: DomainRules | None,
) -> tuple[str, str, str, list[str]]:
    fallback_type = _unknown_element_type(element.discipline)
    source_ref_tail = _source_ref_signal_tail(str(metadata.get("source_ref") or element.source_ref or ""))
    hint_sources = [
        ("block_name", str(metadata.get("block_name") or payload_block_name or "")),
        ("layer", str(metadata.get("layer") or "")),
        ("category", str(metadata.get("category") or element.category or "")),
        ("source_ref_tail", source_ref_tail),
        ("entity_type", str(metadata.get("entity_type") or payload_entity_type or "")),
    ]
    signals = [f"{label}:{value}" for label, value in hint_sources if value]
    if any(_contains_token(value, _ANNOTATION_HINT_TOKENS) for _label, value in hint_sources if value):
        return (fallback_type, "unknown", "annotation_or_graphic_signal", signals)

    token_map = _token_map_for_discipline(element.discipline)
    allowed_types = set(domain_rules.whitelisted_element_types) if domain_rules else set(token_map)
    for label, value in hint_sources:
        if not value:
            continue
        matched = _match_semantic_type(value, token_map=token_map, allowed_types=allowed_types)
        if matched is None:
            continue
        confidence = "high" if label == "block_name" else "medium" if label in {"layer", "category"} else "low"
        if confidence == "low":
            continue
        return (matched, confidence, f"{label}_token_match", signals)

    return (fallback_type, "unknown", "discipline_fallback_unknown", signals)


def _token_map_for_discipline(discipline: Discipline) -> dict[str, tuple[str, ...]]:
    if discipline == Discipline.ARCH:
        return _ARCH_SEMANTIC_TOKENS
    if discipline == Discipline.STRUC:
        return _STRUCT_SEMANTIC_TOKENS
    if discipline == Discipline.MEP_PLUMBING:
        return _PLUMBING_SEMANTIC_TOKENS
    if discipline == Discipline.MEP_HVAC:
        return _HVAC_SEMANTIC_TOKENS
    if discipline == Discipline.MEP_ELEC:
        return _ELEC_SEMANTIC_TOKENS
    return {}


def _match_semantic_type(
    value: str,
    *,
    token_map: dict[str, tuple[str, ...]],
    allowed_types: set[str],
) -> str | None:
    normalized = value.upper()
    for semantic_type, tokens in token_map.items():
        if semantic_type not in allowed_types:
            continue
        if any(token in normalized for token in tokens):
            return semantic_type
    return None


def _resolve_publishable_name(
    *,
    block_name: str | None,
    semantic_type_confidence: str,
    nearby_texts: list[dict[str, Any]] | None = None,
) -> tuple[str | None, str]:
    if semantic_type_confidence == "high" and block_name:
        normalized = block_name.strip()
        if normalized and not normalized.startswith("A$") and not normalized.upper().startswith("*U"):
            return (normalized, "medium")
    nearby_name = _publishable_name_from_nearby_texts(nearby_texts or [])
    if nearby_name:
        return (nearby_name, "medium")
    return (None, "low")


def _publishable_name_from_nearby_texts(nearby_texts: list[dict[str, Any]]) -> str | None:
    patterns = (
        re.compile(r"\b(?:P|V|VT|E|C|B)-?\d+[A-Z]?\b", flags=re.IGNORECASE),
        re.compile(
            r"\b(?:BAÑO|BANO|COCINA|DORMITORIO|HABITACION|HAB\.?|SALA|COMEDOR|TERRAZA|"
            r"LAVANDERIA|CLOSET|VESTIDOR|PATIO|BALCON|BALCÓN|ESTAR|ESTUDIO)\b",
            flags=re.IGNORECASE,
        ),
    )
    for item in sorted(nearby_texts, key=lambda row: float(row.get("distance_mm") or 0.0)):
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        for pattern in patterns:
            match = pattern.search(content)
            if match:
                return match.group(0).strip()
    return None


def _bbox_from_element(element: Element25D) -> tuple[float, float, float, float] | None:
    if not element.footprint_coords_mm:
        return None
    xs = [point[0] for point in element.footprint_coords_mm]
    ys = [point[1] for point in element.footprint_coords_mm]
    return (min(xs), min(ys), max(xs), max(ys))


def _centroid_from_element(element: Element25D) -> tuple[float, float] | None:
    bbox = _bbox_from_element(element)
    if bbox is None:
        return None
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _confidence_from_quality(value: Any) -> str:
    quality = str(value or "medium").lower()
    if quality in {"high", "exact"}:
        return "high"
    if quality in {"medium", "proxy"}:
        return "medium"
    return "low"


def _contains_token(value: str, tokens: tuple[str, ...]) -> bool:
    normalized = value.upper()
    return any(token in normalized for token in tokens)


def _source_ref_signal_tail(source_ref: str) -> str:
    parts = [part.strip() for part in source_ref.split("|") if part.strip()]
    if len(parts) >= 4:
        return "|".join(parts[1:4])
    if len(parts) >= 2:
        return "|".join(parts[1:])
    return ""


def _layer_from_source_ref(source_ref: str) -> str | None:
    parts = source_ref.split("|")
    return parts[1] if len(parts) > 1 else None


def _entity_from_source_ref(source_ref: str) -> str | None:
    parts = source_ref.split("|")
    return parts[2] if len(parts) > 2 else None


def _handle_from_source_ref(source_ref: str) -> str | None:
    parts = source_ref.split("|")
    return parts[3] if len(parts) > 3 else None
