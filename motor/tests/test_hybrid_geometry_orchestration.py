"""Integration-style tests for the DXF -> APS -> hybrid geometry orchestration."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import ezdxf

MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from coordination.core.models_25d import Discipline
from coordination.extraction.dxf_aps_alignment import solve_dxf_to_aps_alignment_by_view
from coordination.extraction.dxf_aps_matching import build_dxf_aps_match_report
from coordination.extraction.dxf_geometry import extract_dxf_geometry
from coordination.extraction.hybrid_geometry import (
    APS_FRAGMENT_FALLBACK_GEOMETRY_SOURCE,
    DXF_TRANSFORMED_GEOMETRY_SOURCE,
    build_hybrid_geometry,
)


def _sheet_xy(model_xy: tuple[float, float], *, outlier: bool = False) -> tuple[float, float]:
    if outlier:
        return (99.0, 99.0)
    scale = 0.5
    rotation = math.radians(10.0)
    c, s = math.cos(rotation), math.sin(rotation)
    x, y = model_xy
    return (
        scale * (c * x - s * y) + 2.0,
        scale * (s * x + c * y) + 3.0,
    )


def _write_dxf(path: Path) -> dict[str, tuple[float, float]]:
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    doc.layers.add("A-WALL")
    doc.layers.add("A-DOOR")
    doc.layers.add("TEXTOS")

    msp = doc.modelspace()
    entities = [
        msp.add_line((0.0, 0.0), (2.0, 2.0), dxfattribs={"layer": "A-WALL"}),
        msp.add_line((20.0, 0.0), (22.0, 2.0), dxfattribs={"layer": "A-WALL"}),
        msp.add_line((0.0, 12.0), (2.0, 14.0), dxfattribs={"layer": "A-WALL"}),
        msp.add_line((20.0, 12.0), (22.0, 14.0), dxfattribs={"layer": "A-WALL"}),
        msp.add_lwpolyline(
            [(7.0, 5.0), (9.0, 5.0), (9.0, 7.0), (7.0, 7.0)],
            close=True,
            dxfattribs={"layer": "A-DOOR"},
        ),
    ]
    note = msp.add_text("annotation", dxfattribs={"layer": "TEXTOS"})
    note.set_placement((50.0, 50.0))

    doc.saveas(path)

    centers: dict[str, tuple[float, float]] = {}
    for entity in entities:
        handle = str(entity.dxf.handle).upper()
        if entity.dxftype() == "LWPOLYLINE":
            centers[handle] = (8.0, 6.0)
        else:
            start = entity.dxf.start
            end = entity.dxf.end
            centers[handle] = ((float(start.x) + float(end.x)) / 2.0, (float(start.y) + float(end.y)) / 2.0)
    centers[str(note.dxf.handle).upper()] = (50.0, 50.0)
    return centers


def _viewer_dump(centers: dict[str, tuple[float, float]], *, bad_handle: str | None = None) -> dict:
    objects = []
    for index, (handle, model_center) in enumerate(centers.items(), start=1):
        layer = "TEXTOS" if model_center == (50.0, 50.0) else "A-WALL"
        sx, sy = _sheet_xy(model_center, outlier=handle == bad_handle)
        objects.append(
            {
                "handle": handle,
                "dbId": index,
                "layer": layer,
                "world_bounds": [sx - 0.1, sy - 0.1, sx + 0.1, sy + 0.1],
            }
        )
    objects.append(
        {
            "handle": "APS_ONLY",
            "dbId": 999,
            "layer": "A-WALL",
            "world_bounds": [20.0, 20.0, 21.0, 21.0],
        }
    )
    return {
        "views": [
            {
                "name": "A-1.1",
                "sheet_bounds": [0.0, 0.0, 36.0, 24.0],
                "objects": objects,
            }
        ]
    }


def test_full_hybrid_geometry_orchestration_from_dxf_and_viewer_dump(tmp_path: Path) -> None:
    dxf_path = tmp_path / "sheet.dxf"
    centers = _write_dxf(dxf_path)
    dxf = extract_dxf_geometry(dxf_path, Discipline.ARCH, include_non_physical=False)
    match_report = build_dxf_aps_match_report(dxf, _viewer_dump(centers))
    alignments = solve_dxf_to_aps_alignment_by_view(match_report.pairs)

    hybrid = build_hybrid_geometry(match_report, alignments)

    assert alignments["A-1.1"].transform.status == "ok"
    assert alignments["A-1.1"].transform.n_inliers == 5
    assert match_report.rejected.get("dxf_non_physical", 0) == 0
    assert hybrid.source_counts[DXF_TRANSFORMED_GEOMETRY_SOURCE] == 5
    assert hybrid.source_counts[APS_FRAGMENT_FALLBACK_GEOMETRY_SOURCE] == 1
    assert all(record.coordinate_unit == "sheet_paper_units" for record in hybrid.records)
    assert all(record.db_id for record in hybrid.records)


def test_orchestration_reports_outlier_without_losing_hybrid_inliers(tmp_path: Path) -> None:
    dxf_path = tmp_path / "sheet.dxf"
    centers = _write_dxf(dxf_path)
    bad_handle = next(handle for handle, center in centers.items() if center == (8.0, 6.0))
    dxf = extract_dxf_geometry(dxf_path, Discipline.ARCH, include_non_physical=False)
    match_report = build_dxf_aps_match_report(dxf, _viewer_dump(centers, bad_handle=bad_handle))
    alignments = solve_dxf_to_aps_alignment_by_view(match_report.pairs)

    hybrid = build_hybrid_geometry(match_report, alignments)

    assert alignments["A-1.1"].transform.status == "ok"
    assert alignments["A-1.1"].transform.n_outliers == 1
    assert alignments["A-1.1"].outlier_handles == [bad_handle]
    assert hybrid.source_counts[DXF_TRANSFORMED_GEOMETRY_SOURCE] == 5
    assert hybrid.source_counts[APS_FRAGMENT_FALLBACK_GEOMETRY_SOURCE] == 1


def test_orchestration_skips_hybrid_records_when_alignment_is_insufficient(tmp_path: Path) -> None:
    dxf_path = tmp_path / "sheet.dxf"
    centers = _write_dxf(dxf_path)
    keep = dict(list(centers.items())[:2])
    dxf = extract_dxf_geometry(dxf_path, Discipline.ARCH, include_non_physical=False)
    match_report = build_dxf_aps_match_report(dxf, _viewer_dump(keep))
    alignments = solve_dxf_to_aps_alignment_by_view(match_report.pairs)

    hybrid = build_hybrid_geometry(match_report, alignments, include_aps_fallback=False)

    assert alignments["A-1.1"].transform.status == "insufficient"
    assert hybrid.records == []
    assert hybrid.skipped == {"alignment_insufficient": 2}
