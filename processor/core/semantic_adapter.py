"""
Adapter from semantic quality decisions to quantifier-consumable inventory.
"""

from __future__ import annotations

from typing import Iterable

from core.quality_models import QualityReport
from core.schemas import LevelInventory, level_inventory_from_dict
from core.semantic_models import SemanticBuilding

_ENTITY_LIST_FIELDS = (
    "walls",
    "openings",
    "doors",
    "windows",
    "wet_areas",
    "kitchens",
    "stairs",
    "fixtures",
    "structural_elements",
)


def _blocked_element_ids(report: QualityReport) -> set[str]:
    return {
        issue.element_id
        for issue in report.blocked_items
        if issue.element_id
    }


def adapt_semantic_to_inventory(
    building: SemanticBuilding,
    quality_report: QualityReport,
    levels: Iterable[LevelInventory],
) -> list[LevelInventory]:
    """
    Filter inventory entities according to semantic quality status.

    BLOCKED semantic elements are excluded from quantification.
    """
    blocked_ids = _blocked_element_ids(quality_report)
    out: list[LevelInventory] = []

    for level in levels:
        payload = level.to_dict()
        for key in _ENTITY_LIST_FIELDS:
            entities = list(payload.get(key, []))
            payload[key] = [entity for entity in entities if entity.get("id") not in blocked_ids]

        payload_inputs = dict(payload.get("inputs", {}))
        payload_inputs["semantic_layer"] = {
            "enabled": True,
            "discipline": building.discipline,
            "blocked_ids_count": len(blocked_ids),
            "blocked_ids": sorted(blocked_ids),
        }
        payload["inputs"] = payload_inputs
        out.append(level_inventory_from_dict(payload, default_source=level.source))

    return out
