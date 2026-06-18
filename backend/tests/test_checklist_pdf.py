"""Tests for GA-FO-08 checklist PDF generation."""

from __future__ import annotations

import uuid

from app.models.project_clash_item import ProjectClashItem
from app.services.clash_export_service import build_export_filename
from app.services.clash_reports.checklist_pdf import build_checklist_pdf, build_checklist_pdf_from_items


def _sample_incidents() -> list[dict]:
    return [
        {
            "incident_id": "incident_0001",
            "file_pair": ["PLANOS ARQ.-LAS NASAS 09-20260320.dwg", "20.03.2026 LAS NASAS 09 ES-05.dwg"],
            "level_id": "P1",
            "representative_conflict": {
                "discipline_a": "ARQUITECTURA",
                "discipline_b": "ESTRUCTURA",
                "raw_layers": ["ARQ_MURO", "EST_COL"],
            },
            "plan_centroid_mm": [150000.0, -160000.0],
            "plan_bounds_mm": [148000.0, -163000.0, 158000.0, -154000.0],
        },
        {
            "incident_id": "incident_0002",
            "file_pair": ["15.04.2026 LAS NASAS 09 HS-AGUA POTABLE.dwg", "PLANOS ARQ.-LAS NASAS 09-20260320.dwg"],
            "level_id": "P1",
            "representative_conflict": {
                "discipline_a": "PLOMERIA",
                "discipline_b": "ARQUITECTURA",
                "raw_layers": ["HS_TUB", "ARQ_SLAB"],
            },
            "plan_centroid_mm": [151000.0, -159000.0],
            "plan_bounds_mm": [149000.0, -161000.0, 157000.0, -155000.0],
        },
    ]


def _pdf_text(pdf: bytes) -> str:
    try:
        from io import BytesIO
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(pdf))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return pdf.decode("latin-1", errors="ignore")


def test_build_checklist_pdf_from_incidents():
    pdf = build_checklist_pdf(
        incidents=_sample_incidents(),
        project_name="LAS NASAS 09",
        reviewer_name="Revisión Técnica",
        folder_name="LAS NASAS 09",
    )
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 2000
    text = _pdf_text(pdf)
    assert "GESTIÓN DE ARQUITECTURA" in text or "GESTI" in text
    assert "GA-FO-08" in text
    assert "LISTA DE CHEQUEO" in text
    assert "OBSERVACIONES" in text


def test_build_checklist_pdf_from_items():
    items = [
        ProjectClashItem(
            id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            clash_code="incident_0001",
            priority="P2",
            severity="medium",
            dwg_a="PLANOS ARQ.-LAS NASAS 09-20260320.dwg",
            dwg_b="20.03.2026 LAS NASAS 09 ES-05.dwg",
            level_id="P1",
            discipline_a="ARQUITECTURA",
            discipline_b="ESTRUCTURA",
            recommended_action="Verificar solape en muro de carga.",
            centroid_x_mm=150000.0,
            centroid_y_mm=-160000.0,
            bounds_minx_mm=148000.0,
            bounds_miny_mm=-163000.0,
            bounds_maxx_mm=158000.0,
            bounds_maxy_mm=-154000.0,
        )
    ]
    meta = {
        "project_name": "LAS NASAS 09",
        "folder_name": "LAS NASAS 09",
        "user_display": "QA Dupla",
        "run_date": "2026-06-17",
    }
    pdf = build_checklist_pdf_from_items(items=items, meta=meta)
    assert pdf[:4] == b"%PDF"
    assert "GA-FO-08" in _pdf_text(pdf)


def test_final_human_filename_ga_fo08_format():
    meta = {
        "folder_name": "LAS NASAS 09",
        "project_name": "LAS NASAS 09",
        "user_display": "QA",
        "run_date": "2026-06-17",
        "run_sequence": 1,
    }
    name = build_export_filename("final_human", meta, revision=2)
    assert "LAS NASAS 09" in name
    assert "COORDINACION" in name
    assert "REV.02" in name
    assert name.endswith(".pdf")
