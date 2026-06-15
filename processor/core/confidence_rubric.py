"""
Confidence scoring rubric for inventory and takeoff entities.

Centralises the heuristic that previously lived as scattered float literals
(0.65, 0.70, 0.88, ...). Each contribution is bounded and explicit so we can
tune deltas in one place and document the reasoning in audit logs.

Score ∈ [0.0, 1.0]. Anything below ``review_threshold`` (default 0.65)
should be flagged for human review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_BASE = 0.50

_DELTA_OCR_CONFIRMED = +0.30
_DELTA_GEOM_ONLY = -0.20
_DELTA_OCR_ONLY = -0.10
_DELTA_OCR_OVERRIDE = +0.05
_DELTA_UNIT_AMBIGUOUS = -0.10
_DELTA_DIMENSIONS_COMPLETE = +0.15
_DELTA_LABELED_ENTITY = +0.10
_DELTA_DEFAULTS_USED = -0.15
_DELTA_ASSUMPTION_HEAVY = -0.10

_REVIEW_THRESHOLD = 0.65


@dataclass
class ConfidenceBreakdown:
    """Detailed breakdown of how a confidence score was computed."""

    score: float
    contributions: list[tuple[str, float]] = field(default_factory=list)
    requiere_revision: bool = False


def score(
    *,
    ocr_confirmed: bool = False,
    ocr_only: bool = False,
    geom_only: bool = False,
    ocr_override: bool = False,
    unit_ambiguous: bool = False,
    dimensions_complete: bool = False,
    labeled_entity: bool = False,
    defaults_used: bool = False,
    assumption_count: int = 0,
    review_threshold: float = _REVIEW_THRESHOLD,
) -> ConfidenceBreakdown:
    """Compute a confidence score from named evidence signals.

    Mutually exclusive signals (e.g. ocr_confirmed vs ocr_only) are caller
    responsibility — if both are passed, both deltas apply.
    """
    contributions: list[tuple[str, float]] = []

    def _apply(label: str, delta: float, condition: bool) -> None:
        if condition and delta != 0.0:
            contributions.append((label, delta))

    _apply("ocr_confirmed", _DELTA_OCR_CONFIRMED, ocr_confirmed)
    _apply("ocr_only", _DELTA_OCR_ONLY, ocr_only)
    _apply("geom_only", _DELTA_GEOM_ONLY, geom_only)
    _apply("ocr_override", _DELTA_OCR_OVERRIDE, ocr_override)
    _apply("unit_ambiguous", _DELTA_UNIT_AMBIGUOUS, unit_ambiguous)
    _apply("dimensions_complete", _DELTA_DIMENSIONS_COMPLETE, dimensions_complete)
    _apply("labeled_entity", _DELTA_LABELED_ENTITY, labeled_entity)
    _apply("defaults_used", _DELTA_DEFAULTS_USED, defaults_used)

    if assumption_count > 0:
        clamped = min(assumption_count, 4)
        _apply("assumption_heavy", _DELTA_ASSUMPTION_HEAVY * clamped / 4, True)

    raw = _BASE + sum(delta for _, delta in contributions)
    final = max(0.0, min(1.0, raw))
    return ConfidenceBreakdown(
        score=final,
        contributions=contributions,
        requiere_revision=final < review_threshold,
    )


def score_vision_entity(raw_entity: dict[str, Any]) -> ConfidenceBreakdown:
    """Score a single raw vision entity (e.g. one entry of walls / doors / structural_elements)."""
    labeled = bool(
        (raw_entity.get("label") or "").strip()
        or (raw_entity.get("wall_typology") or "").strip()
        or (raw_entity.get("schedule_row_text") or "").strip()
    )

    dims_complete = _entity_dimensions_complete(raw_entity)
    defaults_used = bool(raw_entity.get("missing_detail_sheets"))
    unit_ambiguous = False

    explicit_unit = str(raw_entity.get("unit") or "").strip().lower()
    if explicit_unit in {"", "unit", "und", "ud"} and (
        raw_entity.get("type") in {"slab", "footing", "beam", "column"}
    ):
        unit_ambiguous = True

    return score(
        labeled_entity=labeled,
        dimensions_complete=dims_complete,
        defaults_used=defaults_used,
        unit_ambiguous=unit_ambiguous,
    )


def _entity_dimensions_complete(raw_entity: dict[str, Any]) -> bool:
    has_section = (
        raw_entity.get("section_width_m") is not None
        and raw_entity.get("section_height_m") is not None
    ) or raw_entity.get("section_diameter_m") is not None
    has_extent = (
        raw_entity.get("length_m") is not None
        or raw_entity.get("area_m2") is not None
        or raw_entity.get("estimated_length_m") is not None
    )
    return has_section and has_extent
