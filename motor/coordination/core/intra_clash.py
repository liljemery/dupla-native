"""Intra-discipline clash detection on plan (2D bounding-box proxy).

The cross-discipline detector in ``clash.py`` is 2.5D (needs per-element Z
intervals + a level registry) and deliberately skips pairs that share a
discipline.  Intra-discipline coordination needs the opposite: same discipline,
*different conflicting layers*, judged by plan overlap.

This module reuses the same geometric primitives (shapely + STRtree + spatial
incident grouping) but keys conflicts on a configurable layer-pair table.  It
operates on the cleaned, normalized geometry artifact produced by Phase 1
(meters, identity frame for the reference discipline), using each element's
``model_bounds`` as a footprint proxy.

Honesty note: ``model_bounds`` is an axis-aligned bounding box, not the true
polygon, so overlap area is an upper bound on the real geometric overlap. This
is a coarse-but-real proxy suitable for flagging candidate conflicts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from shapely.geometry import box
from shapely.strtree import STRtree

Severity = Literal["critical", "major", "minor"]


@dataclass(frozen=True)
class Element:
    """Lightweight plan element backed by a bounding box (meters)."""

    handle: str
    layer: str
    dxftype: str
    bounds: tuple[float, float, float, float]  # minx, miny, maxx, maxy
    quality: str
    physical: bool

    @property
    def area(self) -> float:
        minx, miny, maxx, maxy = self.bounds
        return max(maxx - minx, 0.0) * max(maxy - miny, 0.0)

    @property
    def center(self) -> tuple[float, float]:
        minx, miny, maxx, maxy = self.bounds
        return ((minx + maxx) / 2.0, (miny + maxy) / 2.0)


@dataclass(frozen=True)
class LayerPairRule:
    """A pair of layers whose plan overlap should be flagged for review."""

    layer_a: str
    layer_b: str
    label: str
    min_overlap_frac: float = 0.5  # of the smaller element's bbox area
    weight: float = 1.0  # severity multiplier; >1 escalates

    @property
    def key(self) -> frozenset[str]:
        return frozenset({self.layer_a, self.layer_b})


@dataclass
class ClashConfig:
    """Editable intra-discipline clash criterion."""

    pairs: list[LayerPairRule]
    exclude_layers: set[str] = field(default_factory=set)
    quality_allow: set[str] = field(default_factory=lambda: {"good", "coarse"})
    min_abs_area_m2: float = 0.02  # ignore slivers below 200 cm^2
    incident_cell_m: float = 3.0
    # Elements whose bbox area exceeds this are block/group containers, not
    # localizable individual items (e.g. a furniture-layout INSERT whose bbox
    # spans the whole floor). They are excluded as "unlocalizable". Area-based
    # so long thin walls (low area) survive while huge furniture bboxes do not.
    max_element_area_m2: float = 20.0

    def rule_index(self) -> dict[frozenset[str], LayerPairRule]:
        return {rule.key: rule for rule in self.pairs}

    def relevant_layers(self) -> set[str]:
        layers: set[str] = set()
        for rule in self.pairs:
            layers.add(rule.layer_a)
            layers.add(rule.layer_b)
        return layers


@dataclass(frozen=True)
class IntraClash:
    """A single flagged overlap between two elements on conflicting layers."""

    handle_a: str
    handle_b: str
    layer_a: str
    layer_b: str
    rule_label: str
    area_a_m2: float
    area_b_m2: float
    overlap_area_m2: float
    overlap_frac: float
    overlap_bounds_m: tuple[float, float, float, float]
    centroid_m: tuple[float, float]
    severity: Severity

    def as_dict(self) -> dict[str, Any]:
        return {
            "handle_a": self.handle_a,
            "handle_b": self.handle_b,
            "layer_a": self.layer_a,
            "layer_b": self.layer_b,
            "rule_label": self.rule_label,
            "area_a_m2": round(self.area_a_m2, 4),
            "area_b_m2": round(self.area_b_m2, 4),
            "overlap_area_m2": round(self.overlap_area_m2, 4),
            "overlap_frac": round(self.overlap_frac, 4),
            "overlap_bounds_m": [round(v, 4) for v in self.overlap_bounds_m],
            "centroid_m": [round(v, 4) for v in self.centroid_m],
            "severity": self.severity,
        }


@dataclass
class IntraIncident:
    """A spatial cluster of clashes reviewed as one incident."""

    incident_id: str
    cell_key: tuple[int, int]
    members: list[IntraClash]
    representative: IntraClash
    bounds_m: tuple[float, float, float, float]
    centroid_m: tuple[float, float]
    severity: Severity
    layers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "cell_key": list(self.cell_key),
            "member_count": len(self.members),
            "severity": self.severity,
            "layers": list(self.layers),
            "centroid_m": [round(v, 4) for v in self.centroid_m],
            "bounds_m": [round(v, 4) for v in self.bounds_m],
            "representative": self.representative.as_dict(),
            "members": [m.as_dict() for m in self.members],
        }


_SEVERITY_RANK: dict[Severity, int] = {"minor": 0, "major": 1, "critical": 2}


def _severity_from_frac(frac: float, weight: float) -> Severity:
    score = frac * weight
    if score >= 0.8:
        return "critical"
    if score >= 0.5:
        return "major"
    return "minor"


def prepare_elements(
    geometry: dict[str, Any],
    *,
    quality_allow: set[str] | None = None,
    use_main_cluster_window: bool = True,
    max_element_area_m2: float | None = None,
) -> tuple[list[Element], dict[str, Any]]:
    """Build plan elements from a Phase-1 sanitized geometry artifact.

    Filters to physical elements of allowed quality, and (default) keeps only
    elements whose center falls inside the cleaned main-cluster window so far
    strays do not pollute the plan or the clash search. Oversized bboxes
    (block/group containers) are dropped as unlocalizable when
    ``max_element_area_m2`` is given.
    """

    allow = quality_allow if quality_allow is not None else {"good", "coarse"}
    raw = geometry.get("elements") or []
    window = None
    if use_main_cluster_window:
        cleanup = geometry.get("cleanup") or {}
        bounds = cleanup.get("cleaned_outline_bounds_m")
        if bounds and len(bounds) == 4:
            window = tuple(float(v) for v in bounds)

    def in_window(center: tuple[float, float]) -> bool:
        if window is None:
            return True
        minx, miny, maxx, maxy = window
        return minx <= center[0] <= maxx and miny <= center[1] <= maxy

    elements: list[Element] = []
    skipped = {"non_physical": 0, "quality": 0, "stray": 0, "degenerate": 0, "oversize": 0}
    for rec in raw:
        bounds = rec.get("model_bounds")
        if not bounds or len(bounds) != 4:
            skipped["degenerate"] += 1
            continue
        center = rec.get("model_center") or (
            (bounds[0] + bounds[2]) / 2.0,
            (bounds[1] + bounds[3]) / 2.0,
        )
        if not rec.get("physical"):
            skipped["non_physical"] += 1
            continue
        quality = str(rec.get("geometry_quality") or "")
        if quality not in allow:
            skipped["quality"] += 1
            continue
        if not in_window((float(center[0]), float(center[1]))):
            skipped["stray"] += 1
            continue
        el = Element(
            handle=str(rec.get("handle") or ""),
            layer=str(rec.get("layer") or ""),
            dxftype=str(rec.get("dxftype") or ""),
            bounds=(float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3])),
            quality=quality,
            physical=True,
        )
        if el.area <= 0.0:
            skipped["degenerate"] += 1
            continue
        if max_element_area_m2 is not None and el.area > max_element_area_m2:
            skipped["oversize"] += 1
            continue
        elements.append(el)

    meta = {
        "kept": len(elements),
        "skipped": skipped,
        "window_m": list(window) if window else None,
    }
    return elements, meta


def detect(elements: list[Element], config: ClashConfig) -> list[IntraClash]:
    """Find conflicting-layer overlaps among plan elements."""

    rule_index = config.rule_index()
    relevant = config.relevant_layers()

    candidates = [
        el
        for el in elements
        if el.layer in relevant
        and el.layer not in config.exclude_layers
        and el.quality in config.quality_allow
    ]
    if len(candidates) < 2:
        return []

    geoms = [box(*el.bounds) for el in candidates]
    tree = STRtree(geoms)

    clashes: list[IntraClash] = []
    for i, geom_a in enumerate(geoms):
        for raw_j in tree.query(geom_a, predicate="intersects"):
            j = int(raw_j)
            if j <= i:
                continue
            ea = candidates[i]
            eb = candidates[j]
            rule = rule_index.get(frozenset({ea.layer, eb.layer}))
            if rule is None:
                continue
            if ea.handle and ea.handle == eb.handle:
                continue
            inter = geom_a.intersection(geoms[j])
            area = float(inter.area)
            if area < config.min_abs_area_m2 or math.isnan(area):
                continue
            smaller = min(ea.area, eb.area)
            if smaller <= 0:
                continue
            frac = area / smaller
            if frac < rule.min_overlap_frac:
                continue
            cen = inter.centroid
            bnds = inter.bounds
            clashes.append(
                IntraClash(
                    handle_a=ea.handle,
                    handle_b=eb.handle,
                    layer_a=ea.layer,
                    layer_b=eb.layer,
                    rule_label=rule.label,
                    area_a_m2=ea.area,
                    area_b_m2=eb.area,
                    overlap_area_m2=area,
                    overlap_frac=min(frac, 1.0),
                    overlap_bounds_m=(float(bnds[0]), float(bnds[1]), float(bnds[2]), float(bnds[3])),
                    centroid_m=(float(cen.x), float(cen.y)),
                    severity=_severity_from_frac(min(frac, 1.0), rule.weight),
                )
            )

    clashes.sort(key=lambda c: (-_SEVERITY_RANK[c.severity], -c.overlap_area_m2))
    return clashes


def group_incidents(clashes: list[IntraClash], cell_m: float = 3.0) -> list[IntraIncident]:
    """Cluster clashes into incidents by a coarse spatial grid."""

    groups: dict[tuple[int, int], list[IntraClash]] = {}
    for clash in clashes:
        cx, cy = clash.centroid_m
        key = (int(math.floor(cx / cell_m)), int(math.floor(cy / cell_m)))
        groups.setdefault(key, []).append(clash)

    incidents: list[IntraIncident] = []
    for index, (key, members) in enumerate(sorted(groups.items())):
        representative = max(members, key=lambda m: (_SEVERITY_RANK[m.severity], m.overlap_area_m2))
        xs0 = min(m.overlap_bounds_m[0] for m in members)
        ys0 = min(m.overlap_bounds_m[1] for m in members)
        xs1 = max(m.overlap_bounds_m[2] for m in members)
        ys1 = max(m.overlap_bounds_m[3] for m in members)
        severity = max((m.severity for m in members), key=lambda s: _SEVERITY_RANK[s])
        layers = tuple(sorted({lyr for m in members for lyr in (m.layer_a, m.layer_b)}))
        incidents.append(
            IntraIncident(
                incident_id=f"ARQ-INTRA-{index + 1:03d}",
                cell_key=key,
                members=members,
                representative=representative,
                bounds_m=(xs0, ys0, xs1, ys1),
                centroid_m=((xs0 + xs1) / 2.0, (ys0 + ys1) / 2.0),
                severity=severity,
                layers=layers,
            )
        )

    incidents.sort(
        key=lambda inc: (
            -_SEVERITY_RANK[inc.severity],
            -len(inc.members),
            -inc.representative.overlap_area_m2,
        )
    )
    for new_index, inc in enumerate(incidents, start=1):
        inc.incident_id = f"ARQ-INTRA-{new_index:03d}"
    return incidents
