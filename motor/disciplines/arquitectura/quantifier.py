"""
Architectural discipline quantifier.

For Phase 1 this re-exports the existing monolithic quantifier unchanged.
In later phases, discipline-specific quantifier functions will live here.
"""

from __future__ import annotations

from typing import Iterable

from agents.quantifier_agent import quantify_inventory as _quantify_inventory
from core.schemas import LevelInventory, QuantityTakeoff


def quantify(levels: Iterable[LevelInventory]) -> list[QuantityTakeoff]:
    """Architectural quantification -- delegates to the existing quantifier."""
    return _quantify_inventory(levels)
