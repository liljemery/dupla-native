"""Build DXF-to-APS correspondence pairs from shared entity handles."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from coordination.extraction.dxf_geometry import (
    BoundsXY,
    DxfGeometryExtraction,
    DxfGeometryRecord,
    is_annotation_layer,
    normalize_handle,
)

SHEET_AXIS_COVERAGE_GOOD_MAX = 0.60
SHEET_AREA_COVERAGE_GOOD_MAX = 0.25
SHEET_AXIS_COVERAGE_UNLOCALIZABLE_MIN = 0.95
SHEET_AREA_COVERAGE_UNLOCALIZABLE_MIN = 0.85


@dataclass(frozen=True)
class ApsGeometryRecord:
    handle: str
    db_id: str
    layer: str
    view_name: str
    sheet_bounds: BoundsXY
    sheet_world_bounds: BoundsXY
    sheet_center: tuple[float, float]
    geometry_quality: str
    refinement: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "dbId": self.db_id,
            "layer": self.layer,
            "view_name": self.view_name,
            "sheet_bounds": [float(v) for v in self.sheet_bounds],
            "sheet_world_bounds": [float(v) for v in self.sheet_world_bounds],
            "sheet_center": [float(v) for v in self.sheet_center],
            "geometry_quality": self.geometry_quality,
            "refinement": self.refinement,
        }


@dataclass(frozen=True)
class DxfApsMatchPair:
    handle: str
    dxf: DxfGeometryRecord
    aps: ApsGeometryRecord

    def to_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "model_center": [float(v) for v in self.dxf.model_center],
            "model_bounds": [float(v) for v in self.dxf.model_bounds],
            "sheet_center": [float(v) for v in self.aps.sheet_center],
            "sheet_world_bounds": [float(v) for v in self.aps.sheet_world_bounds],
            "dbId": self.aps.db_id,
            "view_name": self.aps.view_name,
            "dxf_layer": self.dxf.layer,
            "aps_layer": self.aps.layer,
            "dxf_dxftype": self.dxf.dxftype,
            "dxf_geometry_quality": self.dxf.geometry_quality,
            "aps_geometry_quality": self.aps.geometry_quality,
            "aps_refinement": self.aps.refinement,
        }


@dataclass
class DxfApsMatchReport:
    pairs: list[DxfApsMatchPair] = field(default_factory=list)
    aps_records: list[ApsGeometryRecord] = field(default_factory=list)
    rejected: dict[str, int] = field(default_factory=dict)
    pairs_by_view: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_count": len(self.pairs),
            "aps_record_count": len(self.aps_records),
            "pairs_by_view": dict(self.pairs_by_view),
            "rejected": dict(self.rejected),
            "pairs": [pair.to_dict() for pair in self.pairs],
        }


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _bounds_from_any(value: Any) -> BoundsXY | None:
    if isinstance(value, dict):
        if all(key in value for key in ("min_x", "min_y", "max_x", "max_y")):
            vals = [_number(value[key]) for key in ("min_x", "min_y", "max_x", "max_y")]
        elif "min" in value and "max" in value:
            min_v = value.get("min") or {}
            max_v = value.get("max") or {}
            if isinstance(min_v, dict) and isinstance(max_v, dict):
                vals = [_number(min_v.get("x")), _number(min_v.get("y")), _number(max_v.get("x")), _number(max_v.get("y"))]
            elif isinstance(min_v, (list, tuple)) and isinstance(max_v, (list, tuple)) and len(min_v) >= 2 and len(max_v) >= 2:
                vals = [_number(min_v[0]), _number(min_v[1]), _number(max_v[0]), _number(max_v[1])]
            else:
                return None
        else:
            return None
    elif isinstance(value, (list, tuple)) and len(value) >= 4:
        vals = [_number(value[0]), _number(value[1]), _number(value[2]), _number(value[3])]
    else:
        return None
    if any(v is None for v in vals):
        return None
    min_x, min_y, max_x, max_y = [float(v) for v in vals if v is not None]
    if max_x < min_x:
        min_x, max_x = max_x, min_x
    if max_y < min_y:
        min_y, max_y = max_y, min_y
    if max_x <= min_x or max_y <= min_y:
        return None
    return (min_x, min_y, max_x, max_y)


def _bounds_center(bounds: BoundsXY) -> tuple[float, float]:
    return ((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0)


def _union_bounds(bounds_items: Iterable[BoundsXY]) -> BoundsXY | None:
    rows = list(bounds_items)
    if not rows:
        return None
    return (
        min(row[0] for row in rows),
        min(row[1] for row in rows),
        max(row[2] for row in rows),
        max(row[3] for row in rows),
    )


def _fragment_bounds(obj: dict[str, Any]) -> list[BoundsXY]:
    fragments = obj.get("fragments") or obj.get("fragment_bounds") or obj.get("fragmentBounds") or []
    out: list[BoundsXY] = []
    if isinstance(fragments, dict):
        fragments = list(fragments.values())
    if not isinstance(fragments, list):
        return out
    for fragment in fragments:
        if isinstance(fragment, dict):
            bounds = _bounds_from_any(
                fragment.get("world_bounds")
                or fragment.get("worldBounds")
                or fragment.get("bounds")
                or fragment.get("bbox")
            )
        else:
            bounds = _bounds_from_any(fragment)
        if bounds is not None:
            out.append(bounds)
    return out


def _object_aggregate_bounds(obj: dict[str, Any]) -> BoundsXY | None:
    for key in ("world_bounds", "worldBounds", "aggregate_world_bounds", "bounds", "bbox"):
        bounds = _bounds_from_any(obj.get(key))
        if bounds is not None:
            return bounds
    return _union_bounds(_fragment_bounds(obj))


def _sheet_bounds(view: dict[str, Any], objects: list[dict[str, Any]]) -> BoundsXY | None:
    for key in ("sheet_bounds", "sheetBounds", "world_bounds", "worldBounds", "bounds", "bbox"):
        bounds = _bounds_from_any(view.get(key))
        if bounds is not None:
            return bounds
    return _union_bounds(
        bounds for obj in objects for bounds in [_object_aggregate_bounds(obj)] if bounds is not None
    )


def classify_sheet_geometry(bounds: BoundsXY, sheet: BoundsXY) -> str:
    sheet_w = max(sheet[2] - sheet[0], 1e-9)
    sheet_h = max(sheet[3] - sheet[1], 1e-9)
    sheet_area = sheet_w * sheet_h
    w = max(bounds[2] - bounds[0], 0.0)
    h = max(bounds[3] - bounds[1], 0.0)
    x_ratio = w / sheet_w
    y_ratio = h / sheet_h
    area_ratio = (w * h) / sheet_area
    if (
        x_ratio >= SHEET_AXIS_COVERAGE_UNLOCALIZABLE_MIN
        or y_ratio >= SHEET_AXIS_COVERAGE_UNLOCALIZABLE_MIN
        or area_ratio >= SHEET_AREA_COVERAGE_UNLOCALIZABLE_MIN
    ):
        return "unlocalizable"
    if (
        x_ratio < SHEET_AXIS_COVERAGE_GOOD_MAX
        and y_ratio < SHEET_AXIS_COVERAGE_GOOD_MAX
        and area_ratio < SHEET_AREA_COVERAGE_GOOD_MAX
    ):
        return "good"
    return "coarse"


def _best_fragment_bounds(aggregate: BoundsXY, fragments: list[BoundsXY], sheet: BoundsXY) -> tuple[BoundsXY, str, str]:
    aggregate_quality = classify_sheet_geometry(aggregate, sheet)
    if aggregate_quality == "good" or not fragments:
        return aggregate, aggregate_quality, "aggregate"
    sheet_w = max(sheet[2] - sheet[0], 1e-9)
    sheet_h = max(sheet[3] - sheet[1], 1e-9)
    agg_w = max(aggregate[2] - aggregate[0], 0.0)
    agg_h = max(aggregate[3] - aggregate[1], 0.0)
    if agg_w / sheet_w <= SHEET_AXIS_COVERAGE_GOOD_MAX and agg_h / sheet_h <= SHEET_AXIS_COVERAGE_GOOD_MAX:
        return aggregate, aggregate_quality, "aggregate"

    candidates = [(bounds, classify_sheet_geometry(bounds, sheet)) for bounds in fragments]
    good = [item for item in candidates if item[1] == "good"]
    if good:
        return min(good, key=lambda item: (item[0][2] - item[0][0]) * (item[0][3] - item[0][1]))[0], "good", "fragment_refined"
    coarse = [item for item in candidates if item[1] == "coarse"]
    if coarse:
        return min(coarse, key=lambda item: (item[0][2] - item[0][0]) * (item[0][3] - item[0][1]))[0], "coarse", "fragment_refined"
    return aggregate, aggregate_quality, "aggregate"


def aps_records_from_viewer_dump(viewer_dump: dict[str, Any]) -> list[ApsGeometryRecord]:
    records: list[ApsGeometryRecord] = []
    for view in viewer_dump.get("views") or []:
        if not isinstance(view, dict):
            continue
        view_name = str(view.get("name") or "Unnamed view")
        objects = view.get("objects") or []
        if not isinstance(objects, list):
            continue
        sheet = _sheet_bounds(view, objects)
        if sheet is None:
            continue
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            handle = normalize_handle(obj.get("handle") or obj.get("externalId") or obj.get("external_id") or "")
            if not handle:
                continue
            aggregate = _object_aggregate_bounds(obj)
            fragments = _fragment_bounds(obj)
            if aggregate is None and fragments:
                aggregate = _union_bounds(fragments)
            if aggregate is None:
                continue
            selected, quality, refinement = _best_fragment_bounds(aggregate, fragments, sheet)
            records.append(
                ApsGeometryRecord(
                    handle=handle,
                    db_id=str(obj.get("dbId") or obj.get("dbid") or obj.get("objectid") or obj.get("id") or ""),
                    layer=str(obj.get("layer") or obj.get("Layer") or ""),
                    view_name=view_name,
                    sheet_bounds=sheet,
                    sheet_world_bounds=selected,
                    sheet_center=_bounds_center(selected),
                    geometry_quality=quality,
                    refinement=refinement,
                )
            )
    return records


def _pick_best_aps(records: list[ApsGeometryRecord]) -> ApsGeometryRecord:
    quality_rank = {"good": 0, "coarse": 1, "unlocalizable": 2}

    def score(record: ApsGeometryRecord) -> tuple[int, float]:
        area = (record.sheet_world_bounds[2] - record.sheet_world_bounds[0]) * (
            record.sheet_world_bounds[3] - record.sheet_world_bounds[1]
        )
        return (quality_rank.get(record.geometry_quality, 3), area)

    return min(records, key=score)


def build_dxf_aps_match_report(
    dxf: DxfGeometryExtraction,
    viewer_dump: dict[str, Any],
    *,
    require_physical: bool = True,
    allowed_aps_qualities: tuple[str, ...] = ("good",),
    allowed_dxf_qualities: tuple[str, ...] = ("good", "coarse"),
    exclude_annotation_layers: bool = True,
) -> DxfApsMatchReport:
    """Match DXF records to APS Viewer objects using normalized handles."""
    rejected: Counter[str] = Counter()
    aps_records = aps_records_from_viewer_dump(viewer_dump)
    aps_by_handle: dict[str, list[ApsGeometryRecord]] = defaultdict(list)
    for record in aps_records:
        aps_by_handle[record.handle].append(record)

    pairs: list[DxfApsMatchPair] = []
    for record in dxf.records:
        handle = normalize_handle(record.handle)
        if not handle:
            rejected["dxf_missing_handle"] += 1
            continue
        if require_physical and not record.is_physical:
            rejected["dxf_non_physical"] += 1
            continue
        if record.geometry_quality not in allowed_dxf_qualities:
            rejected[f"dxf_quality_{record.geometry_quality}"] += 1
            continue
        if exclude_annotation_layers and is_annotation_layer(record.layer):
            rejected["dxf_annotation_layer"] += 1
            continue

        candidates = aps_by_handle.get(handle) or []
        if not candidates:
            rejected["aps_missing_handle"] += 1
            continue
        aps = _pick_best_aps(candidates)
        if aps.geometry_quality not in allowed_aps_qualities:
            rejected[f"aps_quality_{aps.geometry_quality}"] += 1
            continue
        if exclude_annotation_layers and is_annotation_layer(aps.layer):
            rejected["aps_annotation_layer"] += 1
            continue
        pairs.append(DxfApsMatchPair(handle=handle, dxf=record, aps=aps))

    pairs_by_view = Counter(pair.aps.view_name for pair in pairs)
    return DxfApsMatchReport(
        pairs=pairs,
        aps_records=aps_records,
        rejected=dict(sorted(rejected.items())),
        pairs_by_view=dict(sorted(pairs_by_view.items())),
    )

