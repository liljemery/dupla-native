"""Report mapper contract tests."""

from __future__ import annotations

import sys
from pathlib import Path

COORD_ROOT = Path(__file__).resolve().parents[1]
if str(COORD_ROOT) not in sys.path:
    sys.path.insert(0, str(COORD_ROOT))

from adapters.report_mapper import map_to_structural_analysis_report


def test_report_mapper_uses_incident_description_and_disciplines() -> None:
    report = map_to_structural_analysis_report(
        run_status="completed",
        project_name="Demo",
        profile_slug="folder",
        primary_incidents={
            "incident_count": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "incidents": [
                {
                    "incident_id": "incident_0001",
                    "priority": "critical",
                    "level_id": "P1",
                    "description": "Descripción explícita del incidente.",
                    "disciplines": ["ESTRUCTURA", "FONTANERIA"],
                    "representative_conflict": {
                        "clash_type": "HARD",
                        "overlap_depth_z_mm": 250,
                        "plan_intersection_area_mm2": 1_500_000,
                        "confidence": "high",
                        "geometry_sources": ["dwg_aps_viewer_2d", "dwg_aps_viewer_2d"],
                    },
                }
            ],
        },
        coordination_context=None,
        analyzed_documents=[
            {
                "id": "doc-1",
                "file_name": "a.dwg",
                "discipline_label": "Estructura",
                "status": "ok",
                "element_count": 10,
                "retryable": False,
            }
        ],
        analysis_mode="real",
    )

    assert report["analysis_mode"] == "real"
    assert report["clashes"][0]["description"] == "Descripción explícita del incidente."
    assert report["clashes"][0]["disciplines"] == ["Estructura", "Plomería"]
    assert report["clashes"][0]["priority"] == "critical"
    assert report["clashes"][0]["confidence"] == "high"
    assert report["clashes"][0]["geometry_sources"] == "dwg_aps_viewer_2d / dwg_aps_viewer_2d"
    assert report["summary"]["total_clashes"] == 1
    assert report["geometry_audit"] is None


def test_report_mapper_exposes_geometry_audit_from_context() -> None:
    report = map_to_structural_analysis_report(
        run_status="completed",
        project_name="Demo",
        profile_slug="folder",
        primary_incidents={"incident_count": 0, "incidents": []},
        coordination_context={
            "hybrid_geometry": {
                "audit": {
                    "status": "warn",
                    "summary": {"views_warn": 2, "issues_warn": 3},
                }
            },
            "hybrid_geometry_audit_gate": {
                "mode": "report_only",
                "status": "warn",
                "blocked": False,
            },
        },
        analyzed_documents=[],
        analysis_mode="real",
    )

    assert report["geometry_audit"] == {
        "status": "warn",
        "summary": {"views_warn": 2, "issues_warn": 3},
        "gate": {"mode": "report_only", "status": "warn", "blocked": False},
    }
