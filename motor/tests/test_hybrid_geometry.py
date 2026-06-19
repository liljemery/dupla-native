"""Tests for hybrid DXF-transformed/APS geometry build."""

from __future__ import annotations

import sys
from pathlib import Path

MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from coordination.extraction.dxf_aps_alignment import DxfApsAlignmentReport, DxfApsAlignmentTransform
from coordination.extraction.dxf_aps_matching import ApsGeometryRecord, DxfApsMatchPair, DxfApsMatchReport
from coordination.extraction.dxf_geometry import DxfGeometryRecord
from coordination.extraction.hybrid_geometry import (
    APS_FRAGMENT_FALLBACK_GEOMETRY_SOURCE,
    DXF_TRANSFORMED_GEOMETRY_SOURCE,
    build_hybrid_geometry,
)


def _dxf(handle: str, bounds=(0.0, 0.0, 2.0, 2.0)) -> DxfGeometryRecord:
    return DxfGeometryRecord(
        handle=handle,
        layer="A-WALL",
        discipline="ARQUITECTURA",
        dxftype="LINE",
        source_ref=f"sample|{handle}",
        model_bounds=bounds,
        model_center=((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0),
        geometry_quality="good",
        is_physical=True,
        block_resolution_method="direct_fast",
    )


def _aps(handle: str, *, view="A-1.1", bounds=(10.0, 10.0, 12.0, 12.0), quality="good") -> ApsGeometryRecord:
    return ApsGeometryRecord(
        handle=handle,
        db_id=f"db-{handle}",
        layer="A-WALL",
        view_name=view,
        sheet_bounds=(0.0, 0.0, 36.0, 24.0),
        sheet_world_bounds=bounds,
        sheet_center=((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0),
        geometry_quality=quality,
        refinement="aggregate",
    )


def _transform(status: str = "ok") -> DxfApsAlignmentTransform:
    return DxfApsAlignmentTransform(
        status=status,
        scale=0.5 if status == "ok" else None,
        rotation_deg=0.0 if status == "ok" else None,
        translation=(2.0, 3.0) if status == "ok" else None,
        matrix=((0.5, 0.0), (0.0, 0.5)) if status == "ok" else None,
        n_pairs=3,
        n_inliers=3 if status == "ok" else 0,
    )


def test_build_hybrid_geometry_transforms_dxf_bounds_to_sheet_frame() -> None:
    pair = DxfApsMatchPair(handle="H1", dxf=_dxf("H1"), aps=_aps("H1"))
    match_report = DxfApsMatchReport(pairs=[pair], aps_records=[pair.aps])

    report = build_hybrid_geometry(match_report, {"A-1.1": _transform()})
    record = report.records[0]

    assert len(report.records) == 1
    assert record.geometry_source == DXF_TRANSFORMED_GEOMETRY_SOURCE
    assert record.handle == "H1"
    assert record.db_id == "db-H1"
    assert record.sheet_bounds == (2.0, 3.0, 3.0, 4.0)
    assert record.sheet_center == (2.5, 3.5)
    assert record.model_bounds == (0.0, 0.0, 2.0, 2.0)
    assert record.aps_sheet_bounds == (10.0, 10.0, 12.0, 12.0)
    assert report.source_counts == {DXF_TRANSFORMED_GEOMETRY_SOURCE: 1}


def test_build_hybrid_geometry_accepts_alignment_report_wrapper() -> None:
    pair = DxfApsMatchPair(handle="H1", dxf=_dxf("H1"), aps=_aps("H1"))
    alignment = DxfApsAlignmentReport(transform=_transform(), view_name="A-1.1")

    report = build_hybrid_geometry(DxfApsMatchReport(pairs=[pair], aps_records=[pair.aps]), {"A-1.1": alignment})

    assert report.records[0].sheet_center == (2.5, 3.5)


def test_build_hybrid_geometry_skips_pairs_without_ok_alignment() -> None:
    pair = DxfApsMatchPair(handle="H1", dxf=_dxf("H1"), aps=_aps("H1"))

    report = build_hybrid_geometry(
        DxfApsMatchReport(pairs=[pair], aps_records=[pair.aps]),
        {"A-1.1": _transform("insufficient")},
        include_aps_fallback=False,
    )

    assert report.records == []
    assert report.skipped == {"alignment_insufficient": 1}


def test_build_hybrid_geometry_adds_aps_fallback_for_unmatched_good_records() -> None:
    pair = DxfApsMatchPair(handle="H1", dxf=_dxf("H1"), aps=_aps("H1"))
    fallback = _aps("H2", bounds=(5.0, 6.0, 7.0, 8.0))
    match_report = DxfApsMatchReport(pairs=[pair], aps_records=[pair.aps, fallback])

    report = build_hybrid_geometry(match_report, {"A-1.1": _transform()})
    fallback_record = next(record for record in report.records if record.handle == "H2")

    assert len(report.records) == 2
    assert fallback_record.geometry_source == APS_FRAGMENT_FALLBACK_GEOMETRY_SOURCE
    assert fallback_record.sheet_bounds == (5.0, 6.0, 7.0, 8.0)
    assert fallback_record.model_bounds is None
    assert report.source_counts == {
        APS_FRAGMENT_FALLBACK_GEOMETRY_SOURCE: 1,
        DXF_TRANSFORMED_GEOMETRY_SOURCE: 1,
    }


def test_build_hybrid_geometry_rejects_unlocalizable_aps_fallback() -> None:
    fallback = _aps("H2", bounds=(0.0, 0.0, 36.0, 24.0), quality="unlocalizable")
    match_report = DxfApsMatchReport(pairs=[], aps_records=[fallback])

    report = build_hybrid_geometry(match_report, {})

    assert report.records == []
    assert report.skipped == {"fallback_aps_quality_unlocalizable": 1}


def test_build_hybrid_geometry_view_source_counts_populated() -> None:
    pair = DxfApsMatchPair(handle="H1", dxf=_dxf("H1"), aps=_aps("H1", view="A-1.1"))
    fallback = _aps("H2", view="A-1.2", bounds=(5.0, 6.0, 7.0, 8.0))
    match_report = DxfApsMatchReport(pairs=[pair], aps_records=[pair.aps, fallback])

    report = build_hybrid_geometry(match_report, {"A-1.1": _transform()})

    assert report.view_source_counts["A-1.1"] == {DXF_TRANSFORMED_GEOMETRY_SOURCE: 1}
    assert report.view_source_counts["A-1.2"] == {APS_FRAGMENT_FALLBACK_GEOMETRY_SOURCE: 1}


def test_build_hybrid_geometry_same_handle_different_views_not_deduplicated() -> None:
    """Handle dedup must be per (handle, view_name); same handle in view B is kept as fallback."""
    aps_view_a = _aps("H1", view="A-1.1", bounds=(10.0, 10.0, 12.0, 12.0))
    aps_view_b = _aps("H1", view="A-1.2", bounds=(20.0, 20.0, 22.0, 22.0))
    pair = DxfApsMatchPair(handle="H1", dxf=_dxf("H1"), aps=aps_view_a)
    match_report = DxfApsMatchReport(pairs=[pair], aps_records=[aps_view_a, aps_view_b])

    report = build_hybrid_geometry(match_report, {"A-1.1": _transform()})

    handles_by_view = {(r.handle, r.view_name) for r in report.records}
    assert ("H1", "A-1.1") in handles_by_view, "DXF-transformed record for view A-1.1 must be present"
    assert ("H1", "A-1.2") in handles_by_view, "APS fallback for same handle in view A-1.2 must be kept"
    assert len(report.records) == 2


def test_build_hybrid_geometry_same_handle_same_view_deduplicated() -> None:
    """Handle in the same view must not be duplicated even if it appears twice in aps_records."""
    aps = _aps("H1", view="A-1.1")
    pair = DxfApsMatchPair(handle="H1", dxf=_dxf("H1"), aps=aps)
    match_report = DxfApsMatchReport(pairs=[pair], aps_records=[aps, aps])

    report = build_hybrid_geometry(match_report, {"A-1.1": _transform()})

    view_a_records = [r for r in report.records if r.view_name == "A-1.1"]
    assert len(view_a_records) == 1, "DXF-transformed record must not be doubled by APS fallback in same view"

