"""2.5D clash detection: plan overlap plus vertical overlap."""

from __future__ import annotations

import math
from itertools import combinations
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from shapely.geometry import Polygon
from shapely.strtree import STRtree
from shapely.validation import explain_validity

from coordination.core.models_25d import Discipline, Element25D
from coordination.core.registry import ProjectLevelRegistry


class ClashConflict(BaseModel):
    """Auditable clash between two 2.5D elements."""

    model_config = ConfigDict(extra="forbid")

    element_id_a: str
    element_id_b: str
    discipline_a: Discipline
    discipline_b: Discipline
    clash_type: Literal["HARD", "SOFT"] = "HARD"
    overlap_depth_z_mm: float = Field(..., ge=0.0)
    z_overlap_range_project_mm: tuple[float, float]
    plan_intersection_area_mm2: float = Field(..., ge=0.0)
    plan_intersection_centroid_mm: tuple[float, float]
    plan_intersection_bounds_mm: tuple[float, float, float, float]
    level_ids: tuple[str, str]
    confidence: Literal["low", "medium", "high"] = "medium"
    geometry_sources: tuple[str, str] = ("unknown", "unknown")
    level_assignment_sources: tuple[str, str] = ("unknown", "unknown")
    raw_layers: tuple[str, str] = ("", "")
    source_refs: tuple[str, str]
    notes: list[str] = Field(default_factory=list)

    def to_human_readable(self) -> str:
        z0, z1 = self.z_overlap_range_project_mm
        return (
            f"{self.clash_type}: {self.element_id_a} ({self.discipline_a.value}) vs "
            f"{self.element_id_b} ({self.discipline_b.value}) - "
            f"profundidad Z {self.overlap_depth_z_mm:.1f} mm, tramo comun [{z0:.1f}, {z1:.1f}] mm, "
            f"area planta {self.plan_intersection_area_mm2:.0f} mm2, confianza {self.confidence}"
        )


class ClashIncident(BaseModel):
    """Grouped clash result suitable for review as a single incident."""

    model_config = ConfigDict(extra="forbid")

    incident_id: str
    file_pair: tuple[str, str]
    level_id: str
    cell_key: tuple[int, int]
    member_count: int = Field(..., ge=1)
    representative_conflict: ClashConflict
    plan_centroid_mm: tuple[float, float]
    plan_bounds_mm: tuple[float, float, float, float]
    confidence: Literal["low", "medium", "high"] = "medium"
    geometry_sources: tuple[str, str] = ("unknown", "unknown")


def _footprint_polygon(el: Element25D, *, planar_tolerance_mm: float) -> Polygon:
    coords = list(el.footprint_coords_mm)
    if len(coords) < 3:
        raise ValueError(f"Elemento {el.id}: se necesitan al menos 3 vertices en footprint_coords_mm")
    if coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    poly = Polygon(coords)
    if planar_tolerance_mm > 0:
        poly = poly.buffer(planar_tolerance_mm)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if not poly.is_valid:
        raise ValueError(f"Poligono invalido {el.id}: {explain_validity(poly)}")
    return poly


def _z_overlap(
    a0: float, a1: float, b0: float, b1: float
) -> tuple[float, tuple[float, float] | None]:
    left = max(a0, b0)
    right = min(a1, b1)
    depth = right - left
    if depth <= 0:
        return 0.0, None
    return depth, (left, right)


