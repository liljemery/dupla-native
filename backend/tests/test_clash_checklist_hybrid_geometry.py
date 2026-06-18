"""Tests for checklist plan-geometry source selection."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.clash_reports import checklist_pdf


def test_checklist_pdf_prefers_hybrid_plan_geometry(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "job"
    hybrid_dir = output_dir / "hybrid_geometry"
    hybrid_dir.mkdir(parents=True)
    (output_dir / "plan_geometry.json").write_text(
        json.dumps({"files": {"ARQ.dwg": {"element_count": 1, "elements": []}}}),
        encoding="utf-8",
    )
    (hybrid_dir / "plan_geometry.hybrid.json").write_text(
        json.dumps({"files": {"ARQ.dwg": {"element_count": 7, "elements": []}}}),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_render_entry_plan(entry, plan_geometry, clash_zones_by_file):
        captured["plan_geometry"] = plan_geometry
        entry.plan_bytes = b"plan"

    monkeypatch.setattr(checklist_pdf, "_render_entry_plan", fake_render_entry_plan)
    monkeypatch.setattr(checklist_pdf, "_build_annex_flowables", lambda entries, plan_w, plan_h: [])
    monkeypatch.setattr(checklist_pdf.BaseDocTemplate, "build", lambda self, story, canvasmaker=None: None)

    checklist_pdf.build_checklist_pdf(
        incidents=[
            {
                "incident_id": "incident_1",
                "file_pair": ["ARQ.dwg", "EST.dwg"],
                "representative_conflict": {},
            }
        ],
        project_name="Demo",
        checklist_number="CHK-1",
        reviewer_name="QA",
        export_date="18.06.2026",
        logo_grupodupla_path=None,
        logo_constructora_path=None,
        aps_token=None,
        job_cache_dir=str(output_dir),
    )

    assert captured["plan_geometry"]["ARQ.dwg"]["element_count"] == 7
