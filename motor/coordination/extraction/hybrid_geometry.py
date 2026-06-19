"""Build hybrid DXF/APS sheet-frame geometry records."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from coordination.extraction.dxf_aps_alignment import (
    DxfApsAlignmentReport,
    DxfApsAlignmentTransform,
    apply_alignment_to_bounds,
    apply_alignment_to_point,
)
from coordination.extraction.dxf_aps_matching import DxfApsMatchPair, DxfApsMatchReport
from coordination.extraction.dxf_geometry import BoundsXY, is_annotation_layer

HYBRID_COORDINATE_UNIT = "sheet_paper_units"
DXF_TRANSFORMED_GEOMETRY_SOURCE = "dxf_ezdxf_transformed"
APS_FRAGMENT_FALLBACK_GEOMETRY_SOURCE = "aps_fragment_fallback"


@dataclass(frozen=True)
class HybridGeometryRecord:
    handle: str
    db_id: str | None
    layer: str
    discipline: str
    dxftype: str
    source_ref: str
    view_name: str
    sheet_bounds: BoundsXY
    sheet_center: tuple[float, float]
    geometry_source: str
    geometry_quality: str
    coordinate_unit: str = HYBRID_COORDINATE_UNIT
    model_bounds: BoundsXY | None = None
    model_center: tuple[float, float] | None = None
    aps_sheet_bounds: BoundsXY | None = None
    transform_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "dbId": self.db_id,
            "layer": self.layer,
            "discipline": self.discipline,
            "dxftype": self.dxftype,
            "source_ref": self.source_ref,
            "view_name": self.view_name,
            "sheet_bounds": [float(v) for v in self.sheet_bounds],
            "sheet_center": [float(v) for v in self.sheet_center],
            "geometry_source": self.geometry_source,
            "geometry_quality": self.geometry_quality,
            "coordinate_unit": self.coordinate_unit,
            "model_bounds": [float(v) for v in self.model_bounds] if self.model_bounds is not None else None,
            "model_center": [float(v) for v in self.model_center] if self.model_center is not None else None,
            "aps_sheet_bounds": [float(v) for v in self.aps_sheet_bounds] if self.aps_sheet_bounds is not None else None,
            "transform_status": self.transform_status,
        }


@dataclass
class HybridGeometryBuildReport:
    records: list[HybridGeometryRecord] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=dict)
    quality_counts: dict[str, int] = field(default_factory=dict)
    view_source_counts: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_count": len(self.records),
            "skipped": dict(self.skipped),
            "source_counts": dict(self.source_counts),
            "quality_counts": dict(self.quality_counts),
            "view_source_counts": {
                view: dict(counts) for view, counts in self.view_source_counts.items()
            },
            "records": [record.to_dict() for record in self.records],
        }


def _center(bounds: BoundsXY) -> tuple[float, float]:
    return ((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0)


def _alignment_for_pair(
    pair: DxfApsMatchPair,
    alignments_by_view: dict[str, DxfApsAlignmentReport | DxfApsAlignmentTransform | dict[str, Any]],
) -> DxfApsAlignmentTransform | dict[str, Any] | None:
    alignment = alignments_by_view.get(pair.aps.view_name)
    if isinstance(alignment, DxfApsAlignmentReport):
        return alignment.transform
    return alignment


def _transform_status(transform: DxfApsAlignmentTransform | dict[str, Any]) -> str:
    if isinstance(transform, DxfApsAlignmentTransform):
        return transform.status
    return str(transform.get("status") or "")


def build_hybrid_geometry(
    match_report: DxfApsMatchReport,
    alignments_by_view: dict[str, DxfApsAlignmentReport | DxfApsAlignmentTransform | dict[str, Any]],
    *,
    include_aps_fallback: bool = True,
) -> HybridGeometryBuildReport:
    """Transform matched DXF physical geometry into APS sheet coordinates."""
    skipped: Counter[str] = Counter()
    records: list[HybridGeometryRecord] = []
    used_handle_views: set[tuple[str, str]] = set()

    for pair in match_report.pairs:
        transform = _alignment_for_pair(pair, alignments_by_view)
        if transform is None:
            skipped["missing_alignment"] += 1
            continue
        status = _transform_status(transform)
        if status != "ok":
            skipped[f"alignment_{status or 'unknown'}"] += 1
            continue
        sheet_bounds = apply_alignment_to_bounds(pair.dxf.model_bounds, transform)
        sheet_center = apply_alignment_to_point(pair.dxf.model_center, transform)
        records.append(
            HybridGeometryRecord(
                handle=pair.handle,
                db_id=pair.aps.db_id,
                layer=pair.dxf.layer,
                discipline=pair.dxf.discipline,
                dxftype=pair.dxf.dxftype,
                source_ref=pair.dxf.source_ref,
                view_name=pair.aps.view_name,
                sheet_bounds=sheet_bounds,
                sheet_center=sheet_center,
                geometry_source=DXF_TRANSFORMED_GEOMETRY_SOURCE,
                geometry_quality=pair.dxf.geometry_quality,
                model_bounds=pair.dxf.model_bounds,
                model_center=pair.dxf.model_center,
                aps_sheet_bounds=pair.aps.sheet_world_bounds,
                transform_status=status,
            )
        )
        used_handle_views.add((pair.handle, pair.aps.view_name))

    if include_aps_fallback:
        for aps in match_report.aps_records:
            if (aps.handle, aps.view_name) in used_handle_views:
                continue
            if is_annotation_layer(aps.layer):
                skipped["fallback_aps_annotation_layer"] += 1
                continue
            if aps.geometry_quality not in {"good", "coarse"}:
                skipped[f"fallback_aps_quality_{aps.geometry_quality}"] += 1
                continue
            records.append(
                HybridGeometryRecord(
                    handle=aps.handle,
                    db_id=aps.db_id,
                    layer=aps.layer,
                    discipline="",
                    dxftype="APS_OBJECT",
                    source_ref=f"{aps.view_name}|aps_fragment:{aps.handle}",
                    view_name=aps.view_name,
                    sheet_bounds=aps.sheet_world_bounds,
                    sheet_center=_center(aps.sheet_world_bounds),
                    geometry_source=APS_FRAGMENT_FALLBACK_GEOMETRY_SOURCE,
                    geometry_quality=aps.geometry_quality,
                    aps_sheet_bounds=aps.sheet_world_bounds,
                    transform_status=None,
                )
            )

    source_counts = Counter(record.geometry_source for record in records)
    quality_counts = Counter(record.geometry_quality for record in records)
    view_source_counts: dict[str, dict[str, int]] = {}
    for record in records:
        view_counts = view_source_counts.setdefault(record.view_name, {})
        view_counts[record.geometry_source] = view_counts.get(record.geometry_source, 0) + 1
    return HybridGeometryBuildReport(
        records=records,
        skipped=dict(sorted(skipped.items())),
        source_counts=dict(sorted(source_counts.items())),
        quality_counts=dict(sorted(quality_counts.items())),
        view_source_counts={k: dict(sorted(v.items())) for k, v in sorted(view_source_counts.items())},
    )
