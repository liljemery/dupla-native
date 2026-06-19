"""
(P2.7) GeometryMerger — mata el doble conteo de muros.

Un muro suele dibujarse como DOS lineas paralelas (sus dos caras) separadas por el
espesor del muro. Si cada linea se mide por separado, el largo del muro se cuenta
dos veces. Tambien pasa con segmentos colineales solapados (la misma linea dibujada
encima). Este modulo agrupa segmentos que son:

    - paralelos (diferencia angular < angle_tol),
    - cercanos (distancia perpendicular <= max_wall_thickness_m), y
    - solapados (proyeccion comun >= min_overlap_m),

y los colapsa a UN largo: la union de intervalos proyectada sobre el eje del grupo.
Para dos caras de 5 m alineadas, el resultado es ~5 m (no 10 m).

Es geometria pura (sin dependencias de APS), por eso es 100% testeable. Opera
sobre los ``geometry_hints`` que traen coordenadas (``start``/``end`` para lineas,
``vertices`` para polilineas) — las que produce DuplaExtractor (DA).
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger("dupla.geometry_merger")

Point = tuple[float, float]
Segment = tuple[Point, Point]


def _num(v: Any) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def _point(obj: Any) -> Point | None:
    if isinstance(obj, dict):
        x, y = _num(obj.get("X", obj.get("x"))), _num(obj.get("Y", obj.get("y")))
    elif isinstance(obj, (list, tuple)) and len(obj) >= 2:
        x, y = _num(obj[0]), _num(obj[1])
    else:
        return None
    if x is None or y is None:
        return None
    return (x, y)


def hint_segments(hint: dict[str, Any]) -> list[Segment]:
    """Extract straight sub-segments (with coords) from a geometry hint."""
    start = _point(hint.get("start"))
    end = _point(hint.get("end"))
    if start and end:
        return [(start, end)]
    verts_raw = hint.get("vertices") or []
    pts = [p for p in (_point(v) for v in verts_raw) if p is not None]
    segs: list[Segment] = []
    for i in range(len(pts) - 1):
        segs.append((pts[i], pts[i + 1]))
    return segs


def seg_length(seg: Segment) -> float:
    (x1, y1), (x2, y2) = seg
    return math.hypot(x2 - x1, y2 - y1)


def _unit(seg: Segment) -> Point | None:
    (x1, y1), (x2, y2) = seg
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return None
    return (dx / L, dy / L)


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _are_parallel(u1: Point, u2: Point, angle_tol_deg: float) -> bool:
    # |sin(theta)| = |cross(u1,u2)| for unit vectors
    return abs(_cross(u1, u2)) <= math.sin(math.radians(angle_tol_deg))


def _perp_distance(seg_ref: Segment, u_ref: Point, other_point: Point) -> float:
    p = seg_ref[0]
    v = (other_point[0] - p[0], other_point[1] - p[1])
    return abs(_cross(u_ref, v))  # perpendicular component magnitude


def _project(point: Point, origin: Point, u: Point) -> float:
    v = (point[0] - origin[0], point[1] - origin[1])
    return v[0] * u[0] + v[1] * u[1]


def _overlap_len(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> float:
    return max(0.0, min(a_hi, b_hi) - max(a_lo, b_lo))


def _union_length(intervals: list[tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    ordered = sorted((min(a, b), max(a, b)) for a, b in intervals)
    total = 0.0
    cur_lo, cur_hi = ordered[0]
    for lo, hi in ordered[1:]:
        if lo > cur_hi:
            total += cur_hi - cur_lo
            cur_lo, cur_hi = lo, hi
        else:
            cur_hi = max(cur_hi, hi)
    total += cur_hi - cur_lo
    return total


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.parent[ri] = rj


def merge_segments(
    segments: list[Segment],
    *,
    max_wall_thickness_m: float = 0.4,
    angle_tol_deg: float = 6.0,
    min_overlap_m: float = 0.3,
) -> dict[str, Any]:
    """Collapse double-line / overlapping parallel segments.

    Returns {"merged_length_m", "raw_length_m", "groups", "n_input", "n_groups"}.
    """
    segs = [s for s in segments if seg_length(s) > 1e-6]
    n = len(segs)
    raw_length = sum(seg_length(s) for s in segs)
    if n == 0:
        return {"merged_length_m": 0.0, "raw_length_m": 0.0, "groups": [], "n_input": 0, "n_groups": 0}

    units = [_unit(s) for s in segs]
    uf = _UnionFind(n)

    for i in range(n):
        ui = units[i]
        if ui is None:
            continue
        li = seg_length(segs[i])
        oi, hi = segs[i][0], segs[i][1]
        ai_lo = 0.0
        ai_hi = li
        for j in range(i + 1, n):
            uj = units[j]
            if uj is None:
                continue
            if not _are_parallel(ui, uj, angle_tol_deg):
                continue
            # perpendicular gap between the two parallel lines
            dist = _perp_distance(segs[i], ui, segs[j][0])
            if dist > max_wall_thickness_m:
                continue
            # overlap along i's axis
            t1 = _project(segs[j][0], oi, ui)
            t2 = _project(segs[j][1], oi, ui)
            lo, high = min(t1, t2), max(t1, t2)
            if _overlap_len(ai_lo, ai_hi, lo, high) >= min_overlap_m:
                uf.union(i, j)

    # Build groups
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    merged_length = 0.0
    group_summaries: list[dict[str, Any]] = []
    for members in groups.values():
        if len(members) == 1:
            L = seg_length(segs[members[0]])
            merged_length += L
            continue
        # project all members onto the longest member's axis, union intervals
        longest = max(members, key=lambda k: seg_length(segs[k]))
        origin = segs[longest][0]
        axis = units[longest] or (1.0, 0.0)
        intervals: list[tuple[float, float]] = []
        for k in members:
            t1 = _project(segs[k][0], origin, axis)
            t2 = _project(segs[k][1], origin, axis)
            intervals.append((t1, t2))
        gl = _union_length(intervals)
        merged_length += gl
        group_summaries.append({
            "members": len(members),
            "raw_length_m": round(sum(seg_length(segs[k]) for k in members), 3),
            "merged_length_m": round(gl, 3),
        })

    return {
        "merged_length_m": round(merged_length, 3),
        "raw_length_m": round(raw_length, 3),
        "groups": group_summaries,
        "n_input": n,
        "n_groups": len(groups),
    }


def merge_geometry_hints(
    hints: list[dict[str, Any]],
    *,
    max_wall_thickness_m: float = 0.4,
    angle_tol_deg: float = 6.0,
    min_overlap_m: float = 0.3,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collapse double-line wall hints; return (new_hints, stats).

    Line hints that share a collapse group are reduced to ONE representative hint
    whose ``length`` is the group's merged (de-duplicated) length; the partner
    hints are dropped. Non-line hints (blocks/circles/text) pass through.
    Hints without coordinates pass through unchanged (cannot be de-duplicated).
    """
    line_idx: list[int] = []
    seg_of: dict[int, Segment] = {}
    passthrough: list[dict[str, Any]] = []

    for idx, h in enumerate(hints):
        et = str(h.get("entity_type", "")).lower()
        segs = hint_segments(h) if et in {"line", "polyline", "lwpolyline", ""} else []
        if len(segs) == 1:
            line_idx.append(idx)
            seg_of[idx] = segs[0]
        else:
            passthrough.append(h)

    if len(line_idx) < 2:
        return list(hints), {"applied": False, "reason": "insufficient coord lines"}

    segments = [seg_of[i] for i in line_idx]
    units = [_unit(s) for s in segments]
    n = len(segments)
    uf = _UnionFind(n)
    for i in range(n):
        ui = units[i]
        if ui is None:
            continue
        oi = segments[i][0]
        li = seg_length(segments[i])
        for j in range(i + 1, n):
            uj = units[j]
            if uj is None or not _are_parallel(ui, uj, angle_tol_deg):
                continue
            if _perp_distance(segments[i], ui, segments[j][0]) > max_wall_thickness_m:
                continue
            t1 = _project(segments[j][0], oi, ui)
            t2 = _project(segments[j][1], oi, ui)
            if _overlap_len(0.0, li, min(t1, t2), max(t1, t2)) >= min_overlap_m:
                uf.union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    new_hints: list[dict[str, Any]] = list(passthrough)
    collapsed = 0
    removed_length = 0.0
    for members in groups.values():
        rep_local = max(members, key=lambda k: seg_length(segments[k]))
        rep_hint = dict(hints[line_idx[rep_local]])
        if len(members) > 1:
            origin = segments[rep_local][0]
            axis = units[rep_local] or (1.0, 0.0)
            intervals = [
                (_project(segments[k][0], origin, axis), _project(segments[k][1], origin, axis))
                for k in members
            ]
            merged_len = _union_length(intervals)
            raw = sum(seg_length(segments[k]) for k in members)
            removed_length += max(0.0, raw - merged_len)
            collapsed += len(members) - 1
            rep_hint["length"] = round(merged_len, 4)
            rep_hint["merged_from"] = len(members)
        new_hints.append(rep_hint)

    stats = {
        "applied": True,
        "input_lines": n,
        "groups": len(groups),
        "collapsed_segments": collapsed,
        "removed_length_m": round(removed_length, 3),
    }
    return new_hints, stats
