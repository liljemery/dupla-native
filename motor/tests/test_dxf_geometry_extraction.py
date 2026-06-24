"""Tests for low-level ezdxf model-space geometry extraction."""

from __future__ import annotations

import sys
from pathlib import Path

import ezdxf

MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from coordination.core.models_25d import Discipline
from coordination.extraction.dxf_geometry import (
    DXF_EZDXF_GEOMETRY_SOURCE,
    MODEL_METERS_COORDINATE_UNIT,
    extract_dxf_geometry,
)


def _write_basic_dxf(path: Path) -> None:
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    doc.layers.add("A-WALL")
    doc.layers.add("E-LIGHT")
    doc.layers.add("TEXTOS")

    msp = doc.modelspace()
    msp.add_line((1.0, 2.0), (4.0, 6.0), dxfattribs={"layer": "A-WALL"})
    msp.add_circle((20.0, 30.0), 2.5, dxfattribs={"layer": "E-LIGHT"})
    msp.add_text("note", dxfattribs={"layer": "TEXTOS"}).set_placement((100.0, 100.0))

    block = doc.blocks.new("DOOR_BLOCK")
    block.add_line((0.0, 0.0), (2.0, 1.0), dxfattribs={"layer": "A-WALL"})
    msp.add_blockref(
        "DOOR_BLOCK",
        (10.0, 20.0),
        dxfattribs={"layer": "A-DOOR", "xscale": 2.0, "yscale": 3.0},
    )

    doc.saveas(path)


def test_extract_dxf_geometry_emits_handle_records_with_model_bounds(tmp_path: Path) -> None:
    dxf_path = tmp_path / "sample.dxf"
    _write_basic_dxf(dxf_path)

    result = extract_dxf_geometry(dxf_path, Discipline.ARCH)
    wall = next(record for record in result.records if record.dxftype == "LINE" and record.layer == "A-WALL")
    circle = next(record for record in result.records if record.dxftype == "CIRCLE")

    assert result.dxf_present is True
    assert result.insunits == 6
    assert wall.handle
    assert wall.model_bounds == (1.0, 2.0, 4.0, 6.0)
    assert wall.model_center == (2.5, 4.0)
    assert wall.coordinate_unit == MODEL_METERS_COORDINATE_UNIT
    assert wall.geometry_source == DXF_EZDXF_GEOMETRY_SOURCE
    assert wall.geometry_quality == "good"
    assert wall.is_physical is True
    assert circle.model_bounds == (17.5, 27.5, 22.5, 32.5)


def test_extract_dxf_geometry_resolves_insert_from_cached_block_bbox(tmp_path: Path) -> None:
    dxf_path = tmp_path / "sample.dxf"
    _write_basic_dxf(dxf_path)

    result = extract_dxf_geometry(dxf_path, "ARQUITECTURA")
    insert = next(record for record in result.records if record.dxftype == "INSERT")

    assert insert.block_name == "DOOR_BLOCK"
    assert insert.block_resolution_method == "insert_block_bbox"
    assert insert.model_bounds == (10.0, 20.0, 14.0, 23.0)
    assert insert.model_center == (12.0, 21.5)
    assert result.stats.insert_stats["insert_total"] == 1
    assert result.stats.insert_stats["insert_resolved"] == 1
    assert result.stats.insert_stats["block_bbox_resolved"] == 1
    assert result.stats.insert_stats["block_defs_cached"] >= 1


def test_extract_dxf_geometry_can_return_only_physical_entities(tmp_path: Path) -> None:
    dxf_path = tmp_path / "sample.dxf"
    _write_basic_dxf(dxf_path)

    result = extract_dxf_geometry(dxf_path, Discipline.ARCH, include_non_physical=False)

    assert {record.dxftype for record in result.records} == {"LINE", "CIRCLE", "INSERT"}
    assert all(record.is_physical for record in result.records)
    assert result.stats.all_entities == 4
    assert result.stats.physical_entities == 3
    assert result.stats.physical_bbox_ok == 3


def test_extract_dxf_geometry_serializes_stable_contract(tmp_path: Path) -> None:
    dxf_path = tmp_path / "sample.dxf"
    _write_basic_dxf(dxf_path)

    payload = extract_dxf_geometry(dxf_path, Discipline.MEP_ELEC).to_dict()
    first = payload["records"][0]

    assert payload["path"] == str(dxf_path)
    assert payload["discipline"] == "ELECTRICIDAD"
    assert payload["coordinate_unit"] == MODEL_METERS_COORDINATE_UNIT
    assert payload["stats"]["all_entities"] == 4
    assert {
        "handle",
        "layer",
        "discipline",
        "dxftype",
        "source_ref",
        "model_bounds",
        "model_center",
        "geometry_source",
        "geometry_quality",
        "coordinate_unit",
        "block_resolution_method",
        "is_physical",
        "block_name",
    }.issubset(first)


def test_probe_dxf_readable_valid_and_invalid(tmp_path: Path) -> None:
    from coordination.extraction.dxf_geometry import probe_dxf_readable

    valid = tmp_path / "ok.dxf"
    _write_basic_dxf(valid)
    assert probe_dxf_readable(valid)

    bad = tmp_path / "bad.dxf"
    bad.write_text("0\nSECTION\n", encoding="utf-8")
    assert not probe_dxf_readable(bad)


def test_parse_error_line_reads_ezdxf_message() -> None:
    from coordination.extraction.dxf_geometry import _parse_error_line

    assert _parse_error_line(Exception('Invalid group code "X" at line 42.')) == 42
    assert _parse_error_line(Exception("no line here")) is None


def test_salvage_dxf_at_line_truncates_before_error(tmp_path: Path) -> None:
    from coordination.extraction.dxf_geometry import _salvage_dxf_at_line

    source = tmp_path / "source.dxf"
    source.write_text("0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n", encoding="utf-8")
    salvaged = _salvage_dxf_at_line(source, 4)
    assert salvaged is not None
    text = salvaged.read_text(encoding="utf-8")
    assert "SECTION" in text
    assert "HEADER" not in text
    assert text.endswith("0\nEOF\n")


def test_read_dxf_salvage_when_recover_fails(tmp_path: Path, monkeypatch) -> None:
    from ezdxf import recover as recover_mod

    from coordination.extraction import dxf_geometry as dg

    source = tmp_path / "source.dxf"
    _write_basic_dxf(source)
    err_line = len(source.read_text(encoding="utf-8").splitlines()) + 1
    real_recover = recover_mod.readfile

    def fail_read(path: str, errors: str | None = None) -> object:
        if ".salvaged" in path:
            return real_recover(path, errors=errors)
        raise Exception(f'Invalid group code "X" at line {err_line}.')

    monkeypatch.setattr(dg.ezdxf, "readfile", lambda path: fail_read(path))
    monkeypatch.setattr(recover_mod, "readfile", fail_read)

    doc, _partial, salvaged = dg._read_dxf(source)
    assert salvaged
    assert len(list(doc.modelspace())) >= 3

