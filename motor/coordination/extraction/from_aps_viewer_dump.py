"""Convert cached APS Viewer 2D primitive dumps into Element25D objects."""

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
        for obj in view.get("objects") or []:
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