def clash_pairs(
    elements: list[Element25D],
    registry: ProjectLevelRegistry,
    *,
    planar_tolerance_mm: float = 0.0,
    min_plan_area_mm2: float = 1.0,
    strict_levels: bool = False,
    require_same_metadata_key: str | None = None,
) -> list[ClashConflict]:
    level_map = registry.offsets_map()
    polys: dict[str, Polygon] = {
        el.id: _footprint_polygon(el, planar_tolerance_mm=planar_tolerance_mm) for el in elements
    }
    intervals: dict[str, tuple[float, float]] = {
        el.id: el.get_absolute_interval_mm(level_map, strict_levels=strict_levels) for el in elements
    }

    conflicts: list[ClashConflict] = []
    geom_list = [polys[el.id] for el in elements]
    tree = STRtree(geom_list) if len(elements) > 80 else None

    def maybe_add_conflict(ea: Element25D, eb: Element25D) -> None:
        if require_same_metadata_key:
            ka = ea.metadata.get(require_same_metadata_key)
            kb = eb.metadata.get(require_same_metadata_key)
            if ka is None or kb is None or ka != kb:
                return
        if ea.discipline == eb.discipline:
            return
        poly_a = polys[ea.id]
        poly_b = polys[eb.id]
        if not poly_a.intersects(poly_b):
            return
        intersection = poly_a.intersection(poly_b)
        area = float(intersection.area)
        if area < min_plan_area_mm2 or math.isnan(area):
            return
        centroid = intersection.centroid
        bounds = intersection.bounds

        za = intervals[ea.id]
        zb = intervals[eb.id]
        depth, z_range = _z_overlap(za[0], za[1], zb[0], zb[1])
        if z_range is None or depth <= 0:
            return

        notes: list[str] = []
        if ea.z_data.invert_level_hint:
            notes.append(f"{ea.id}: cota referencia tipo invert")
        if eb.z_data.invert_level_hint:
            notes.append(f"{eb.id}: cota referencia tipo invert")

        conflicts.append(
            ClashConflict(
                element_id_a=ea.id,
                element_id_b=eb.id,
                discipline_a=ea.discipline,
                discipline_b=eb.discipline,
                clash_type="HARD",
                overlap_depth_z_mm=depth,
                z_overlap_range_project_mm=z_range,
                plan_intersection_area_mm2=area,
                plan_intersection_centroid_mm=(float(centroid.x), float(centroid.y)),
                plan_intersection_bounds_mm=(
                    float(bounds[0]),
                    float(bounds[1]),
                    float(bounds[2]),
                    float(bounds[3]),
                ),
                level_ids=(ea.z_data.level_id, eb.z_data.level_id),
                confidence=_pair_confidence(ea, eb),
                geometry_sources=(
                    str(ea.metadata.get("geometry_source") or "unknown"),
                    str(eb.metadata.get("geometry_source") or "unknown"),
                ),
                level_assignment_sources=(
                    str(ea.metadata.get("level_assignment_source") or "unknown"),
                    str(eb.metadata.get("level_assignment_source") or "unknown"),
                ),
                raw_layers=(
                    str(ea.metadata.get("layer") or ""),
                    str(eb.metadata.get("layer") or ""),
                ),
                source_refs=(ea.source_ref, eb.source_ref),
                notes=notes,
            )
        )

    if tree is not None:
        for index, ea in enumerate(elements):
            for other_index in tree.query(geom_list[index], predicate="intersects"):
                other_index = int(other_index)
                if other_index <= index:
                    continue
                maybe_add_conflict(ea, elements[other_index])
    else:
        for ea, eb in combinations(elements, 2):
            maybe_add_conflict(ea, eb)

    conflicts.sort(key=lambda item: (-item.overlap_depth_z_mm, -item.plan_intersection_area_mm2))
    return conflicts


def conflicts_to_conflict_notes(conflicts: list[ClashConflict]) -> list[str]:
    return [conflict.to_human_readable() for conflict in conflicts]


def group_conflicts_into_incidents(
    conflicts: list[ClashConflict],
    *,
    cell_size_mm: float = 2000.0,
) -> list[ClashIncident]:
    groups: dict[tuple[tuple[str, str], str, tuple[int, int]], list[ClashConflict]] = {}
    for conflict in conflicts:
        file_pair = tuple(sorted(_source_file(ref) for ref in conflict.source_refs))
        level_id = conflict.level_ids[0] if conflict.level_ids[0] == conflict.level_ids[1] else "mixed"
        cell_key = _incident_cell_key(conflict.plan_intersection_centroid_mm, cell_size_mm=cell_size_mm)
        groups.setdefault((file_pair, level_id, cell_key), []).append(conflict)

    incidents: list[ClashIncident] = []
    for index, ((file_pair, level_id, cell_key), members) in enumerate(sorted(groups.items())):
        representative = max(
            members,
            key=lambda item: (item.plan_intersection_area_mm2, item.overlap_depth_z_mm),
        )
        incidents.append(
            ClashIncident(
                incident_id=f"incident_{index:04d}",
                file_pair=file_pair,
                level_id=level_id,
                cell_key=cell_key,
                member_count=len(members),
                representative_conflict=representative,
                plan_centroid_mm=representative.plan_intersection_centroid_mm,
                plan_bounds_mm=representative.plan_intersection_bounds_mm,
                confidence=representative.confidence,
                geometry_sources=representative.geometry_sources,
            )
        )
    incidents.sort(
        key=lambda item: (
            -item.member_count,
            -item.representative_conflict.plan_intersection_area_mm2,
            item.incident_id,
        )
    )
    return incidents


def _pair_confidence(ea: Element25D, eb: Element25D) -> Literal["low", "medium", "high"]:
    score = min(_element_confidence_score(ea), _element_confidence_score(eb))
    if score <= 1:
        return "low"
    if score == 2:
        return "medium"
    return "high"


def _element_confidence_score(element: Element25D) -> int:
    quality = str(element.metadata.get("geometry_quality") or "medium").lower()
    score = {
        "unlocalizable": 0,
        "low": 0,
        "proxy": 1,
        "coarse": 2,
        "medium": 2,
        "good": 3,
        "high": 3,
        "exact": 4,
    }.get(quality, 2)
    level_source = str(element.metadata.get("level_assignment_source") or "")
    if level_source == "page_index_fallback":
        return min(score, 1)
    if level_source == "default_level":
        return min(score, 2)
    return score


def _source_file(source_ref: str) -> str:
    return source_ref.split("|", 1)[0]


def _incident_cell_key(
    centroid_mm: tuple[float, float],
    *,
    cell_size_mm: float,
) -> tuple[int, int]:
    return (
        int(math.floor(centroid_mm[0] / cell_size_mm)),
        int(math.floor(centroid_mm[1] / cell_size_mm)),
    )
