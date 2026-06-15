"""Tests for clash report formatting helpers."""

from __future__ import annotations

from app.services.clash_reports.formatting import (
    FilenameAliasRegistry,
    compute_severity,
    format_optional,
    layers_from_incident,
    make_zoom_command,
)


def test_format_optional_never_shows_question_mark():
    assert format_optional(None) == "no disponible"
    assert format_optional("?") == "no disponible"
    assert format_optional(150, " mm") == "150 mm"


def test_make_zoom_command_from_bounds():
    cmd, fb = make_zoom_command([1000, 2000, 3000, 4000], padding_mm=500)
    assert cmd is not None
    assert cmd.startswith("Z W")
    assert fb is None


def test_make_zoom_command_fallback_without_geometry():
    cmd, fb = make_zoom_command(None, center=None)
    assert cmd is None
    assert fb is not None
    assert "Z E" in fb


def test_filename_alias_shortens_long_names():
    reg = FilenameAliasRegistry()
    alias = reg.alias_for(
        "PLANOS ARQ TORTUGA C-40 NOV 2025.dwg",
        discipline="ARQUITECTURA",
    )
    assert alias.startswith("ARQ_")
    assert len(alias) < 30


def test_layers_from_source_refs():
    inc = {
        "representative_conflict": {
            "source_refs": [
                "path/a.dwg|SOLAR|Polyline|ABC",
                "path/b.dwg|VIGA|Line|DEF",
            ]
        }
    }
    la, lb = layers_from_incident(inc)
    assert la == "SOLAR"
    assert lb == "VIGA"


def test_severity_rule_thresholds():
    assert compute_severity(area_mm2=300_000, z_depth_mm=10) == "Alta"
    assert compute_severity(area_mm2=10_000, z_depth_mm=80) == "Media"
    assert compute_severity(area_mm2=1_000, z_depth_mm=10) == "Baja"
