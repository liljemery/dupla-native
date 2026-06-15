"""
Structural discipline quantifier.

Produces takeoffs focused on concrete volumes, reinforcement weight,
formwork areas, and excavation volumes for foundations.

For Phase 3 this re-exports the existing structural quantification
functions from the monolithic quantifier (which already handles
structural elements).  Future iterations will add structural-specific
formulas like excavation volumes derived from footing dimensions.
"""

from __future__ import annotations

from typing import Iterable

from agents.quantifier_agent import quantify_inventory as _quantify_all
from core.schemas import LevelInventory, QuantityTakeoff

_STRUCTURAL_ITEM_TYPES = frozenset({
    "structural_count", "structural_length", "structural_area", "structural_volume",
    "beam_concrete_volume", "beam_volume", "beam_area", "beam_length", "beam_count",
    "beam_formwork_area_hint", "beam_reinforcement_kg",
    "column_concrete_volume", "column_volume", "column_area", "column_length", "column_count",
    "column_formwork_area_hint", "column_reinforcement_kg",
    "slab_concrete_volume", "slab_area", "slab_count",
    "slab_formwork_area_hint", "slab_reinforcement_kg",
    "footing_concrete_volume", "footing_volume", "footing_area",
    "footing_formwork_area_hint", "footing_reinforcement_kg",
    "stair_count",
})


def quantify(levels: Iterable[LevelInventory]) -> list[QuantityTakeoff]:
    """Structural quantification -- filter structural-only takeoffs."""
    all_takeoffs = _quantify_all(list(levels))
    return [t for t in all_takeoffs if t.item_type in _STRUCTURAL_ITEM_TYPES]
