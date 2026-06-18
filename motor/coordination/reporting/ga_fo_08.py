"""GA-FO-08 (04.2025) V.01 — Lista de Chequeo de Planos (formato Dupla).

Pixel-faithful port of the canonical Dupla checklist form: letter-landscape,
floating GRUPODUPLA logo + centered titles, meta rows (PROYECTO / FECHA /
No. LISTA / REVISADO POR), 8-column table with per-file observation bullets,
two-pass "Página N de M" footer, and full-bleed plan annex pages.

This module is presentational: it receives already-built rows (``Entry``) and
pre-rendered annex image paths. It does not know about clash detection, APS, or
geometry — callers shape the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.doctemplate import LayoutError

# ── Exact page geometry (points, letter landscape) ──────────────────────────
PAGE_W = 792.0
PAGE_H = 612.0
TABLE_X0 = 38.6
TABLE_Y_TOP = 105.6
TABLE_W = 714.7
FOOTER_Y_FROM_BOTTOM = 22.1
COL_WIDTHS = [70.2, 69.6, 69.6, 126.1, 47.4, 47.4, 89.9, 194.5]  # sum = 714.7

GRAY_FILL = colors.Color(0.749, 0.749, 0.749)
BLACK = colors.black

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
TITLE_SIZE = 9.6
TABLE_SIZE = 6.6
FOOTER_SIZE = 6.0

CENTER_TITLE_1 = "PROCESO: GESTIÓN DE ARQUITECTURA Y CONTROL DE PLANOS"
CENTER_TITLE_2 = "LISTA DE CHEQUEO - PLANOS"
FOOTER_LEFT = "Este documento es confidencial"
FOOTER_CENTER = "GA-FO-08 (04.2025) V.01"

COLUMN_HEADERS = [
    "DISCIPLINA",
    "NÚMERO DE PLANO",
    "TÍTULO DEL PLANO",
    "DESCRIPCIÓN DE PLANOS Y/O\nCAMBIOS",
    "FECHA DEL\nPLANO",
    "REVISIÓN",
    "CORRELACIÓN CON\nDEMÁS DISCIPLINAS",
    "OBSERVACIONES",
]

_NA = "—"


@dataclass
class Entry:
    discipline: str = _NA
    numero_plano: str = _NA
    titulo: str = _NA
    descripcion: str = _NA
    fecha: str = _NA
    revision: str = _NA
    correlacion: list[str] = field(default_factory=list)
    observation_lines: list[str] = field(default_factory=list)
    annex_labels: list[str] = field(default_factory=list)


def _cell_style(align: str = "CENTER", bold: bool = False) -> ParagraphStyle:
    return ParagraphStyle(
        f"chk_{align}_{bold}",
        fontName=FONT_BOLD if bold else FONT,
        fontSize=TABLE_SIZE,
        leading=TABLE_SIZE + 1.6,
        alignment=TA_CENTER if align == "CENTER" else TA_LEFT,
        wordWrap="LTR",
    )


def _esc(text: Any) -> str:
    s = str(text if text is not None else "")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_observation_cell(entry: Entry) -> list:
    obs_style = _cell_style("LEFT")
    cell: list = []
    for line in entry.observation_lines or [_NA]:
        cell.append(Paragraph(_esc(line), obs_style))
    if entry.annex_labels:
        cell.append(Spacer(1, 3))
        ref_style = _cell_style("LEFT", bold=True)
        ref = entry.annex_labels[0] if len(entry.annex_labels) == 1 \
            else f"{entry.annex_labels[0]} a {entry.annex_labels[-1]}"
        cell.append(Paragraph(f"Ver Anexo {ref} (plano).", ref_style))
    return cell


class _PageDrawer:
    """Floating logos + centered titles on every form page."""

    def __init__(self, logo_left: str | None, logo_right: str | None) -> None:
        self.logo_left = logo_left if logo_left and Path(logo_left).is_file() else None
        self.logo_right = logo_right if logo_right and Path(logo_right).is_file() else None

    def __call__(self, cnv: canvas.Canvas, doc) -> None:
        cnv.saveState()
        if self.logo_left:
            cnv.drawImage(
                self.logo_left, 14.2, PAGE_H - 8.5 - 51.0, width=110.3, height=51.0,
                preserveAspectRatio=True, mask="auto",
            )
        if self.logo_right:
            cnv.drawImage(
                self.logo_right, 667.2, PAGE_H - 26.4 - 33.1, width=110.6, height=33.1,
                preserveAspectRatio=True, mask="auto",
            )
        cnv.setFont(FONT_BOLD, TITLE_SIZE)
        cnv.drawCentredString(396, PAGE_H - 26, CENTER_TITLE_1)
        cnv.drawCentredString(396, PAGE_H - 50, CENTER_TITLE_2)
        cnv.restoreState()


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas that stamps 'Página N de M'."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._saved_states: list[dict] = []

    def showPage(self) -> None:
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int) -> None:
        self.saveState()
        self.setFont(FONT, FOOTER_SIZE)
        y = FOOTER_Y_FROM_BOTTOM
        self.drawString(15.2, y, FOOTER_LEFT)
        self.drawCentredString(PAGE_W / 2, y, FOOTER_CENTER)
        self.drawRightString(PAGE_W - 38.7, y, f"Página {self._pageNumber} de {total}")
        self.restoreState()


def _build_table(
    entries: list[Entry],
    *,
    project_name: str,
    checklist_number: str,
    fecha: str,
    reviewer: str,
    merge_disciplines: bool = True,
) -> Table:
    label = _cell_style("CENTER", bold=True)
    value = _cell_style("CENTER")
    header = _cell_style("CENTER", bold=True)

    data: list[list[Any]] = []
    data.append([
        Paragraph("PROYECTO:", label), "", "",
        Paragraph(_esc(project_name), value),
        Paragraph("No. LISTA DE CHEQUEO:", label), "",
        Paragraph(_esc(checklist_number), value), "",
    ])
    data.append([
        Paragraph("FECHA:", label), "", "",
        Paragraph(_esc(fecha), value),
        Paragraph("REVISADO POR:", label), "",
        Paragraph(_esc(reviewer), value), "",
    ])
    data.append([Paragraph(_esc(h).replace("\n", "<br/>"), header) for h in COLUMN_HEADERS])

    discipline_runs: list[tuple[int, int]] = []
    run_start = 3
    prev_disc: str | None = None
    for idx, entry in enumerate(entries):
        row_idx = 3 + idx
        correlacion = "\n".join(sorted(set(entry.correlacion))) or _NA
        data.append([
            Paragraph(_esc(entry.discipline), value),
            Paragraph(_esc(entry.numero_plano), value),
            Paragraph(_esc(entry.titulo), value),
            Paragraph(_esc(entry.descripcion), value),
            Paragraph(_esc(entry.fecha), value),
            Paragraph(_esc(entry.revision), value),
            Paragraph(_esc(correlacion).replace("\n", "<br/>"), value),
            _build_observation_cell(entry),
        ])
        if entry.discipline != prev_disc:
            if prev_disc is not None:
                discipline_runs.append((run_start, row_idx - 1))
            run_start = row_idx
            prev_disc = entry.discipline
    if entries:
        discipline_runs.append((run_start, 3 + len(entries) - 1))
    else:
        data.append([Paragraph("Sin incidencias en esta corrida.", value)] + [""] * 7)

    style_cmds: list[tuple] = [
        ("SPAN", (0, 0), (2, 0)), ("SPAN", (4, 0), (5, 0)), ("SPAN", (6, 0), (7, 0)),
        ("SPAN", (0, 1), (2, 1)), ("SPAN", (4, 1), (5, 1)), ("SPAN", (6, 1), (7, 1)),
        ("BACKGROUND", (0, 0), (2, 0), GRAY_FILL),
        ("BACKGROUND", (4, 0), (5, 0), GRAY_FILL),
        ("BACKGROUND", (0, 1), (2, 1), GRAY_FILL),
        ("BACKGROUND", (4, 1), (5, 1), GRAY_FILL),
        ("BACKGROUND", (0, 2), (-1, 2), GRAY_FILL),
        ("GRID", (0, 0), (-1, -1), 0.5, BLACK),
        ("LINEBELOW", (0, 2), (-1, 2), 1.0, BLACK),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), TABLE_SIZE),
        ("FONTNAME", (0, 2), (-1, 2), FONT_BOLD),
        ("FONTNAME", (0, 0), (2, 1), FONT_BOLD),
        ("FONTNAME", (4, 0), (5, 1), FONT_BOLD),
        ("ALIGN", (0, 0), (-1, 2), "CENTER"),
        ("ALIGN", (0, 3), (6, -1), "CENTER"),
        ("ALIGN", (7, 3), (7, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("VALIGN", (0, 0), (-1, 2), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    if merge_disciplines:
        for start, end in discipline_runs:
            if end > start:
                style_cmds.append(("SPAN", (0, start), (0, end)))
                style_cmds.append(("VALIGN", (0, start), (0, end), "MIDDLE"))

    table = Table(data, colWidths=COL_WIDTHS, repeatRows=3, splitByRow=1)
    table.setStyle(TableStyle(style_cmds))
    return table


def _draw_plan_legend_factory(left_text: str):
    def _draw(cnv: canvas.Canvas, doc) -> None:
        cnv.saveState()
        cnv.setFillColor(colors.HexColor("#1A1A1A"))
        cnv.rect(0, 0, PAGE_W, 22, fill=1, stroke=0)
        cnv.setFillColor(colors.white)
        cnv.setFont(FONT_BOLD, 7)
        cnv.drawString(10, 7, left_text)
        cnv.setFont(FONT, 7)
        cnv.drawRightString(PAGE_W - 10, 7, "GrupoDupla / Dupla Constructora")
        cnv.restoreState()
    return _draw


def _scaled_image(img_path: str, max_w: float, max_h: float):
    from PIL import Image as PILImage

    if not Path(img_path).is_file():
        return None
    with PILImage.open(img_path) as im:
        iw, ih = im.size
    if iw <= 0 or ih <= 0:
        return None
    # Images are pre-sized to annex aspect; scale to fill the frame exactly.
    scale = min(max_w / iw, max_h / ih)
    img = Image(img_path, width=iw * scale, height=ih * scale)
    img.hAlign = "CENTER"
    img.vAlign = "MIDDLE"
    return img


def _default_checklist_number(project_name: str) -> str:
    import re

    slug = re.sub(r"[^A-Za-z0-9]+", "", project_name).upper()[:4] or "PROJ"
    return f"LDC-{slug}-01"


def build_checklist_pdf(
    *,
    entries: list[Entry],
    project_name: str,
    out_path: str,
    checklist_number: str | None = None,
    reviewer_name: str = _NA,
    export_date: str | None = None,
    logo_left_path: str | None = None,
    logo_right_path: str | None = None,
    annex_pages: list[tuple[str, str]] | None = None,
) -> str:
    """Build the GA-FO-08 checklist PDF. annex_pages = [(legend_left, image_path)]."""
    checklist_number = checklist_number or _default_checklist_number(project_name)
    export_date = export_date or date.today().strftime("%d.%m.%Y")
    annex_pages = annex_pages or []

    frame_bottom = FOOTER_Y_FROM_BOTTOM + 5
    frame_top = PAGE_H - TABLE_Y_TOP
    frame_height = frame_top - frame_bottom
    plan_margin = 10.0
    plan_frame_bottom = FOOTER_Y_FROM_BOTTOM + 4
    plan_frame_top = PAGE_H - plan_margin
    plan_w = PAGE_W - 2 * plan_margin
    plan_h = plan_frame_top - plan_frame_bottom
    drawer = _PageDrawer(logo_left_path, logo_right_path)

    def _render(merge_disciplines: bool) -> None:
        table = _build_table(
            entries, project_name=project_name, checklist_number=checklist_number,
            fecha=export_date, reviewer=reviewer_name or _NA,
            merge_disciplines=merge_disciplines,
        )
        frame = Frame(TABLE_X0, frame_bottom, TABLE_W, frame_height,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="main")
        main_tpl = PageTemplate(id="main", frames=[frame], onPage=drawer, pagesize=(PAGE_W, PAGE_H))

        # One plan template per annex page so each carries its own bottom legend.
        templates = [main_tpl]
        story: list = [table]
        for i, (legend_left, img_path) in enumerate(annex_pages):
            img = _scaled_image(img_path, plan_w, plan_h)
            if img is None:
                continue
            tpl_id = f"plan_{i}"
            plan_frame = Frame(plan_margin, plan_frame_bottom, plan_w, plan_h,
                               leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="plan")
            templates.append(PageTemplate(id=tpl_id, frames=[plan_frame],
                                          onPage=_draw_plan_legend_factory(legend_left),
                                          pagesize=(PAGE_W, PAGE_H)))
            story.append(NextPageTemplate(tpl_id))
            story.append(PageBreak())
            story.append(img)

        doc = BaseDocTemplate(
            out_path, pagesize=(PAGE_W, PAGE_H), pageTemplates=templates,
            leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0,
            title="Lista de Chequeo de Planos",
        )
        doc.build(story, canvasmaker=NumberedCanvas)

    try:
        _render(merge_disciplines=True)
    except LayoutError:
        _render(merge_disciplines=False)
    return out_path
