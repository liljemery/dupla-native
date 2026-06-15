"""
Electrical discipline quantifier.

Filters fixture-type takeoffs with electrical discipline markers.
"""

from __future__ import annotations

from typing import Iterable

from agents.quantifier_agent import quantify_inventory as _quantify_all
from core.schemas import LevelInventory, QuantityTakeoff

_ELECTRICAL_FIXTURE_TYPES = frozenset({
    "outlet_110v", "outlet_220v",
    "switch_single", "switch_double", "switch_triple", "switch_dimmer",
    "luminaire_ceiling", "luminaire_wall", "luminaire_recessed",
    "panel_breaker", "intercom", "doorbell",
    "data_outlet", "tv_outlet", "phone_outlet",
    "smoke_detector", "emergency_light",
    "fan_connection", "ac_connection",
    "electrical_other",
})


def quantify(levels: Iterable[LevelInventory]) -> list[QuantityTakeoff]:
    """Electrical quantification -- filter electrical fixtures."""
    all_takeoffs = _quantify_all(list(levels))
    result: list[QuantityTakeoff] = []
    for t in all_takeoffs:
        if t.item_type != "fixture_count":
            continue
        fixture_type = t.inputs.get("fixture_type", "")
        discipline = t.inputs.get("discipline") or ""
        if fixture_type in _ELECTRICAL_FIXTURE_TYPES or discipline == "electrical":
            result.append(t)
    return result
