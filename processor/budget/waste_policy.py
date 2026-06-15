"""
Waste / merma policy for Dominican Republic construction budgets.

Typical office practice adds a percentage on top of the net measured quantity
to absorb cutting losses, lap splices, mortar joints, mixing waste, etc.

Numbers here are deliberately conservative midpoints used across Punta Cana
contractors. They can be overridden via ``ProjectContext.metadata``:

    {
        "waste_policy_overrides": {
            "*_concrete_volume": 0.05,
            "wall_finish_*": 0.10,
        }
    }

Each entry is a fnmatch-style pattern matched against ``item_type``.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Iterable

# Pattern -> waste fraction. Ordered from most specific to least specific.
DEFAULT_WASTE_BY_PATTERN: tuple[tuple[str, float], ...] = (
    ("*_concrete_volume", 0.03),
    ("*_reinforcement_kg", 0.05),
    ("*_formwork_*", 0.10),
    ("wall_finish_*", 0.07),
    ("wall_net_area", 0.05),
    ("wall_volume", 0.05),
    ("wall_waterproofing", 0.05),
    ("floor_finish*", 0.07),
    ("floor_tile*", 0.10),
    ("ceiling_finish*", 0.05),
    ("excavation_volume", 0.10),
    ("door_*", 0.00),
    ("window_*", 0.00),
    ("fixture_*", 0.00),
)


def waste_fraction_for(
    item_type: str,
    *,
    overrides: dict[str, float] | None = None,
) -> float:
    """Return the merma fraction (0.0..1.0) for an item_type.

    Override mapping is checked first; otherwise the default table is scanned
    in order and the first matching pattern wins. Unknown item_types get 0.0.
    """
    if not item_type:
        return 0.0

    item_type = item_type.lower()
    if overrides:
        for pattern, fraction in overrides.items():
            if fnmatchcase(item_type, pattern.lower()):
                return _clamp_fraction(fraction)

    for pattern, fraction in DEFAULT_WASTE_BY_PATTERN:
        if fnmatchcase(item_type, pattern):
            return _clamp_fraction(fraction)
    return 0.0


def apply_waste(
    quantity_neta: float,
    item_type: str,
    *,
    overrides: dict[str, float] | None = None,
) -> tuple[float, float, str]:
    """Apply waste policy to a net quantity.

    Returns (quantity_con_merma, waste_fraction, formula_note).
    """
    fraction = waste_fraction_for(item_type, overrides=overrides)
    if fraction <= 0:
        return quantity_neta, 0.0, ""
    quantity_con_merma = quantity_neta * (1.0 + fraction)
    note = f"quantity_neta * (1 + {fraction:.2%}) merma"
    return quantity_con_merma, fraction, note


def categorize(item_types: Iterable[str]) -> dict[str, float]:
    """Return a mapping item_type -> waste_fraction (diagnostic helper)."""
    return {it: waste_fraction_for(it) for it in item_types}


def _clamp_fraction(value: float) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(0.5, f))
