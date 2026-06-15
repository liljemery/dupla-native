"""
Deterministic semantic enrichment for all disciplines.

Builds a SemanticBuilding hierarchy from merged level inventories,
assigning confidence scores and spatial context to each entity.
Phase 1: deterministic only (no LLM).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core.schemas import InventoryEntity, LevelInventory
from core.semantic_models import (
    SemanticBuilding,
    SemanticElement,
    SemanticLevel,
    SemanticSpace,
    SemanticUnit,
)

_ALL_ENTITY_GROUPS = (
    ("wall", "walls"),
    ("opening", "openings"),
    ("door", "doors"),
    ("window", "windows"),
    ("wet_area", "wet_areas"),
    ("kitchen", "kitchens"),
    ("stair", "stairs"),
    ("fixture", "fixtures"),
    ("structural_element", "structural_elements"),
)

_DISCIPLINE_ENTITY_GROUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "arquitectura": (
        ("wall", "walls"),
        ("opening", "openings"),
        ("door", "doors"),
        ("window", "windows"),
        ("wet_area", "wet_areas"),
        ("kitchen", "kitchens"),
        ("stair", "stairs"),
        ("fixture", "fixtures"),
    ),
    "estructura": (
        ("wall", "walls"),
        ("structural_element", "structural_elements"),
    ),
    "electrico": (
        ("fixture", "fixtures"),
    ),
    "sanitario": (
        ("fixture", "fixtures"),
        ("wet_area", "wet_areas"),
    ),
}


def _normalize_token(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _source_from_entity(entity: InventoryEntity) -> str:
    if entity.source == "json":
        return "aps"
    if entity.source == "vision":
        return "vision"
    return "inferred"


def _base_confidence(entity: InventoryEntity) -> float:
    if entity.confidence is not None:
        return max(0.0, min(float(entity.confidence), 1.0))
    if entity.source == "json":
        return 0.9
    if entity.source == "hybrid":
        return 0.78
    if entity.source == "vision":
        return 0.65
    return 0.5


def _infer_space_name(entity: InventoryEntity, level: LevelInventory) -> str:
    tokens: list[str] = []
    for ref in entity.source_refs:
        tokens.extend(_normalize_token(str(ref)).split(":"))
    if isinstance(entity.inputs, dict):
        for key in ("location_hint", "space", "space_type", "room", "room_name"):
            value = entity.inputs.get(key)
            if isinstance(value, str) and value.strip():
                tokens.append(_normalize_token(value))
    for token in tokens:
        if token in {"bathroom", "bano", "bano_principal", "toilet"}:
            return "bathroom"
        if token in {"kitchen", "cocina"}:
            return "kitchen"
        if token in {"living", "sala", "living_room"}:
            return "living_room"
        if token in {"bedroom", "habitacion", "dormitorio"}:
            return "bedroom"
        if token in {"electrical", "electrico", "panel", "tablero"}:
            return "electrical_room"
        if token in {"plumbing", "sanitario", "agua", "desague"}:
            return "wet_area"

    if entity.id.startswith("json-door") or entity.id.startswith("json-window"):
        return "circulation"
    return level.space_types[0] if level.space_types else "unknown"


def _entity_to_semantic_element(
    entity_type: str,
    entity: InventoryEntity,
    *,
    discipline: str,
    level: LevelInventory,
    unit_id: str,
    space_id: str | None,
) -> SemanticElement:
    payload = asdict(entity)
    confidence = _base_confidence(entity)
    if space_id is None:
        confidence = min(confidence, 0.45)
    return SemanticElement(
        element_id=entity.id,
        element_type=entity_type,
        discipline=discipline,
        level_id=level.level_id,
        unit_id=unit_id,
        space_id=space_id,
        confidence_score=round(confidence, 3),
        source=_source_from_entity(entity),  # type: ignore[arg-type]
        evidence_refs=list(entity.source_refs),
        raw_entity_ids=[entity.id],
        attributes=payload,
    )


def enrich_semantics(
    *,
    project_id: str | None,
    project_name: str | None,
    discipline: str,
    levels: list[LevelInventory],
) -> SemanticBuilding:
    """
    Build semantic hierarchy from merged level inventories for any discipline.

    Selects the relevant entity groups per discipline and assigns confidence,
    spatial context, and evidence to each element. Deterministic only (no LLM).
    """
    entity_groups = _DISCIPLINE_ENTITY_GROUPS.get(discipline, _ALL_ENTITY_GROUPS)

    sem_levels: list[SemanticLevel] = []
    sem_spaces: list[SemanticSpace] = []
    sem_elements: list[SemanticElement] = []

    for level in levels:
        default_unit_id = f"{level.level_id}:unit_01"
        unit = SemanticUnit(
            unit_id=default_unit_id,
            level_id=level.level_id,
            name="default_unit",
            confidence_score=0.8,
            source="inferred",
            evidence_refs=list(level.source_refs),
            spaces=[],
        )

        spaces_by_name: dict[str, SemanticSpace] = {}
        for space_type in level.space_types:
            key = _normalize_token(space_type or "unknown")
            space_id = f"{level.level_id}:space:{key}"
            space = SemanticSpace(
                space_id=space_id,
                level_id=level.level_id,
                unit_id=default_unit_id,
                name=key,
                space_type=key,
                confidence_score=0.7,
                source="inferred",
                evidence_refs=list(level.source_refs),
                element_ids=[],
            )
            spaces_by_name[key] = space

        for entity_type, attr_name in entity_groups:
            for entity in getattr(level, attr_name, []):
                inferred_space = _normalize_token(_infer_space_name(entity, level))
                space_id: str | None = None
                if inferred_space != "unknown":
                    if inferred_space not in spaces_by_name:
                        spaces_by_name[inferred_space] = SemanticSpace(
                            space_id=f"{level.level_id}:space:{inferred_space}",
                            level_id=level.level_id,
                            unit_id=default_unit_id,
                            name=inferred_space,
                            space_type=inferred_space,
                            confidence_score=0.65,
                            source="inferred",
                            evidence_refs=list(entity.source_refs),
                            element_ids=[],
                        )
                    space_id = spaces_by_name[inferred_space].space_id

                sem_element = _entity_to_semantic_element(
                    entity_type,
                    entity,
                    discipline=discipline,
                    level=level,
                    unit_id=default_unit_id,
                    space_id=space_id,
                )
                sem_elements.append(sem_element)
                if space_id is not None:
                    spaces_by_name[inferred_space].element_ids.append(sem_element.element_id)

        level_spaces = list(spaces_by_name.values())
        unit.spaces = level_spaces
        sem_spaces.extend(level_spaces)
        sem_levels.append(
            SemanticLevel(
                level_id=level.level_id,
                level_name=level.level_name,
                confidence_score=0.75,
                source_refs=list(level.source_refs),
                units=[unit],
                orphan_space_ids=[],
            )
        )

    confidence = 0.0
    if sem_elements:
        confidence = sum(element.confidence_score for element in sem_elements) / len(sem_elements)

    return SemanticBuilding(
        project_id=project_id,
        project_name=project_name,
        discipline=discipline,
        confidence_score=round(confidence, 3),
        levels=sem_levels,
        spaces=sem_spaces,
        elements=sem_elements,
        metadata={"mode": "deterministic_phase1"},
    )


def enrich_architecture_semantics(
    *,
    project_id: str | None,
    project_name: str | None,
    levels: list[LevelInventory],
) -> SemanticBuilding:
    """Backward-compatible wrapper for architecture discipline."""
    return enrich_semantics(
        project_id=project_id,
        project_name=project_name,
        discipline="arquitectura",
        levels=levels,
    )
