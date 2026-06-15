"""Final clash PDF appendix with reviewer decisions."""

from __future__ import annotations

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Spacer

from app.domain.clash_workflow_enums import ClashStatus, ReviewerDecision, decision_label, status_label
from app.models.project_clash_item import ProjectClashItem
from app.services.clash_reports.human_pdf import build_human_pdf
from app.services.clash_reports.pdf_base import P, build_pdf, data_table, section
from app.services.clash_reports.technical_pdf import build_technical_pdf
from app.services.clash_reports.data import ReportBundle

_PAGE_W = A4[0] - 36 * mm


def _decisions_appendix(items: list[ProjectClashItem]) -> list:
    rows = [["Código", "Estado", "Decisión", "DWG A", "DWG B", "Responsable", "Observación"]]
    for item in items:
        try:
            st = status_label(ClashStatus(item.status))
        except ValueError:
            st = item.status or "—"
        dec = "Sin decisión (valor inicial)"
        if item.reviewer_decision:
            try:
                dec = decision_label(ReviewerDecision(item.reviewer_decision))
            except ValueError:
                dec = item.reviewer_decision
        rows.append(
            [
                item.clash_code,
                st,
                dec,
                item.dwg_a or "—",
                item.dwg_b or "—",
                item.assigned_to or "—",
                (item.observation or "—")[:120],
            ]
        )
    headers = rows[0]
    body = rows[1:]
    return [
        *section("Decisiones del revisor (informe final)"),
        P(
            "Este anexo congela el estado actual de cada clash, incluyendo decisiones "
            "registradas o el valor por defecto detectado por el motor."
        ),
        Spacer(1, 6),
        data_table(
            headers,
            body,
            col_widths=[22 * mm, 24 * mm, 32 * mm, 28 * mm, 28 * mm, 22 * mm, 38 * mm],
        ),
    ]


def build_final_technical_pdf(bundle: ReportBundle, items: list[ProjectClashItem]) -> bytes:
    base = build_technical_pdf(bundle)
    appendix_flow = _decisions_appendix(items)
    appendix_pdf = build_pdf(
        appendix_flow,
        title="Decisiones — informe técnico final",
        meta_line="Dupla — anexo de decisiones",
    )
    return _merge_pdfs(base, appendix_pdf)


def build_final_human_pdf(bundle: ReportBundle, items: list[ProjectClashItem]) -> bytes:
    base = build_human_pdf(bundle)
    appendix_flow = _decisions_appendix(items)
    appendix_pdf = build_pdf(
        appendix_flow,
        title="Decisiones — informe final",
        meta_line="Dupla — anexo de decisiones",
    )
    return _merge_pdfs(base, appendix_pdf)


def _merge_pdfs(first: bytes, second: bytes) -> bytes:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return first

    writer = PdfWriter()
    for data in (first, second):
        reader = PdfReader(__import__("io").BytesIO(data))
        for page in reader.pages:
            writer.add_page(page)
    out = __import__("io").BytesIO()
    writer.write(out)
    return out.getvalue()
