"""Budget line provenance suffixes."""

from __future__ import annotations

from budget.provenance import append_provenance, format_provenance_suffix, source_file_from_takeoff
from core.schemas import QuantityTakeoff


def test_provenance_suffix_includes_level_and_file() -> None:
    takeoff = QuantityTakeoff(
        item_key="wall:1",
        item_type="wall_length",
        level_id="level_02",
        unit="m",
        quantity=12.0,
        inputs={"level_name": "N2", "source_file": "Cimientos Las Nasas Rev 1.dwg"},
        source_refs=["file:Cimientos Las Nasas Rev 1.dwg", "geometry:MUROS"],
    )
    suffix = format_provenance_suffix(takeoff)
    assert "N2" in suffix
    assert "Cimientos Las Nasas Rev 1.dwg" in suffix


def test_append_provenance_when_missing() -> None:
    takeoff = QuantityTakeoff(
        item_key="beam:1",
        item_type="beam_volume",
        unit="m3",
        quantity=1.0,
        inputs={"source_file": "ES 01 General Details.dwg"},
        source_refs=["file:ES 01 General Details.dwg"],
    )
    out = append_provenance("Hormigón en viga V1", takeoff)
    assert "ES 01 General Details.dwg" in out


def test_source_file_from_refs() -> None:
    takeoff = QuantityTakeoff(
        item_key="x",
        item_type="wall_length",
        unit="m",
        quantity=1.0,
        source_refs=["geometry:ABC", "file:Plano.dwg"],
    )
    assert source_file_from_takeoff(takeoff) == "Plano.dwg"
