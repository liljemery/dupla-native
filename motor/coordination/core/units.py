"""Unit normalization helpers for coordination geometry.

The coordination engine historically stores active clash geometry in millimeters.
Phase 1 also exposes meter factors for diagnostic and normalized-geometry flows.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

Unit = Literal["mm", "cm", "m"]

INSUNITS_TO_MM: dict[int, float] = {
    0: 1.0,
    1: 25.4,      # inches
    2: 304.8,     # feet
    4: 1.0,       # millimeters
    5: 10.0,      # centimeters
    6: 1000.0,    # meters
    7: 1_000_000.0,
    10: 914.4,    # yards
    14: 100.0,    # decimeters
}

INSUNITS_TO_METERS: dict[int, float] = {code: factor / 1000.0 for code, factor in INSUNITS_TO_MM.items()}

UNIT_CANDIDATE_FACTORS_TO_METERS: dict[str, float] = {
    "mm": 0.001,
    "cm": 0.01,
    "m": 1.0,
    "inch": 0.0254,
    "ft": 0.3048,
}

PLAUSIBLE_BUILDING_AXIS_M = (20.0, 300.0)
# A real CAD element (wall segment, door ~0.9 m, fixture, room) spans ~5 cm to ~12 m.
# Used as an independent second signal so a tiny-real-building + far-stray span cannot
# fool the outline check into trusting a wrong unit (e.g. INSUNITS=1/4 on meter geometry).
PLAUSIBLE_ELEMENT_AXIS_M = (0.05, 12.0)
_NUMERIC_UNIT_RE = re.compile(r"-?\d+(?:[\.,]\d+)?")


@dataclass(frozen=True)
class UnitInference:
    factor_to_meters: float
    unit_label: str
    reason: str
    outline_before: tuple[float, float] | None = None
    outline_after: tuple[float, float] | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class UnitReconciliation:
    factor_to_meters: float
    source: str
    declared_factor_to_meters: float | None
    inferred: UnitInference
    warning: dict[str, Any] | None = None


def to_mm(value: float, unit: Unit) -> float:
    """Convierte una longitud al sistema interno del motor de coordinación (milímetros)."""
    if unit == "mm":
        return float(value)
    if unit == "cm":
        return float(value) * 10.0
    if unit == "m":
        return float(value) * 1000.0
    raise ValueError(f"Unidad no soportada: {unit!r}")


def from_mm(value_mm: float, unit: Unit) -> float:
    """Convierte desde mm al unit solicitado (para reportes)."""
    if unit == "mm":
        return float(value_mm)
    if unit == "cm":
        return float(value_mm) / 10.0
    if unit == "m":
        return float(value_mm) / 1000.0
    raise ValueError(f"Unidad no soportada: {unit!r}")


def insunits_to_mm_factor(insunits: int | None, *, measurement: int | None = None) -> float:
    """Return the CAD declared unit factor to millimeters."""
    code = int(insunits or 0)
    factor = INSUNITS_TO_MM.get(code)
    if factor is not None and code != 0:
        return factor
    if measurement is not None:
        return 1.0 if int(measurement) == 1 else 25.4
    return INSUNITS_TO_MM[0]


def insunits_to_meters_factor(insunits: int | None, *, measurement: int | None = None) -> float | None:
    code = int(insunits or 0)
    if code in INSUNITS_TO_METERS and code != 0:
        return INSUNITS_TO_METERS[code]
    if measurement is not None:
        return 0.001 if int(measurement) == 1 else 0.0254
    return None


def _bounds_from_points(points: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    if not points:
        return None
    xs = [p[0] for p in points if math.isfinite(p[0])]
    ys = [p[1] for p in points if math.isfinite(p[1])]
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _robust_outline_size(geometry: Any) -> tuple[float, float] | None:
    """Compute robust percentile outline size from geometry rows or bounds.

    Promoted from the SERENA sanitation POC's percentile outline idea. Accepts:
    - list of records with ``model_center`` or ``center``
    - list of bounds tuples/lists
    - dict with ``elements`` or ``outline_bounds``
    """
    if isinstance(geometry, dict):
        if geometry.get("outline_bounds"):
            b = geometry["outline_bounds"]
            return abs(float(b[2]) - float(b[0])), abs(float(b[3]) - float(b[1]))
        geometry = geometry.get("elements") or geometry.get("geometry") or []
    points: list[tuple[float, float]] = []
    bounds_rows: list[tuple[float, float, float, float]] = []
    for row in geometry or []:
        if isinstance(row, dict):
            center = row.get("model_center") or row.get("center")
            bounds = row.get("model_bounds") or row.get("bounds") or row.get("bbox")
        else:
            center = None
            bounds = row
        if center and len(center) >= 2:
            try:
                points.append((float(center[0]), float(center[1])))
                continue
            except Exception:
                pass
        if bounds and len(bounds) >= 4:
            try:
                b = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
                bounds_rows.append(b)
                points.append(((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0))
            except Exception:
                pass
    if len(points) >= 20:
        xs = sorted(p[0] for p in points)
        ys = sorted(p[1] for p in points)
        lo = max(0, int(0.05 * (len(points) - 1)))
        hi = min(len(points) - 1, int(0.95 * (len(points) - 1)))
        return abs(xs[hi] - xs[lo]), abs(ys[hi] - ys[lo])
    bounds = _bounds_from_points(points)
    if bounds is not None:
        return abs(bounds[2] - bounds[0]), abs(bounds[3] - bounds[1])
    if bounds_rows:
        min_x = min(b[0] for b in bounds_rows)
        min_y = min(b[1] for b in bounds_rows)
        max_x = max(b[2] for b in bounds_rows)
        max_y = max(b[3] for b in bounds_rows)
        return abs(max_x - min_x), abs(max_y - min_y)
    return None


def _cleaned_outline_and_element_axis(geometry: Any) -> tuple[tuple[float, float] | None, float | None]:
    """Outline size + median element max-axis from the CLEANED main cluster (raw units).

    Strays are removed first (percentile main cluster) so the outline reflects the real
    building core, not a tiny building plus a far outlier/paperspace artifact. The median
    element axis is returned as an independent unit signal. Falls back to the robust
    percentile span when rows carry no usable bounds.
    """
    # Explicit outline only (no element rows): nothing to clean, no element signal.
    if isinstance(geometry, dict) and geometry.get("outline_bounds"):
        b = geometry["outline_bounds"]
        return (abs(float(b[2]) - float(b[0])), abs(float(b[3]) - float(b[1]))), None
    if isinstance(geometry, dict):
        rows = geometry.get("elements") or geometry.get("geometry") or []
    else:
        rows = geometry or []
    norm: list[dict[str, Any]] = []
    for row in rows:
        bounds = (row.get("model_bounds") or row.get("bounds") or row.get("bbox")) if isinstance(row, dict) else row
        center = (row.get("model_center") or row.get("center")) if isinstance(row, dict) else None
        if bounds and len(bounds) >= 4:
            try:
                b = [float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3])]
            except Exception:
                continue
            entry: dict[str, Any] = {"model_bounds": b}
            if center and len(center) >= 2:
                try:
                    entry["model_center"] = [float(center[0]), float(center[1])]
                except Exception:
                    pass
            norm.append(entry)
    if not norm:
        return _robust_outline_size(geometry), None
    # Local import avoids a hard module-level dependency (no import cycle: cleaner is leaf).
    from coordination.core.geometry_cleaner import clean_geometry

    cleaned = clean_geometry(norm, method="percentile")
    main = cleaned.main_geometry or norm
    outline = cleaned.cleaned_outline
    size = (abs(outline[2] - outline[0]), abs(outline[3] - outline[1])) if outline else _robust_outline_size(geometry)
    axes = sorted(
        max(abs(r["model_bounds"][2] - r["model_bounds"][0]), abs(r["model_bounds"][3] - r["model_bounds"][1]))
        for r in main
    )
    median_axis = axes[len(axes) // 2] if axes else None
    return size, median_axis


def _dimension_text_scale_hint(dimensions: list[dict[str, Any]] | None) -> float | None:
    """Promoted from json_processor._infer_global_scale dimension-text heuristic.

    Returns drawing-units-per-real-unit style factors from legacy code:
    1000 ~= millimeters, 100 ~= centimeters, 10 ~= decimeters.
    Converted by caller to meters factors.
    """
    factors: list[float] = []
    for dim in dimensions or []:
        meas = dim.get("measurement")
        text = str(dim.get("text") or "")
        if meas is None or not text:
            continue
        try:
            match = _NUMERIC_UNIT_RE.search(text.replace(",", "."))
            if not match:
                continue
            text_num = float(match.group())
            meas_num = float(meas)
            if text_num <= 0 or meas_num <= 0:
                continue
            ratio = meas_num / text_num
            if 800 < ratio < 1200:
                factors.append(1000.0)
            elif 80 < ratio < 120:
                factors.append(100.0)
            elif 8 < ratio < 12:
                factors.append(10.0)
        except Exception:
            continue
    if factors:
        return Counter(factors).most_common(1)[0][0]
    return None


def _geometry_length_scale_hint(geometry_hints: list[dict[str, Any]] | None) -> float | None:
    lengths = [float(g["length"]) for g in geometry_hints or [] if g.get("length") is not None]
    if not lengths:
        return None
    total_len = sum(lengths)
    top = sorted(lengths, reverse=True)[:100]
    avg_top = sum(top) / len(top)
    if total_len > 300_000.0 or avg_top > 3000.0:
        return 1000.0
    if total_len > 40_000.0 or avg_top > 300.0:
        return 100.0
    return None


def infer_units_from_geometry(
    geometry: Any,
    *,
    dimensions: list[dict[str, Any]] | None = None,
    geometry_hints: list[dict[str, Any]] | None = None,
    plausible_axis_m: tuple[float, float] = PLAUSIBLE_BUILDING_AXIS_M,
) -> UnitInference:
    """Infer factor-to-meters from geometry size and dimension heuristics."""
    outline, median_element_axis = _cleaned_outline_and_element_axis(geometry)
    dim_hint = _dimension_text_scale_hint(dimensions)
    if dim_hint:
        factor = 1.0 / dim_hint
        return UnitInference(
            factor_to_meters=factor,
            unit_label={1000.0: "mm", 100.0: "cm", 10.0: "dm"}.get(dim_hint, "dimension_hint"),
            reason=f"dimension_text_ratio={dim_hint}",
            outline_before=outline,
            outline_after=tuple(v * factor for v in outline) if outline else None,
        )
    len_hint = _geometry_length_scale_hint(geometry_hints)
    if len_hint:
        factor = 1.0 / len_hint
        return UnitInference(
            factor_to_meters=factor,
            unit_label={1000.0: "mm", 100.0: "cm"}.get(len_hint, "geometry_length_hint"),
            reason=f"geometry_length_hint={len_hint}",
            outline_before=outline,
            outline_after=tuple(v * factor for v in outline) if outline else None,
        )
    if not outline:
        return UnitInference(1.0, "m", "no_geometry_outline_fallback_m")

    low, high = plausible_axis_m
    elem_low, elem_high = PLAUSIBLE_ELEMENT_AXIS_M
    candidates: list[dict[str, Any]] = []
    for label, factor in UNIT_CANDIDATE_FACTORS_TO_METERS.items():
        scaled = tuple(v * factor for v in outline)
        axes_in_range = sum(1 for value in scaled if low <= value <= high)
        max_axis = max(scaled)
        min_axis = min(v for v in scaled if v > 0) if any(v > 0 for v in scaled) else 0.0
        penalty = 0.0
        if max_axis > high:
            penalty += (max_axis - high) / high
        if min_axis and min_axis < low:
            penalty += (low - min_axis) / low
        # Second signal: would a typical element be a plausible CAD element at this factor?
        element_axis_m = median_element_axis * factor if median_element_axis is not None else None
        element_ok = 1 if (element_axis_m is not None and elem_low <= element_axis_m <= elem_high) else 0
        candidates.append(
            {
                "unit": label,
                "factor_to_meters": factor,
                "outline_after": scaled,
                "axes_in_range": axes_in_range,
                "element_axis_m": element_axis_m,
                "element_ok": element_ok,
                "penalty": penalty,
            }
        )
    # Rank by combined evidence (outline axes in range + element-size agreement), then
    # by penalty, then by closeness to a typical ~120 m footprint.
    best = sorted(
        candidates,
        key=lambda c: (-(c["axes_in_range"] + c["element_ok"]), c["penalty"], abs(max(c["outline_after"]) - 120.0)),
    )[0]
    reason = "geometry_cleaned_outline_plausible_building"
    if median_element_axis is not None:
        reason += f"+element_size_signal(median_axis_m={best['element_axis_m']:.3f})"
    return UnitInference(
        factor_to_meters=float(best["factor_to_meters"]),
        unit_label=str(best["unit"]),
        reason=reason,
        outline_before=outline,
        outline_after=tuple(float(v) for v in best["outline_after"]),
        candidates=candidates,
    )


def reconcile_units(
    declared_insunits: int | None,
    inferred: UnitInference,
    *,
    discipline: str | None = None,
    measurement: int | None = None,
    tolerance_ratio: float = 0.05,
) -> UnitReconciliation:
    """Choose final factor-to-meters.

    INSUNITS is a hint only. If declaration and geometry inference disagree,
    geometry wins and a warning record is emitted.
    """
    declared = insunits_to_meters_factor(declared_insunits, measurement=measurement)
    if declared is None:
        return UnitReconciliation(inferred.factor_to_meters, "geometry_inferred", declared, inferred)
    denom = max(abs(declared), abs(inferred.factor_to_meters), 1e-12)
    disagrees = abs(declared - inferred.factor_to_meters) / denom > tolerance_ratio
    if not disagrees:
        return UnitReconciliation(declared, "declared_insunits_agrees", declared, inferred)
    warning = {
        "discipline": discipline,
        "declared_insunits": declared_insunits,
        "declared_factor_to_meters": declared,
        "inferred_factor_to_meters": inferred.factor_to_meters,
        "inferred_unit": inferred.unit_label,
        "outline_before": inferred.outline_before,
        "outline_after": inferred.outline_after,
        "decision": "trusted_geometry_over_insunits",
    }
    return UnitReconciliation(inferred.factor_to_meters, "geometry_over_declared_insunits", declared, inferred, warning)
