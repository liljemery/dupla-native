"""Tests for FOSS local_cad_pipeline -> cad_facts contract."""

from __future__ import annotations

import sys
from pathlib import Path

import ezdxf

MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from coordination.core.models_25d import Discipline
from coordination.extraction.local_cad_pipeline import (
    LOCAL_EXTRACTOR,
    extract_cad_facts,
    extract_dxf_records,
    records_to_cad_facts,
    records_to_elements25d,
)


def _write_wall_dxf(path: Path) -> None:
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    doc.layers.add("A-WALL")
    msp = doc.modelspace()
    msp.add_line((0.0, 0.0), (10.0, 0.0), dxfattribs={"layer": "A-WALL"})
    doc.saveas(path)


def test_records_to_cad_facts_shape(tmp_path: Path) -> None:
    dxf_path = tmp_path / "wall.dxf"
    _write_wall_dxf(dxf_path)
    extraction = extract_dxf_records(dxf_path, Discipline.ARCH)
    payload = records_to_cad_facts(extraction, source_path=dxf_path)

    assert payload["extractor"] == LOCAL_EXTRACTOR
    cad = payload["cad_facts"]
    assert "A-WALL" in cad["layers"]
    assert cad["layers"]["A-WALL"]["object_count"] >= 1
    assert any(hint.get("layer") == "A-WALL" for hint in cad["geometry_hints"])
    assert "inventory_hints" in payload


def test_extract_cad_facts_caches(tmp_path: Path) -> None:
    dxf_path = tmp_path / "wall.dxf"
    _write_wall_dxf(dxf_path)
    cache_root = tmp_path / "cache"
    first = extract_cad_facts(dxf_path, cache_root=cache_root)
    second = extract_cad_facts(dxf_path, cache_root=cache_root)
    assert first["cad_facts"]["layers"] == second["cad_facts"]["layers"]


def test_records_to_elements25d_emits_footprints(tmp_path: Path) -> None:
    dxf_path = tmp_path / "large.dxf"
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    doc.layers.add("A-WALL")
    msp = doc.modelspace()
    msp.add_lwpolyline([(0.0, 0.0), (20.0, 0.0), (20.0, 15.0), (0.0, 15.0)], close=True, dxfattribs={"layer": "A-WALL"})
    doc.saveas(dxf_path)

    extraction = extract_dxf_records(dxf_path, Discipline.ARCH)
    elements = records_to_elements25d(
        extraction,
        Discipline.ARCH,
        level_id="NPT_P1",
        translation_mm=(0.0, 0.0),
        path_label="large",
        coordination_issue_key="d:20240101",
        min_area_mm2=1.0,
    )
    assert elements
    assert elements[0].footprint_coords_mm
    assert elements[0].metadata.get("geometry_source") == LOCAL_EXTRACTOR
