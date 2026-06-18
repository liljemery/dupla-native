"""Geometry cleanup helpers: robust main cluster and dominant grid cluster."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GeometryCleanupResult:
    main_geometry: list[dict[str, Any]]
    stray_geometry: list[dict[str, Any]]
    stray_count: int
    cleaned_centroid: tuple[float, float] | None
    cleaned_outline: tuple[float, float, float, float] | None
    method: str
    diagnostics: dict[str, Any]


def _bounds(row: dict[str, Any]) -> tuple[float, float, float, float] | None:
    raw = row.get("model_bounds") or row.get("bounds") or row.get("bbox")
    if not raw or len(raw) < 4:
        return None
    try:
        return float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])
    except Exception:
        return None


def _center(row: dict[str, Any]) -> tuple[float, float] | None:
    raw = row.get("model_center") or row.get("center")
    if raw and len(raw) >= 2:
        try:
            return float(raw[0]), float(raw[1])
        except Exception:
            pass
    bounds = _bounds(row)
    if bounds:
        return (bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0
    return None


def _union_bounds(rows: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    bounds = [b for row in rows if (b := _bounds(row))]
    if not bounds:
        return None
    return (
        min(b[0] for b in bounds),
        min(b[1] for b in bounds),
        max(b[2] for b in bounds),
        max(b[3] for b in bounds),
    )


def _centroid(rows: list[dict[str, Any]]) -> tuple[float, float] | None:
    centers = [c for row in rows if (c := _center(row))]
    if not centers:
        return None
    return sum(c[0] for c in centers) / len(centers), sum(c[1] for c in centers) / len(centers)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * pct / 100.0
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - pos) + values[hi] * (pos - lo)


def robust_main_cluster(
    geometry: list[dict[str, Any]],
    *,
    percentile_low: float = 5.0,
    percentile_high: float = 95.0,
    padding_ratio: float = 0.20,
) -> GeometryCleanupResult:
    """Separate strays using a robust percentile bbox.

    Promoted from ``stage_data_sanitation.py``.
    """
    rows = list(geometry or [])
    centers = [(row, c) for row in rows if (c := _center(row))]
    if not centers:
        return GeometryCleanupResult([], rows, len(rows), None, None, "percentile", {"reason": "no_centers"})
    xs = [c[0] for _row, c in centers]
    ys = [c[1] for _row, c in centers]
    lo_x = _percentile(xs, percentile_low)
    lo_y = _percentile(ys, percentile_low)
    hi_x = _percentile(xs, percentile_high)
    hi_y = _percentile(ys, percentile_high)
    span_x = max(hi_x - lo_x, 1e-9)
    span_y = max(hi_y - lo_y, 1e-9)
    min_x = lo_x - span_x * padding_ratio
    min_y = lo_y - span_y * padding_ratio
    max_x = hi_x + span_x * padding_ratio
    max_y = hi_y + span_y * padding_ratio
    main: list[dict[str, Any]] = []
    stray: list[dict[str, Any]] = []
    for row in rows:
        center = _center(row)
        if center and min_x <= center[0] <= max_x and min_y <= center[1] <= max_y:
            main.append(row)
        else:
            stray.append(row)
    return GeometryCleanupResult(
        main_geometry=main,
        stray_geometry=stray,
        stray_count=len(stray),
        cleaned_centroid=_centroid(main),
        cleaned_outline=_union_bounds(main),
        method="percentile_main_cluster",
        diagnostics={
            "percentile_low": percentile_low,
            "percentile_high": percentile_high,
            "cluster_window": (min_x, min_y, max_x, max_y),
            "input_count": len(rows),
            "main_count": len(main),
        },
    )


def dominant_grid_cluster(
    geometry: list[dict[str, Any]],
    *,
    cell_size: float = 500.0,
    max_entity_span: float = 100.0,
) -> GeometryCleanupResult:
    """Dominant-cluster grid-bin detection promoted from active ACCORE profiling."""
    rows = list(geometry or [])
    cluster_counts: dict[tuple[int, int], int] = {}
    cluster_area_like: dict[tuple[int, int], float] = {}
    cluster_rows: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:
        bounds = _bounds(row)
        center = _center(row)
        if not bounds or not center:
            continue
        span_x = abs(bounds[2] - bounds[0])
        span_y = abs(bounds[3] - bounds[1])
        if span_x > max_entity_span or span_y > max_entity_span:
            continue
        key = (int(math.floor(center[0] / cell_size)), int(math.floor(center[1] / cell_size)))
        cluster_counts[key] = cluster_counts.get(key, 0) + 1
        cluster_area_like[key] = cluster_area_like.get(key, 0.0) + max(span_x * span_y, max(span_x, span_y, 1.0))
        cluster_rows.setdefault(key, []).append(row)
    if not cluster_counts:
        return GeometryCleanupResult(rows, [], 0, _centroid(rows), _union_bounds(rows), "dominant_grid", {"reason": "no_clusters"})
    dominant = max(cluster_counts, key=lambda key: (cluster_counts[key], cluster_area_like.get(key, 0.0), key[0], key[1]))
    main_ids = {id(row) for row in cluster_rows[dominant]}
    main = [row for row in rows if id(row) in main_ids]
    stray = [row for row in rows if id(row) not in main_ids]
    return GeometryCleanupResult(
        main_geometry=main,
        stray_geometry=stray,
        stray_count=len(stray),
        cleaned_centroid=_centroid(main),
        cleaned_outline=_union_bounds(main),
        method="dominant_grid_cluster",
        diagnostics={
            "dominant_cluster_key": dominant,
            "dominant_cluster_count": cluster_counts[dominant],
            "cluster_count": len(cluster_counts),
            "cell_size": cell_size,
            "max_entity_span": max_entity_span,
        },
    )


def clean_geometry(
    geometry: list[dict[str, Any]],
    *,
    method: str = "percentile",
    percentile_low: float = 5.0,
    percentile_high: float = 95.0,
    cell_size: float = 500.0,
    max_entity_span: float = 100.0,
) -> GeometryCleanupResult:
    if method == "dominant_grid":
        return dominant_grid_cluster(geometry, cell_size=cell_size, max_entity_span=max_entity_span)
    return robust_main_cluster(geometry, percentile_low=percentile_low, percentile_high=percentile_high)
