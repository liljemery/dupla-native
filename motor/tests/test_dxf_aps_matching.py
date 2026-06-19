"""Tests for DXF to APS handle correspondence matching."""

from __future__ import annotations

import sys
from pathlib import Path

import ezdxf

MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from coordination.core.models_25d import Discipline
from coordination.extraction.dxf_aps_matching import (
    aps_records_from_viewer_dump,
    build_dxf_aps_match_report,
)
from coordination.extraction.dxf_geometry import extract_dxf_geometry


def _write_match_dxf(path: Path) -> dict[str, str]:
    doc = ezdxf.new("R2010", setup=True)
    doc.layers.add("A-WALL")
    doc.layers.add("A-DOOR")
    doc.layers.add("TEXTOS")
    msp = doc.modelspace()
    wall = msp.add_line((1.0, 2.0), (4.0, 6.0), dxfattribs={"layer": "A-WALL"})
    door = msp.add_lwpolyline(
        [(10.0, 10.0), (12.0, 10.0), (12.0, 11.0), (10.0, 11.0)],
        close=True,
        dxfattribs={"layer": "A-DOOR"},
    )
    note = msp.add_text("note", dxfattribs={"layer": "TEXTOS"})
    note.set_placement((20.0, 20.0))
    doc.saveas(path)
    return {
        "wall": wall.dxf.handle,
        "door": door.dxf.handle,
        "note": note.dxf.handle,
    }


def _viewer(handles: dict[str, str]) -> dict:
    return {
        "views": [
            {
                "name": "A-1.1",
                "sheet_bounds": [0.0, 0.0, 36.0, 24.0],
                "objects": [
                    {
                        "handle": handles["wall"],
                        "dbId": 101,
                        "layer": "A-WALL",
                        "world_bounds": [1.0, 2.0, 4.0, 6.0],
                    },
                    {
                        "handle": handles["door"],
                        "dbId": 202,
                        "layer": "A-DOOR",
                        "world_bounds": [0.0, 0.0, 36.0, 24.0],
                        "fragments": [
                            {"world_bounds": [0.0, 0.0, 36.0, 24.0]},
                            {"world_bounds": [10.0, 10.0, 12.0, 11.0]},
                        ],
                    },
                    {
                        "handle": handles["note"],
                        "dbId": 303,
                        "layer": "TEXTOS",
                        "world_bounds": [20.0, 20.0, 21.0, 21.0],
                    },
                ],
            }
        ]
    }


def test_aps_records_from_viewer_dump_refines_full_sheet_fragments(tmp_path: Path) -> None:
    handles = _write_match_dxf(tmp_path / "sample.dxf")

    records = aps_records_from_viewer_dump(_viewer(handles))
    door = next(record for record in records if record.handle == handles["door"].upper())

    assert door.db_id == "202"
    assert door.geometry_quality == "good"
    assert door.refinement == "fragment_refined"
    assert door.sheet_world_bounds == (10.0, 10.0, 12.0, 11.0)
    assert door.sheet_center == (11.0, 10.5)


def test_build_dxf_aps_match_report_pairs_clean_physical_handles(tmp_path: Path) -> None:
    dxf_path = tmp_path / "sample.dxf"
    handles = _write_match_dxf(dxf_path)
    dxf = extract_dxf_geometry(dxf_path, Discipline.ARCH)

    report = build_dxf_aps_match_report(dxf, _viewer(handles))

    assert len(report.pairs) == 2
    assert report.pairs_by_view == {"A-1.1": 2}
    assert {pair.handle for pair in report.pairs} == {handles["wall"].upper(), handles["door"].upper()}
    assert report.rejected["dxf_non_physical"] == 1
    assert report.pairs[0].to_dict()["dbId"] in {"101", "202"}


def test_build_dxf_aps_match_report_rejects_unlocalizable_aps_bounds(tmp_path: Path) -> None:
    dxf_path = tmp_path / "sample.dxf"
    handles = _write_match_dxf(dxf_path)
    payload = _viewer(handles)
    payload["views"][0]["objects"][0]["world_bounds"] = [0.0, 0.0, 36.0, 24.0]
    payload["views"][0]["objects"][0].pop("fragments", None)
    dxf = extract_dxf_geometry(dxf_path, Discipline.ARCH)

    report = build_dxf_aps_match_report(dxf, payload)

    assert len(report.pairs) == 1
    assert report.rejected["aps_quality_unlocalizable"] == 1
    assert report.pairs[0].handle == handles["door"].upper()


def test_build_dxf_aps_match_report_can_allow_coarse_aps_pairs(tmp_path: Path) -> None:
    dxf_path = tmp_path / "sample.dxf"
    handles = _write_match_dxf(dxf_path)
    payload = _viewer(handles)
    payload["views"][0]["objects"][0]["world_bounds"] = [1.0, 2.0, 30.0, 4.0]
    dxf = extract_dxf_geometry(dxf_path, Discipline.ARCH)

    strict = build_dxf_aps_match_report(dxf, payload)
    relaxed = build_dxf_aps_match_report(dxf, payload, allowed_aps_qualities=("good", "coarse"))

    assert strict.rejected["aps_quality_coarse"] == 1
    assert len(strict.pairs) == 1
    assert len(relaxed.pairs) == 2

