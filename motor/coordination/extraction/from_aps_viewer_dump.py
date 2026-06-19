"""Convert cached APS Viewer 2D geometry dumps into Element25D objects.

Layer 1 APS extraction is intentionally sheet-frame native: 2D fragment bounds
from the Viewer are paper-space values (inches-like for the NASAS sheets), not
legacy project millimeters. The Element25D field name remains
``footprint_coords_mm`` for compatibility, but every APS fragment record is tagged
with ``coordinate_unit="sheet_paper_units"`` so downstream exports do not silently
mix it with mm proxy geometry.
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any

from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon
from shapely.ops import unary_union

from coordination.selection.level_inference import infer_level_from_view_name
from coordination.extraction.from_autodesk_properties import is_nonphysical_entity
from coordination.core.models_25d import Discipline, Element25D, ZInterval
from coordination.core.nasas_paths import translate_footprint
from coordination.core.registry import ProjectLevelRegistryDocument

logger = logging.getLogger("dupla.coordination.viewer_dump")

_BATCH_UNION_SIZE = 500
_HEAVY_PRIMITIVE_THRESHOLD = 2_000
_MAX_PRIMITIVES_PER_OBJECT = 8_000


def min_area_mm2_for_viewer_dump(*, discipline: Discipline, fallback_mm2: float) -> float:
    """Umbral bajo para geometría real (líneas acotadas con buffer), sin perder tuberías/vigas."""
    _by_discipline = {
        Discipline.ARCH: 2_000.0,
        Discipline.STRUC: 1_000.0,
        Discipline.MEP_ELEC: 500.0,
        Discipline.MEP_PLUMBING: 500.0,
    }
    cap = _by_discipline.get(discipline, 1_000.0)
    return min(fallback_mm2, cap)


def line_buffer_mm_for_discipline(discipline: Discipline) -> float:
    override = (os.getenv("APS_VIEWER_LINE_BUFFER_MM") or "").strip()
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    _by_discipline = {
        Discipline.ARCH: 20.0,
        Discipline.STRUC: 25.0,
        Discipline.MEP_ELEC: 20.0,
        Discipline.MEP_PLUMBING: 35.0,
    }
    return _by_discipline.get(discipline, 20.0)


def viewer_dump_has_geometry(viewer_dump: dict[str, Any]) -> bool:
    for view in viewer_dump.get("views") or []:
        for obj in view.get("objects") or []:
            if obj.get("primitives"):
                return True
    return False


SHEET_AXIS_COVERAGE_GOOD_MAX = 0.60
"""An element is localizable only if each axis covers less than 60% of the sheet."""

SHEET_AREA_COVERAGE_GOOD_MAX = 0.25
"""An element is good only if its bbox covers less than 25% of the sheet area."""

SHEET_AXIS_COVERAGE_UNLOCALIZABLE_MIN = 0.95
"""Near full-sheet bounds are title/sheet containers, not element geometry."""

SHEET_AREA_COVERAGE_UNLOCALIZABLE_MIN = 0.85
"""Near full-sheet area coverage is unlocalizable even if fragments exist."""

APS_FRAGMENT_COORDINATE_UNIT = "sheet_paper_units"
APS_FRAGMENT_GEOMETRY_SOURCE = "dwg_aps_fragment_world_bounds"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _bounds_from_any(value: Any) -> tuple[float, float, float, float] | None:
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


def _bbox_polygon(bounds: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    min_x, min_y, max_x, max_y = bounds
    return [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]


def _bounds_center(bounds: tuple[float, float, float, float]) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = bounds
    return ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)


def _union_bounds(bounds_items: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float] | None:
    if not bounds_items:
        return None
    return (
        min(item[0] for item in bounds_items),
        min(item[1] for item in bounds_items),
        max(item[2] for item in bounds_items),
        max(item[3] for item in bounds_items),
    )


def _sheet_bounds(view: dict[str, Any], objects: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    for key in ("sheet_bounds", "sheetBounds", "world_bounds", "worldBounds", "bounds", "bbox"):
        bounds = _bounds_from_any(view.get(key))
        if bounds is not None:
            return bounds
    object_bounds = [
        bounds
        for obj in objects
        for bounds in [_object_aggregate_bounds(obj)]
        if bounds is not None
    ]
    return _union_bounds(object_bounds)


def _fragment_bounds(obj: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    fragments = obj.get("fragments") or obj.get("fragment_bounds") or obj.get("fragmentBounds") or []
    out: list[tuple[float, float, float, float]] = []
    if isinstance(fragments, dict):
        fragments = list(fragments.values())
    if isinstance(fragments, list):
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


def _object_aggregate_bounds(obj: dict[str, Any]) -> tuple[float, float, float, float] | None:
    for key in ("world_bounds", "worldBounds", "bounds", "bbox"):
        bounds = _bounds_from_any(obj.get(key))
        if bounds is not None:
            return bounds
    return _union_bounds(_fragment_bounds(obj))


def _classify_fragment_geometry(
    bounds: tuple[float, float, float, float],
    sheet: tuple[float, float, float, float],
) -> str:
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


def _best_fragment_bounds(
    aggregate: tuple[float, float, float, float],
    fragments: list[tuple[float, float, float, float]],
    sheet: tuple[float, float, float, float],
) -> tuple[tuple[float, float, float, float], str, str]:
    """Prefer aggregate bounds; refine broad sheet-like objects with fragments."""
    aggregate_quality = _classify_fragment_geometry(aggregate, sheet)
    if aggregate_quality == "good" or not fragments:
        return aggregate, aggregate_quality, "aggregate"
    sheet_w = max(sheet[2] - sheet[0], 1e-9)
    sheet_h = max(sheet[3] - sheet[1], 1e-9)
    agg_w = max(aggregate[2] - aggregate[0], 0.0)
    agg_h = max(aggregate[3] - aggregate[1], 0.0)
    if agg_w / sheet_w <= SHEET_AXIS_COVERAGE_GOOD_MAX and agg_h / sheet_h <= SHEET_AXIS_COVERAGE_GOOD_MAX:
        return aggregate, aggregate_quality, "aggregate"

    candidates = [
        (bounds, _classify_fragment_geometry(bounds, sheet))
        for bounds in fragments
    ]
    good = [item for item in candidates if item[1] == "good"]
    if good:
        return min(good, key=lambda item: (item[0][2] - item[0][0]) * (item[0][3] - item[0][1]))[0], "good", "fragment_refined"
    coarse = [item for item in candidates if item[1] == "coarse"]
    if coarse:
        return min(coarse, key=lambda item: (item[0][2] - item[0][0]) * (item[0][3] - item[0][1]))[0], "coarse", "fragment_refined"
    return aggregate, aggregate_quality, "aggregate"


def elements_from_viewer_dump(
    viewer_dump: dict[str, Any],
    *,
    discipline: Discipline,
    level_doc: ProjectLevelRegistryDocument | None,
    default_level_id: str,
    translation_mm: tuple[float, float],
    path_label: str,
    coordination_issue_key: str,
    max_entities: int = 400,
    min_area_mm2: float = 40_000.0,
    z_thickness_mm: float = 250.0,
    line_buffer_mm: float | None = None,
    fast_footprint: bool = False,
) -> list[Element25D]:
    min_area_mm2 = min_area_mm2_for_viewer_dump(discipline=discipline, fallback_mm2=min_area_mm2)
    if line_buffer_mm is None:
        line_buffer_mm = line_buffer_mm_for_discipline(discipline)
    views = viewer_dump.get("views") or []
    out: list[Element25D] = []
    for view in views:
        view_name = str(view.get("name") or "Unnamed view")
        level_resolution = infer_level_from_view_name(
            view_name,
            doc=level_doc,
            default_level_id=default_level_id,
        )
        objects = view.get("objects") or []
        fragment_elements = _elements_from_fragment_objects(
            objects,
            view=view,
            discipline=discipline,
            level_id=level_resolution.level_id,
            level_assignment_source=level_resolution.source,
            path_label=path_label,
            view_name=view_name,
            coordination_issue_key=coordination_issue_key,
            z_thickness_mm=z_thickness_mm,
            remaining=max_entities - len(out),
        )
        out.extend(fragment_elements)
        if len(out) >= max_entities:
            return out
        if fragment_elements:
            continue

        for obj in objects:
            layer = str(obj.get("layer") or "")
            entity_name = str(obj.get("name") or layer)
            if is_nonphysical_entity(layer, entity_name):
                continue
            primitives = obj.get("primitives") or []
            if len(primitives) > _MAX_PRIMITIVES_PER_OBJECT:
                logger.info(
                    "Truncando primitivas dbId=%s: %d -> %d",
                    obj.get("dbId"),
                    len(primitives),
                    _MAX_PRIMITIVES_PER_OBJECT,
                )
                primitives = primitives[:_MAX_PRIMITIVES_PER_OBJECT]
            merged = _merge_object_footprint(
                primitives,
                line_buffer_mm=line_buffer_mm,
                fast_footprint=fast_footprint or len(primitives) > _HEAVY_PRIMITIVE_THRESHOLD,
            )
            if merged is None or merged.is_empty:
                continue
            for part_index, poly in enumerate(_iter_polygons(merged)):
                area = float(poly.area)
                if area < min_area_mm2:
                    continue
                coords = [(float(x), float(y)) for x, y in poly.exterior.coords[:-1]]
                coords = translate_footprint(coords, translation_mm[0], translation_mm[1])
                obj_id = str(obj.get("dbId") or obj.get("id") or len(out))
                suffix = "" if part_index == 0 else f"_part{part_index}"
                metadata = {
                    "coordination_issue_key": coordination_issue_key,
                    "geometry_source": "dwg_aps_viewer_2d",
                    "geometry_quality": "exact",
                    "level_assignment_source": level_resolution.source,
                    "sheet_or_view_name": view_name,
                    "source": "dwg_aps_viewer_2d",
                    "dwg_path": path_label,
                }
                if obj.get("layer"):
                    metadata["layer"] = str(obj["layer"])
                if obj.get("name"):
                    metadata["entity_name"] = str(obj["name"])
                if obj.get("handle"):
                    metadata["handle"] = str(obj["handle"])
                out.append(
                    Element25D(
                        id=f"aps_dwg_{path_label}_{obj_id}{suffix}",
                        source_ref=f"{path_label}|viewer|{view_name}|{obj_id}",
                        discipline=discipline,
                        category=f"viewer:{obj.get('name') or obj.get('layer') or 'object'}",
                        footprint_coords_mm=coords,
                        z_data=ZInterval(
                            level_id=level_resolution.level_id,
                            z_ref_raw_mm=0.0,
                            thickness_mm=z_thickness_mm,
                            reference_point="bottom",
                        ),
                        metadata=metadata,
                    )
                )
                if len(out) >= max_entities:
                    return out
    return out


def _elements_from_fragment_objects(
    objects: list[dict[str, Any]],
    *,
    view: dict[str, Any],
    discipline: Discipline,
    level_id: str,
    level_assignment_source: str,
    path_label: str,
    view_name: str,
    coordination_issue_key: str,
    z_thickness_mm: float,
    remaining: int,
) -> list[Element25D]:
    if remaining <= 0:
        return []
    sheet = _sheet_bounds(view, objects)
    if sheet is None:
        return []
    out: list[Element25D] = []
    for obj in objects:
        aggregate = _object_aggregate_bounds(obj)
        fragments = _fragment_bounds(obj)
        if aggregate is None and fragments:
            aggregate = _union_bounds(fragments)
        if aggregate is None:
            continue
        selected_bounds, quality, refinement = _best_fragment_bounds(aggregate, fragments, sheet)
        center = _bounds_center(selected_bounds)
        handle = str(obj.get("handle") or obj.get("externalId") or obj.get("external_id") or "").strip()
        db_id = str(obj.get("dbId") or obj.get("dbid") or obj.get("objectid") or obj.get("id") or len(out))
        layer = str(obj.get("layer") or obj.get("Layer") or "")
        metadata = {
            "coordination_issue_key": coordination_issue_key,
            "geometry_source": APS_FRAGMENT_GEOMETRY_SOURCE,
            "geometry_quality": quality,
            "coordinate_unit": APS_FRAGMENT_COORDINATE_UNIT,
            "source": APS_FRAGMENT_GEOMETRY_SOURCE,
            "dwg_path": path_label,
            "sheet_or_view_name": view_name,
            "level_assignment_source": level_assignment_source,
            "dbId": db_id,
            "fragment_count": len(fragments),
            "world_bounds": list(selected_bounds),
            "aggregate_world_bounds": list(aggregate),
            "fragment_world_bounds": [list(item) for item in fragments],
            "sheet_bounds": list(sheet),
            "center": [center[0], center[1]],
            "refinement": refinement,
        }
        if handle:
            metadata["handle"] = handle
        if layer:
            metadata["layer"] = layer
        out.append(
            Element25D(
                id=f"aps_dwg_{path_label}_{handle or db_id}",
                source_ref=f"{path_label}|aps_fragment:{handle or db_id}",
                discipline=discipline,
                category=f"aps_fragment:{layer or obj.get('name') or 'object'}",
                footprint_coords_mm=_bbox_polygon(selected_bounds),
                z_data=ZInterval(
                    level_id=level_id,
                    z_ref_raw_mm=0.0,
                    thickness_mm=z_thickness_mm,
                    reference_point="bottom",
                ),
                metadata=metadata,
            )
        )
        if len(out) >= remaining:
            break
    return out


def _merge_object_footprint(
    primitives: list[dict[str, Any]],
    *,
    line_buffer_mm: float,
    fast_footprint: bool,
) -> Polygon | MultiPolygon | GeometryCollection | None:
    if not primitives:
        return None
    if fast_footprint:
        polygons = _primitive_polygons(primitives, line_buffer_mm=line_buffer_mm, max_lines=400)
        if not polygons:
            return None
        merged = unary_union(polygons)
        if merged.is_empty:
            return None
        hull = merged.convex_hull
        return hull if not hull.is_empty else merged

    polygons = _primitive_polygons(primitives, line_buffer_mm=line_buffer_mm)
    if not polygons:
        return None
    if len(polygons) <= _BATCH_UNION_SIZE:
        return unary_union(polygons)

    parts: list[Polygon | MultiPolygon] = []
    for start in range(0, len(polygons), _BATCH_UNION_SIZE):
        batch = polygons[start : start + _BATCH_UNION_SIZE]
        part = unary_union(batch)
        if not part.is_empty:
            parts.append(part)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return unary_union(parts)


def _primitive_polygons(
    primitives: list[dict[str, Any]],
    *,
    line_buffer_mm: float,
    max_lines: int | None = None,
) -> list[Polygon]:
    polygons: list[Polygon] = []
    line_count = 0
    for primitive in primitives:
        kind = str(primitive.get("type") or "").lower()
        if kind == "line":
            if max_lines is not None and line_count >= max_lines:
                continue
            line_count += 1
            line = LineString(
                [
                    (float(primitive["x1"]), float(primitive["y1"])),
                    (float(primitive["x2"]), float(primitive["y2"])),
                ]
            )
            polygons.extend(_iter_polygons(line.buffer(line_buffer_mm, cap_style=2)))
        elif kind == "rect":
            x = float(primitive["x"])
            y = float(primitive["y"])
            w = float(primitive["width"])
            h = float(primitive["height"])
            polygons.append(Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
        elif kind == "quad":
            pts = [(float(x), float(y)) for x, y in primitive.get("points") or []]
            if len(pts) >= 3:
                polygons.append(Polygon(pts))
        elif kind == "arc":
            cx = float(primitive["cx"])
            cy = float(primitive["cy"])
            radius = float(primitive["radius"])
            start = float(primitive.get("start", 0.0))
            end = float(primitive.get("end", 2.0 * math.pi))
            pts = []
            steps = max(12, int(abs(end - start) / (math.pi / 18)))
            for step in range(steps + 1):
                t = start + (end - start) * (step / steps)
                pts.append((cx + radius * math.cos(t), cy + radius * math.sin(t)))
            polygons.extend(_iter_polygons(LineString(pts).buffer(line_buffer_mm, cap_style=2)))
    return [poly for poly in polygons if not poly.is_empty and poly.area > 1.0]


def _iter_polygons(geometry: Any) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return [poly for poly in geometry.geoms if poly.area > 1.0]
    if isinstance(geometry, GeometryCollection):
        out: list[Polygon] = []
        for geom in geometry.geoms:
            out.extend(_iter_polygons(geom))
        return out
    return []
