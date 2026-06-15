"""
Rebar notation parser and weight calculator.

Reads standard Dominican/ACI bar notation from plan text and computes
weights using catalog bar weights -- NO volumetric estimation ratios.

Notation formats supported:
  - "4#6+2#5"  -> 4 bars of #6 (3/4") + 2 bars of #5 (5/8")
  - "#3@0.15"  -> #3 stirrups at 15cm spacing
  - "8 f 3/4"  -> 8 bars of 3/4" diameter
  - "4 varillas #6" -> 4 bars of #6
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("dupla.rebar")


# Standard bar weights per ASTM A615 / Dominican practice
REBAR_CATALOG: dict[str, dict[str, Any]] = {
    "#2": {"diameter_in": 0.250, "diameter_mm": 6.4,  "weight_kg_m": 0.25, "size_fraction": "1/4"},
    "#3": {"diameter_in": 0.375, "diameter_mm": 9.5,  "weight_kg_m": 0.56, "size_fraction": "3/8"},
    "#4": {"diameter_in": 0.500, "diameter_mm": 12.7, "weight_kg_m": 0.99, "size_fraction": "1/2"},
    "#5": {"diameter_in": 0.625, "diameter_mm": 15.9, "weight_kg_m": 1.55, "size_fraction": "5/8"},
    "#6": {"diameter_in": 0.750, "diameter_mm": 19.1, "weight_kg_m": 2.24, "size_fraction": "3/4"},
    "#7": {"diameter_in": 0.875, "diameter_mm": 22.2, "weight_kg_m": 3.04, "size_fraction": "7/8"},
    "#8": {"diameter_in": 1.000, "diameter_mm": 25.4, "weight_kg_m": 3.97, "size_fraction": "1"},
    "#9": {"diameter_in": 1.128, "diameter_mm": 28.7, "weight_kg_m": 5.06, "size_fraction": "1-1/8"},
    "#10": {"diameter_in": 1.270, "diameter_mm": 32.3, "weight_kg_m": 6.40, "size_fraction": "1-1/4"},
}

FRACTION_TO_BAR: dict[str, str] = {
    "1/4": "#2", "6mm": "#2",
    "3/8": "#3", "10mm": "#3",
    "1/2": "#4", "12mm": "#4", "13mm": "#4",
    "5/8": "#5", "16mm": "#5",
    "3/4": "#6", "19mm": "#6", "20mm": "#6",
    "7/8": "#7", "22mm": "#7",
    "1": "#8", "25mm": "#8",
    "1-1/8": "#9", "28mm": "#9", "29mm": "#9",
    "1-1/4": "#10", "32mm": "#10",
}

SPLICE_LENGTH_DIAMETERS: dict[str, int] = {
    "grado_40": 30,
    "grado_60": 40,
}


@dataclass
class BarGroup:
    """A group of bars of the same size."""
    count: int
    bar_size: str       # "#3", "#6", etc.
    weight_kg_m: float  # from catalog
    diameter_mm: float


@dataclass
class StirrupSpec:
    """Stirrup specification parsed from notation."""
    bar_size: str
    spacing_m: float
    weight_kg_m: float
    diameter_mm: float


@dataclass
class ParsedReinforcement:
    """Complete parsed reinforcement for an element."""
    main_bars: list[BarGroup]
    stirrups: StirrupSpec | None = None
    tie_bars: list[BarGroup] | None = None
    steel_grade: str | None = None
    parse_warnings: list[str] | None = None


def _normalize_bar_size(raw: str) -> str | None:
    """Convert various bar size notations to standard #N format."""
    raw = raw.strip().lower().replace('"', '').replace("'", "")

    if re.match(r"^#\d+$", raw):
        return raw.upper()

    match = re.match(r"^(\d+)$", raw)
    if match:
        num = int(match.group(1))
        if 2 <= num <= 10:
            return f"#{num}"

    for fraction, bar in FRACTION_TO_BAR.items():
        if fraction in raw:
            return bar

    match = re.match(r"^(\d+)\s*mm$", raw)
    if match:
        key = f"{match.group(1)}mm"
        if key in FRACTION_TO_BAR:
            return FRACTION_TO_BAR[key]

    return None


def parse_main_bars(notation: str) -> list[BarGroup]:
    """Parse main bar notation like '4#6+2#5' or '8 f 3/4'.

    Returns list of BarGroup with count and catalog weight.
    """
    if not notation:
        return []

    notation = notation.strip()
    groups: list[BarGroup] = []
    warnings: list[str] = []

    parts = re.split(r"[+,;]", notation)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        match = re.match(r"(\d+)\s*[#fFφΦ]\s*([0-9/\-]+)", part)
        if not match:
            match = re.match(r"(\d+)\s+(?:varillas?\s+)?[#fFφΦ]?\s*([0-9/\-]+)", part, re.IGNORECASE)

        if not match:
            match = re.match(r"(\d+)\s*[#](\d+)", part)

        if match:
            count = int(match.group(1))
            bar_size = _normalize_bar_size(match.group(2))
            if bar_size and bar_size in REBAR_CATALOG:
                cat = REBAR_CATALOG[bar_size]
                groups.append(BarGroup(
                    count=count,
                    bar_size=bar_size,
                    weight_kg_m=cat["weight_kg_m"],
                    diameter_mm=cat["diameter_mm"],
                ))
            else:
                warnings.append(f"Unknown bar size in '{part}'")
        else:
            warnings.append(f"Could not parse bar group: '{part}'")

    if warnings:
        logger.debug("Bar parse warnings for '%s': %s", notation, warnings)

    return groups


