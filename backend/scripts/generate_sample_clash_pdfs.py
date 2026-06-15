#!/usr/bin/env python3
"""Generate sample TEST_01 clash PDFs for manual inspection."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.clash_export_service import ClashExportService
from app.services.clash_reports.formatting import FilenameAliasRegistry


def _rich_sample_artifacts() -> dict:
    primary = {
        "project_name": "Tutorial · Workspace Dupla",
        "incident_count": 1,
        "incident_conflict_count": 2,
        "analysis_profile": "fast_compare",
        "incidents": [
            {
                "incident_id": "incident_0001",
                "file_pair": [
                    "PLANOS ARQ TORTUGA C-40 NOV 2025.dwg",
                    "PLANOS ESTRUCTURALES-TORTUGA C-40 2025-11-12.dwg",
                ],
                "level_id": "NPT_P1",
                "member_count": 2,
                "plan_centroid_mm": [148500, -158500],
                "plan_bounds_mm": [148000, -163000, 158000, -154000],
                "confidence": "high",
                "representative_conflict": {
                    "discipline_a": "ARQUITECTURA",
                    "discipline_b": "ESTRUCTURA",
                    "clash_type": "HARD",
                    "overlap_depth_z_mm": 220.0,
                    "plan_intersection_area_mm2": 85000.0,
                    "source_refs": [
                        "PLANOS ARQ TORTUGA C-40 NOV 2025.dwg|SOLAR|Polyline|3F6B08",
                        "PLANOS ESTRUCTURALES-TORTUGA C-40 2025-11-12.dwg|EST_VIGA|Line|30A5BD",
                    ],
                },
            }
        ],
    }
    context = {
        "counts": {
            "scheduled_pairs": 1,
            "scheduled_files": 2,
            "primary_incidents": 1,
            "primary_members": 2,
        },
        "analysis_profile": "fast_compare",
    }
    return {
        "primary_incidents": json.dumps(primary),
        "coordination_context": json.dumps(context),
        "pair_schedule": json.dumps(
            {
                "pairs": [
                    {
                        "file_a": "PLANOS ARQ TORTUGA C-40 NOV 2025.dwg",
                        "file_b": "PLANOS ESTRUCTURALES-TORTUGA C-40 2025-11-12.dwg",
                        "scheduled": True,
                        "discipline_a": "ARQUITECTURA",
                        "discipline_b": "ESTRUCTURA",
                        "level_id": "NPT_P1",
                    }
                ]
            }
        ),
        "analyzed_documents": [
            {"original_name": "PLANOS ARQ TORTUGA C-40 NOV 2025.dwg", "discipline_bucket": "arquitectura"},
            {"original_name": "PLANOS ESTRUCTURALES-TORTUGA C-40 2025-11-12.dwg", "discipline_bucket": "estructura"},
        ],
        "output_dir": "/tmp/test_01_clash_output",
    }


def main() -> None:
    meta = {
        "project_name": "Tutorial · Workspace Dupla",
        "folder_name": "TEST_01",
        "user_display": "Carlos Ruiz",
        "run_date": "2026-05-23",
        "run_sequence": 1,
    }
    artifacts = _rich_sample_artifacts()
    svc = ClashExportService(session=None)  # type: ignore[arg-type]
    out = Path(__file__).resolve().parents[1] / "var" / "sample_pdfs"
    out.mkdir(parents=True, exist_ok=True)
    human = svc.build_clash_human_pdf(meta=meta, artifacts=artifacts)
    tech = svc.build_clash_technical_pdf(meta=meta, artifacts=artifacts)
    (out / "TEST_01_human.pdf").write_bytes(human)
    (out / "TEST_01_technical.pdf").write_bytes(tech)
    print(f"Wrote {out / 'TEST_01_human.pdf'}")
    print(f"Wrote {out / 'TEST_01_technical.pdf'}")


if __name__ == "__main__":
    main()
