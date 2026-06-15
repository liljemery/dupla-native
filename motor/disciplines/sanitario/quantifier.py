"""
Sanitary/plumbing discipline quantifier.

Filters wet-area and plumbing-related takeoffs.
"""

from __future__ import annotations

from typing import Iterable

from agents.quantifier_agent import quantify_inventory as _quantify_all
from core.schemas import LevelInventory, QuantityTakeoff

_SANITARY_ITEM_TYPES = frozenset({
    "wet_area_count", "wet_area_area", "wet_area_fixture_count",
    "floor_waterproofing",
})

_PLUMBING_FIXTURE_TYPES = frozenset({
    "water_supply_point", "drain_point", "vent_pipe", "cleanout",
    "floor_drain", "water_heater_connection", "washing_machine_connection",
    "hose_bib", "valve", "water_meter", "cistern", "pump",
    "toilet", "sink", "shower_base", "bathtub", "bidet",
    "urinal", "laundry_sink", "kitchen_sink", "water_heater",
    "plumbing_other",
})


def quantify(levels: Iterable[LevelInventory]) -> list[QuantityTakeoff]:
    """Sanitary/plumbing quantification."""
    all_takeoffs = _quantify_all(list(levels))
    result: list[QuantityTakeoff] = []
    for t in all_takeoffs:
        if t.item_type in _SANITARY_ITEM_TYPES:
            result.append(t)
            continue
        if t.item_type == "fixture_count":
            fixture_type = t.inputs.get("fixture_type", "")
            discipline = t.inputs.get("discipline") or ""
            if fixture_type in _PLUMBING_FIXTURE_TYPES or discipline == "plumbing":
                result.append(t)
    return result