def parse_stirrups(notation: str) -> StirrupSpec | None:
    """Parse stirrup notation like '#3@0.15' or '#3 @ 15cm'.

    Returns StirrupSpec or None if unparseable.
    """
    if not notation:
        return None

    notation = notation.strip()

    match = re.match(r"[#fFφΦ]?\s*([0-9/\-]+)\s*@\s*([0-9.]+)\s*(m|cm|mm)?", notation)
    if not match:
        logger.debug("Could not parse stirrup notation: '%s'", notation)
        return None

    bar_raw = match.group(1)
    spacing_val = float(match.group(2))
    unit = (match.group(3) or "m").lower()

    if unit == "cm":
        spacing_m = spacing_val / 100
    elif unit == "mm":
        spacing_m = spacing_val / 1000
    else:
        spacing_m = spacing_val
        if spacing_m > 1.0:
            spacing_m = spacing_val / 100

    bar_size = _normalize_bar_size(bar_raw)
    if not bar_size or bar_size not in REBAR_CATALOG:
        logger.debug("Unknown stirrup bar size: '%s'", bar_raw)
        return None

    cat = REBAR_CATALOG[bar_size]
    return StirrupSpec(
        bar_size=bar_size,
        spacing_m=spacing_m,
        weight_kg_m=cat["weight_kg_m"],
        diameter_mm=cat["diameter_mm"],
    )


def parse_reinforcement(
    main_bars_notation: str | None,
    stirrups_notation: str | None,
    steel_grade: str | None = None,
    tie_bars_notation: str | None = None,
) -> ParsedReinforcement:
    """Parse all reinforcement notations for a structural element."""
    return ParsedReinforcement(
        main_bars=parse_main_bars(main_bars_notation or ""),
        stirrups=parse_stirrups(stirrups_notation or ""),
        tie_bars=parse_main_bars(tie_bars_notation or "") or None,
        steel_grade=steel_grade,
    )


# ---------------------------------------------------------------------------
# Weight calculation (arithmetic on plan data, NOT estimation)
# ---------------------------------------------------------------------------

def calculate_main_bar_weight(
    bars: list[BarGroup],
    element_length_m: float,
    *,
    steel_grade: str | None = None,
    include_splice: bool = False,
    splice_count: int = 0,
) -> dict[str, Any]:
    """Calculate weight of longitudinal bars.

    Args:
        bars: Parsed bar groups from plan notation.
        element_length_m: Span or length from plan.
        steel_grade: For splice length calculation if include_splice is True.
        include_splice: Whether to add splice lengths (normative assumption).
        splice_count: Number of splices per bar.

    Returns:
        Dict with total_kg, breakdown per bar size, and calculation details.
    """
    breakdown: list[dict[str, Any]] = []
    total_kg = 0.0
    assumptions: list[str] = []

    for group in bars:
        bar_length = element_length_m
        splice_addition = 0.0

        if include_splice and splice_count > 0 and steel_grade:
            diameters = SPLICE_LENGTH_DIAMETERS.get(steel_grade, 40)
            splice_length_m = (group.diameter_mm / 1000) * diameters
            splice_addition = splice_length_m * splice_count
            bar_length += splice_addition
            assumptions.append(
                f"{group.bar_size}: splice length = {diameters}d = {splice_length_m:.3f}m x {splice_count} splices "
                f"(normative, {steel_grade})"
            )

        weight = group.count * bar_length * group.weight_kg_m
        total_kg += weight
        breakdown.append({
            "bar_size": group.bar_size,
            "count": group.count,
            "length_per_bar_m": bar_length,
            "weight_kg_m": group.weight_kg_m,
            "splice_addition_m": splice_addition,
            "subtotal_kg": round(weight, 2),
        })

    return {
        "total_kg": round(total_kg, 2),
        "element_length_m": element_length_m,
        "breakdown": breakdown,
        "assumptions": assumptions,
    }


def calculate_stirrup_weight(
    stirrup: StirrupSpec,
    element_length_m: float,
    section_width_m: float,
    section_height_m: float,
    *,
    cover_m: float = 0.04,
) -> dict[str, Any]:
    """Calculate weight of stirrups.

    Perimeter = 2 * ((width - 2*cover) + (height - 2*cover)) + hook allowance.
    Count = element_length / spacing + 1.
    """
    net_width = section_width_m - 2 * cover_m
    net_height = section_height_m - 2 * cover_m
    hook_allowance_m = 0.20
    perimeter_m = 2 * (net_width + net_height) + hook_allowance_m

    stirrup_count = int(element_length_m / stirrup.spacing_m) + 1
    total_length_m = stirrup_count * perimeter_m
    total_kg = total_length_m * stirrup.weight_kg_m

    return {
        "total_kg": round(total_kg, 2),
        "stirrup_bar": stirrup.bar_size,
        "spacing_m": stirrup.spacing_m,
        "count": stirrup_count,
        "perimeter_m": round(perimeter_m, 3),
        "total_length_m": round(total_length_m, 2),
        "assumptions": [
            f"Cover = {cover_m}m (standard)",
            f"Hook allowance = {hook_allowance_m}m",
            f"Perimeter = 2*({net_width:.3f}+{net_height:.3f}) + {hook_allowance_m} = {perimeter_m:.3f}m",
        ],
    }
