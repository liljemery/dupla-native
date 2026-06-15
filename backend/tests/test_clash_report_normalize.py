"""Tests for clash incident normalization and fallback chains."""

from __future__ import annotations

import json

from app.services.clash_reports.data import build_report_bundle
from app.services.clash_reports.normalize import (
    merge_enriched_cards,
    normalize_incident_for_reports,
    parse_revision_md_incidents,
)


def test_normalize_layers_from_enriched_layer_pair():
    raw = {"incident_id": "incident_0001", "file_pair": ["a.dwg", "b.dwg"]}
    enriched = {"layer_pair": "SOLAR / SOLAR", "disciplines": ["ARQUITECTURA", "ESTRUCTURA"]}
    norm = normalize_incident_for_reports(
        raw=raw,
        human_code="T-A1",
        group_code="T-A",
        enriched=enriched,
    )
    assert norm.layer_a == "SOLAR"
    assert norm.layer_b == "SOLAR"
    assert norm.provenance.layers_source == "coordination_context.layer_pair"


def test_normalize_layers_from_enriched_layers_list():
    raw = {"incident_id": "incident_0002", "file_pair": ["a.dwg", "b.dwg"]}
    enriched = {"layers": ["PLAFON", "SOLAR"]}
    norm = normalize_incident_for_reports(
        raw=raw,
        human_code="T-B1",
        group_code="T-B",
        enriched=enriched,
    )
    assert norm.layer_a == "PLAFON"
    assert norm.layer_b == "SOLAR"


def test_normalize_center_and_bounds_from_context_short_strings():
    raw = {"incident_id": "incident_0021", "file_pair": ["a.dwg", "b.dwg"]}
    enriched = {
        "location_short": "NPT_P1; (168,817,815, 624,648,464) mm",
        "bounds_short": "168,816,581, 624,646,757, 168,819,049, 624,650,171",
        "layer_pair": "MARCO / EST_PROYECCION",
    }
    norm = normalize_incident_for_reports(
        raw=raw,
        human_code="S-A1",
        group_code="S-A",
        enriched=enriched,
    )
    assert norm.center == (168817815.0, 624648464.0)
    assert norm.provenance.center_source == "coordination_context.location_short"
    assert norm.bounds is not None
    assert norm.provenance.bounds_source == "coordination_context.bounds_short"
    assert norm.zoom_command is not None
    assert norm.zoom_command.startswith("Z W")


def test_parse_revision_md_incidents():
    md = """
### T-A1 — `incident_0001`

| **Capas** | `SOLAR` (ARQ) vs `SOLAR` (EST) |
| **Centro del clash** | X: 48,765 mm · Y: 35,327 mm |

```
Z W -3441,9684 103882,64404 145019,160819
```
"""
    parsed = parse_revision_md_incidents(md)
    assert "incident_0001" in parsed
    assert parsed["incident_0001"]["layer_a"] == "SOLAR"
    assert parsed["incident_0001"]["zoom_command"].startswith("Z W")


def test_build_report_bundle_uses_context_when_primary_sparse():
    primary = {
        "incidents": [
            {
                "incident_id": "incident_0001",
                "file_pair": ["arq.dwg", "est.dwg"],
                "level_id": "NPT_P1",
                "member_count": 1,
                "representative_conflict": {"plan_intersection_area_mm2": 1000},
            }
        ]
    }
    context = {
        "all_incidents": [
            {
                "incident_id": "incident_0001",
                "layer_pair": "SOLAR / SOLAR",
                "disciplines": ["ARQUITECTURA", "ESTRUCTURA"],
                "location_short": "NPT_P1; (48,765, 35,327) mm",
                "bounds_short": "43,765, 30,327, 53,765, 40,327",
            }
        ]
    }
    bundle = build_report_bundle(
        meta={"project_name": "TORTUGA C40", "folder_name": "TEST_01", "run_sequence": 1},
        artifacts={
            "primary_incidents": json.dumps(primary),
            "coordination_context": json.dumps(context),
        },
    )
    inc = bundle.incidents[0]
    assert inc.layer_a == "SOLAR"
    assert inc.layer_b == "SOLAR"
    assert inc.center_text != "no disponible"
    assert inc.zoom_command is not None
    assert inc.provenance.layers_source == "coordination_context.layer_pair"


def test_merge_enriched_cards_combines_sections():
    context = {
        "all_incidents": [{"incident_id": "a", "layer_pair": "X / Y"}],
        "defendable_incidents": [{"incident_id": "b", "layer_pair": "P / Q"}],
    }
    merged = merge_enriched_cards(context)
    assert merged["a"]["layer_pair"] == "X / Y"
    assert merged["b"]["layer_pair"] == "P / Q"
