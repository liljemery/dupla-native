"""GA-FO-08 (04.2025) V.01 — Lista de Chequeo de Planos.

Pixel-faithful replica built from the reverse-engineered reference geometry.
The whole document is ONE unified Table (meta rows + column headers + data rows)
rendered on letter-landscape pages with a two-pass footer for "Página N de M".
"""

from __future__ import annotations

import io
import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib import colors
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

from app.services.clash_reports.clash_plan_images import get_plan_images_for_file
from app.services.clash_reports.plan_renderer import (
    load_clash_zones_by_file,
    load_plan_geometry,
    render_plan_image,
)

logger = logging.getLogger(__name__)
coord_logger = logging.getLogger("COORD")

# ── Exact page geometry (points, letter landscape) ──────────────────────────────
PAGE_W = 792.0
PAGE_H = 612.0
TABLE_X0 = 38.6
TABLE_Y_TOP = 105.6          # from PDF top
TABLE_W = 714.7
FOOTER_Y_FROM_BOTTOM = 22.1

COL_WIDTHS = [70.2, 69.6, 69.6, 126.1, 47.4, 47.4, 89.9, 194.5]  # sum = 714.7

# ── Exact colors ────────────────────────────────────────────────────────────────
GRAY_FILL = colors.Color(0.749, 0.749, 0.749)
BLACK = colors.black

# ── Fonts (never above 9.6pt) ────────────────────────────────────────────────────
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

# ── Extraction regexes (per spec) ────────────────────────────────────────────────
RE_DRAWING_CODE = re.compile(r"\b([A-Z]{1,5}[-–]\d{1,3}[A-Z]?)\b", re.IGNORECASE)
RE_DATE = re.compile(r"\b(\d{2}[.\-/]\d{2}[.\-/]\d{4}|\d{4}[.\-/]\d{2}[.\-/]\d{2})\b")
RE_REVISION = re.compile(r"\b(REV?\.?\s*\d+|RV\s*\d+|R\d{1,2})\b", re.IGNORECASE)

_NA = "—"

_DISCIPLINE_DISPLAY = {
    "ARQUITECTURA": "ARQUITECTURA",
    "ESTRUCTURA": "ESTRUCTURA",
    "ESTRUCTURAL": "ESTRUCTURA",
    "ELECTRICIDAD": "ELÉCTRICA",
    "ELECTRICA": "ELÉCTRICA",
    "ELECTRICO": "ELÉCTRICA",
    "CLIMATIZACION": "CLIMATIZACIÓN",
    "MECANICA": "CLIMATIZACIÓN",
    "SANITARIO": "SANITARIOS",
    "SANITARIOS": "SANITARIOS",
    "PLOMERIA": "SANITARIOS",
    "FONTANERIA": "SANITARIOS",
}


def normalize_discipline(raw: str | None) -> str:
    if not raw:
        return _NA
    key = str(raw).strip().upper()
    return _DISCIPLINE_DISPLAY.get(key, key)


# ── Cell paragraph styles ─────────────────────────────────────────────────────────
def _cell_style(align: str = "CENTER", bold: bool = False) -> ParagraphStyle:
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

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


# ── Per-file aggregation ──────────────────────────────────────────────────────────
@dataclass
class ObsEntry:
    incident: dict[str, Any]
    bullets: str


@dataclass
class FileEntry:
    filename: str
    discipline: str = _NA
    numero_plano: str = _NA
    titulo: str = _NA
    descripcion: str = _NA
    fecha: str = _NA
    revision: str = _NA
    correlacion_set: set = field(default_factory=set)
    observations: list[ObsEntry] = field(default_factory=list)
    plan_bytes: bytes | None = None
    plan_image_paths: list[str] = field(default_factory=list)
    annex_no: int | None = None
    annex_labels: list[str] = field(default_factory=list)

    @property
    def clash_count(self) -> int:
        return len(self.observations)


def _basename(path: Any) -> str:
    return Path(str(path or "")).name


def _strip_tokens(stem: str) -> str:
    cleaned = RE_DATE.sub("", stem)
    cleaned = RE_REVISION.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -_.")
    return cleaned or stem


def observation_bullets(inc: dict[str, Any], discipline_display: str) -> str:
    lines = ["El plano presenta las siguientes observaciones:"]

    disciplines = [normalize_discipline(d) for d in (inc.get("disciplines") or [])]
    counterpart = [d for d in disciplines if d != discipline_display]
    if counterpart:
        lines.append(f"- Clash HARD con {counterpart[0]}.")

    area_mm2 = inc.get("max_area_mm2") or 0
    if area_mm2 and area_mm2 > 0:
        lines.append(f"- Área de intersección: {area_mm2 / 1_000_000:.2f} m².")

    z = inc.get("max_overlap_depth_z_mm") or 0
    if z and z > 0:
        lines.append(f"- Solapamiento vertical: {z:.0f} mm.")

    level = inc.get("level_id") or ""
    if level and level != "GENERAL":
        lines.append(f"- Nivel: {level}.")

    if inc.get("priority") == "critical":
        lines.append("- Prioridad CRÍTICA — resolver antes de construcción.")
    elif inc.get("priority") == "high":
        lines.append("- Prioridad ALTA — coordinar con disciplina.")

    bounds = (inc.get("representative_conflict") or {}).get("plan_intersection_bounds_mm")
    if isinstance(bounds, (list, tuple)) and len(bounds) == 4:
        try:
            lines.append(
                f"- AutoCAD ZOOM W {float(bounds[0]):.0f},{float(bounds[1]):.0f} "
                f"{float(bounds[2]):.0f},{float(bounds[3]):.0f}"
            )
        except (TypeError, ValueError):
            pass

    return "\n".join(lines)


def group_incidents_by_file(
    incidents: list[dict[str, Any]],
    file_discipline_hints: dict[str, str],
) -> dict[str, FileEntry]:
    """One FileEntry per DWG that participates in any clash."""
    entries: dict[str, FileEntry] = {}

    def _entry_for(fname: str) -> FileEntry:
        key = _basename(fname)
        if key not in entries:
            stem = Path(key).stem
            disc_hint = file_discipline_hints.get(key)
            code = RE_DRAWING_CODE.search(stem)
            date_m = RE_DATE.search(stem)
            rev_m = RE_REVISION.search(stem)
            entries[key] = FileEntry(
                filename=key,
                discipline=normalize_discipline(disc_hint) if disc_hint else _NA,
                numero_plano=code.group(1).upper() if code else _NA,
                titulo=_strip_tokens(stem),
                descripcion=_NA,
                fecha=date_m.group(1) if date_m else _NA,
                revision=rev_m.group(1).upper() if rev_m else _NA,
            )
        return entries[key]

    for inc in incidents:
        pair = inc.get("file_pair") or []
        if not isinstance(pair, (list, tuple)):
            continue
        disciplines = [normalize_discipline(d) for d in (inc.get("disciplines") or [])]
        for fname in pair:
            entry = _entry_for(str(fname))
            # Counterpart disciplines = those of the OTHER files in this incident.
            others = [str(o) for o in pair if _basename(str(o)) != entry.filename]
            for other in others:
                other_disc = file_discipline_hints.get(_basename(other))
                if other_disc:
                    entry.correlacion_set.add(normalize_discipline(other_disc))
            # Fallback: use the incident disciplines minus the file's own.
            if not entry.correlacion_set:
                for d in disciplines:
                    if d != entry.discipline:
                        entry.correlacion_set.add(d)
            entry.observations.append(
                ObsEntry(incident=inc, bullets=observation_bullets(inc, entry.discipline))
            )

    return entries


# ── High-res plan rendering (B2: from motor geometry) ──────────────────────────────
def _render_entry_plan(
    entry: FileEntry,
    plan_geometry: dict[str, Any],
    clash_zones_by_file: dict[str, list[dict[str, Any]]],
) -> None:
    """Render a full-page high-res plan (footprints + clash overlay) onto the entry."""
    geo = plan_geometry.get(entry.filename)
    zones = clash_zones_by_file.get(entry.filename) or []
    numero = entry.numero_plano if entry.numero_plano != _NA else "s/n"
    header = f"{entry.discipline} - {numero}   {entry.filename}"
    legend_left = f"Disciplina: {entry.discipline}    Clashes: {entry.clash_count}"
    if not geo and not zones:
        logger.warning("No geometry/zones to render plan for %s", entry.filename)
        return
    entry.plan_bytes = render_plan_image(
        file_geometry=geo or {},
        clash_zones=zones,
        header_text=header,
        legend_left=legend_left,
    )
    if not entry.plan_bytes:
        logger.warning("Could not render plan for %s", entry.filename)


def _entry_incidents_for_plan(
    entry: FileEntry,
    clash_zones_by_file: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    incidents = [obs.incident for obs in entry.observations]
    has_bounds = any(
        (inc.get("representative_conflict") or {}).get("plan_intersection_bounds_mm")
        for inc in incidents
    )
    if has_bounds:
        return incidents
    zones = clash_zones_by_file.get(entry.filename) or []
    return [
        {
            "priority": "critical" if str(zone.get("clash_type") or "").upper() == "HARD" else "high",
            "representative_conflict": {
                "plan_intersection_bounds_mm": zone.get("bounds_mm"),
                "plan_intersection_centroid_mm": zone.get("centroid_mm"),
            },
        }
        for zone in zones
    ] or incidents


def _render_entry_real_plan(
    entry: FileEntry,
    *,
    incidents_for_plan: list[dict[str, Any]],
    output_dir: Path,
    aps_token: str,
    plan_geometry: dict[str, Any],
) -> None:
    geo = plan_geometry.get(entry.filename) or {}
    elements = geo.get("elements") if isinstance(geo, dict) else None
    try:
        entry.plan_image_paths = asyncio.run(
            get_plan_images_for_file(
                filename=entry.filename,
                incidents_for_file=incidents_for_plan,
                job_output_dir=str(output_dir),
                aps_token=aps_token,
                elements_for_file=elements if isinstance(elements, list) else None,
            )
        )
    except RuntimeError:
        logger.warning("Could not start APS plan renderer for %s", entry.filename)


def _build_observation_cell(entry: FileEntry) -> list:
    """OBSERVACIONES cell: bullet text only, with a reference to the annex page."""
    cell: list = []
    obs_style = _cell_style("LEFT")

    bullets = "\n\n".join(o.bullets for o in entry.observations) or _NA
    for block in bullets.split("\n"):
        cell.append(Paragraph(_esc(block), obs_style))

    if entry.annex_labels:
        cell.append(Spacer(1, 3))
        ref_style = _cell_style("LEFT", bold=True)
        if len(entry.annex_labels) == 1:
            ref = entry.annex_labels[0]
        else:
            ref = f"{entry.annex_labels[0]} a {entry.annex_labels[-1]}"
        cell.append(Paragraph(f"Ver Anexo {ref} (plano).", ref_style))
    return cell


# ── Header + footer drawing ───────────────────────────────────────────────────────
class _PageDrawer:
    """Draws the floating logos + center titles on every page (no background)."""

    def __init__(self, logo_left: str | None, logo_right: str | None) -> None:
        self.logo_left = logo_left if logo_left and Path(logo_left).is_file() else None
        self.logo_right = logo_right if logo_right and Path(logo_right).is_file() else None

    def __call__(self, cnv: canvas.Canvas, doc) -> None:
        cnv.saveState()
        if self.logo_left:
            # PDF-top box x=14.2 y=8.5 w=110.3 h=51.0 → RL bottom-left
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
    """Two-pass canvas: collects page states, then stamps 'Página N de M'."""

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


# ── Table assembly ────────────────────────────────────────────────────────────────
def _build_table(
    entries: list[FileEntry],
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

    # Row 0 — PROYECTO / No. LISTA
    data.append([
        Paragraph("PROYECTO:", label), "", "",
        Paragraph(_esc(project_name), value),
        Paragraph("No. LISTA DE CHEQUEO:", label), "",
        Paragraph(_esc(checklist_number), value), "",
    ])
    # Row 1 — FECHA / REVISADO POR
    data.append([
        Paragraph("FECHA:", label), "", "",
        Paragraph(_esc(fecha), value),
        Paragraph("REVISADO POR:", label), "",
        Paragraph(_esc(reviewer), value), "",
    ])
    # Row 2 — column headers
    data.append([Paragraph(_esc(h).replace("\n", "<br/>"), header) for h in COLUMN_HEADERS])

    # Data rows (one per file)
    discipline_runs: list[tuple[int, int]] = []  # (start_row, end_row) for col-0 vertical spans
    run_start = 3
    prev_disc: str | None = None
    for idx, entry in enumerate(entries):
        row_idx = 3 + idx
        correlacion = "\n".join(sorted(entry.correlacion_set)) or _NA
        obs_cell = _build_observation_cell(entry)
        data.append([
            Paragraph(_esc(entry.discipline), value),
            Paragraph(_esc(entry.numero_plano), value),
            Paragraph(_esc(entry.titulo), value),
            Paragraph(_esc(entry.descripcion), value),
            Paragraph(_esc(entry.fecha), value),
            Paragraph(_esc(entry.revision), value),
            Paragraph(_esc(correlacion).replace("\n", "<br/>"), value),
            obs_cell,
        ])
        if entry.discipline != prev_disc:
            if prev_disc is not None:
                discipline_runs.append((run_start, row_idx - 1))
            run_start = row_idx
            prev_disc = entry.discipline
    if entries:
        discipline_runs.append((run_start, 3 + len(entries) - 1))

    if not entries:
        data.append([Paragraph("Sin incidencias primarias en esta corrida.", value)] + [""] * 7)

    style_cmds: list[tuple] = [
        # Meta spans
        ("SPAN", (0, 0), (2, 0)), ("SPAN", (4, 0), (5, 0)), ("SPAN", (6, 0), (7, 0)),
        ("SPAN", (0, 1), (2, 1)), ("SPAN", (4, 1), (5, 1)), ("SPAN", (6, 1), (7, 1)),
        # Meta gray fills (labels only)
        ("BACKGROUND", (0, 0), (2, 0), GRAY_FILL),
        ("BACKGROUND", (4, 0), (5, 0), GRAY_FILL),
        ("BACKGROUND", (0, 1), (2, 1), GRAY_FILL),
        ("BACKGROUND", (4, 1), (5, 1), GRAY_FILL),
        # Column header row — full gray
        ("BACKGROUND", (0, 2), (-1, 2), GRAY_FILL),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.5, BLACK),
        ("LINEBELOW", (0, 2), (-1, 2), 1.0, BLACK),
        # Fonts
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), TABLE_SIZE),
        ("FONTNAME", (0, 2), (-1, 2), FONT_BOLD),
        ("FONTNAME", (0, 0), (2, 1), FONT_BOLD),
        ("FONTNAME", (4, 0), (5, 1), FONT_BOLD),
        # Alignment
        ("ALIGN", (0, 0), (-1, 2), "CENTER"),
        ("ALIGN", (0, 3), (6, -1), "CENTER"),
        ("ALIGN", (7, 3), (7, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("VALIGN", (0, 0), (-1, 2), "MIDDLE"),
        # Padding
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]

    # Vertical discipline merges in col 0. Spanned rows cannot be split across
    # pages, so this is skipped on the fallback pass when a group is too tall.
    if merge_disciplines:
        for start, end in discipline_runs:
            if end > start:
                style_cmds.append(("SPAN", (0, start), (0, end)))
                style_cmds.append(("VALIGN", (0, start), (0, end), "MIDDLE"))

    table = Table(data, colWidths=COL_WIDTHS, repeatRows=3, splitByRow=1)
    table.setStyle(TableStyle(style_cmds))
    return table


def _default_checklist_number(project_name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "", project_name).upper()[:4] or "PROJ"
    return f"LDC-{slug}-01"


def _annex_caption_style(align_center: bool = True) -> ParagraphStyle:
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    return ParagraphStyle(
        "chk_annex_caption",
        fontName=FONT_BOLD,
        fontSize=TITLE_SIZE,
        leading=TITLE_SIZE + 2,
        alignment=TA_CENTER if align_center else TA_LEFT,
    )


def _draw_plan_legend(cnv: canvas.Canvas, doc) -> None:
    """Bottom legend strip for real plan pages."""
    cnv.saveState()
    cnv.setFillColor(colors.HexColor("#1A1A1A"))
    cnv.rect(0, 0, PAGE_W, 22, fill=1, stroke=0)
    cnv.setFillColor(colors.white)
    cnv.setFont(FONT_BOLD, 7)
    cnv.drawString(10, 7, "Plano de coordinación con zonas de clash")
    cnv.setFont(FONT, 7)
    cnv.drawString(580, 7, "GrupoDupla / Dupla Constructora")
    cnv.restoreState()


def _scaled_image(img_bytes: bytes, max_w: float, max_h: float):
    """Build a ReportLab Image scaled to fit the box, preserving aspect ratio."""
    from PIL import Image as PILImage

    with PILImage.open(io.BytesIO(img_bytes)) as im:
        iw, ih = im.size
    if iw <= 0 or ih <= 0:
        return None
    scale = min(max_w / iw, max_h / ih)
    return Image(io.BytesIO(img_bytes), width=iw * scale, height=ih * scale, kind="proportional")


def _scaled_image_path(img_path: str, max_w: float, max_h: float):
    from PIL import Image as PILImage

    if not Path(img_path).is_file():
        logger.warning("Skipping missing plan image: %s", img_path)
        return None
    with PILImage.open(img_path) as im:
        iw, ih = im.size
    if iw <= 0 or ih <= 0:
        return None
    scale = min(max_w / iw, max_h / ih)
    coord_logger.info(
        "COORD_PDF_IMAGE px=(%d,%d) frame=(%.1f,%.1f,%.1f,%.1f) scale=%.6f final_pt=(%.1f,%.1f)",
        iw,
        ih,
        10.0,
        FOOTER_Y_FROM_BOTTOM + 4,
        max_w,
        max_h,
        scale,
        iw * scale,
        ih * scale,
    )
    return Image(img_path, width=iw * scale, height=ih * scale, kind="proportional")


def _build_annex_flowables(entries: list[FileEntry], avail_w: float, avail_h: float) -> list:
    """Full-bleed plan pages (one per file). File/discipline/legend baked into image."""
    flowables: list = []
    for entry in entries:
        if entry.annex_no is None or (not entry.plan_image_paths and not entry.plan_bytes):
            continue
        image_paths = entry.plan_image_paths
        if image_paths:
            for img_path in image_paths:
                flowables.append(NextPageTemplate("plan_page"))
                flowables.append(PageBreak())
                plan_img = _scaled_image_path(img_path, avail_w, avail_h)
                if plan_img is not None:
                    plan_img.hAlign = "CENTER"
                    flowables.append(plan_img)
        elif entry.plan_bytes:
            flowables.append(NextPageTemplate("plan_page"))
            flowables.append(PageBreak())
            plan_img = _scaled_image(entry.plan_bytes, avail_w, avail_h)
            if plan_img is not None:
                plan_img.hAlign = "CENTER"
                flowables.append(plan_img)
    return flowables


def build_checklist_pdf(
    incidents: list[dict[str, Any]],
    project_name: str,
    checklist_number: str | None,
    reviewer_name: str,
    export_date: str | None,
    logo_grupodupla_path: str | None,
    logo_constructora_path: str | None,
    aps_token: str | None,
    job_cache_dir: str | None,
    *,
    file_discipline_hints: dict[str, str] | None = None,
    plan_geometry: dict[str, Any] | None = None,
) -> bytes:
    file_discipline_hints = file_discipline_hints or {}
    checklist_number = checklist_number or _default_checklist_number(project_name)
    export_date = export_date or date.today().strftime("%d.%m.%Y")

    # plan_geometry.json + clash_project_report.json live next to the job cache.
    output_dir = Path(job_cache_dir) if job_cache_dir else None
    if output_dir and output_dir.name == "cache":
        output_dir = output_dir.parent
    if plan_geometry is None and output_dir:
        hybrid_geometry_path = output_dir / "hybrid_geometry" / "plan_geometry.hybrid.json"
        plan_geometry = load_plan_geometry(hybrid_geometry_path)
        if not plan_geometry:
            plan_geometry = load_plan_geometry(output_dir / "plan_geometry.json")
    plan_geometry = plan_geometry or {}
    clash_zones_by_file = (
        load_clash_zones_by_file(output_dir / "clash_project_report.json") if output_dir else {}
    )

    entries_map = group_incidents_by_file(incidents, file_discipline_hints)
    # Sort by discipline (groups same-discipline rows for vertical merge), then file
    entries = sorted(entries_map.values(), key=lambda e: (e.discipline, e.filename))

    # Render a high-res plan per file (single pass), then number annexes
    # contiguously over the files that actually produced a plan.
    annex_counter = 0
    for entry in entries:
        incidents_for_plan = _entry_incidents_for_plan(entry, clash_zones_by_file)
        if aps_token and output_dir:
            _render_entry_real_plan(
                entry,
                incidents_for_plan=incidents_for_plan,
                output_dir=output_dir,
                aps_token=aps_token,
                plan_geometry=plan_geometry,
            )
        if not entry.plan_image_paths and not aps_token:
            _render_entry_plan(entry, plan_geometry, clash_zones_by_file)
        page_count = len(entry.plan_image_paths) if entry.plan_image_paths else (1 if entry.plan_bytes else 0)
        if page_count:
            annex_counter += 1
            entry.annex_no = annex_counter
            entry.annex_labels = [
                f"{annex_counter}-{chr(ord('A') + idx)}" for idx in range(page_count)
            ]

    frame_bottom = FOOTER_Y_FROM_BOTTOM + 5
    frame_top = PAGE_H - TABLE_Y_TOP
    frame_height = frame_top - frame_bottom
    # Full-bleed plan page geometry (small margin, above footer).
    plan_margin = 10.0
    plan_frame_bottom = FOOTER_Y_FROM_BOTTOM + 4
    plan_frame_top = PAGE_H - plan_margin
    drawer = _PageDrawer(logo_grupodupla_path, logo_constructora_path)

    def _render(merge_disciplines: bool) -> bytes:
        table = _build_table(
            entries,
            project_name=project_name,
            checklist_number=checklist_number,
            fecha=export_date,
            reviewer=reviewer_name or _NA,
            merge_disciplines=merge_disciplines,
        )
        plan_w = PAGE_W - 2 * plan_margin
        plan_h = plan_frame_top - plan_frame_bottom
        story: list = [table]
        story.extend(_build_annex_flowables(entries, plan_w, plan_h))

        buf = io.BytesIO()
        frame = Frame(
            TABLE_X0, frame_bottom, TABLE_W, frame_height,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="main",
        )
        main_tpl = PageTemplate(id="main", frames=[frame], onPage=drawer, pagesize=(PAGE_W, PAGE_H))
        plan_frame = Frame(
            plan_margin, plan_frame_bottom, plan_w, plan_h,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="plan",
        )
        plan_tpl = PageTemplate(
            id="plan_page",
            frames=[plan_frame],
            onPage=_draw_plan_legend,
            pagesize=(PAGE_W, PAGE_H),
        )
        doc = BaseDocTemplate(
            buf, pagesize=(PAGE_W, PAGE_H),
            pageTemplates=[main_tpl, plan_tpl],
            leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0,
            title="Lista de Chequeo de Planos",
        )
        doc.build(story, canvasmaker=NumberedCanvas)
        return buf.getvalue()

    try:
        return _render(merge_disciplines=True)
    except LayoutError:
        # A same-discipline group was too tall to keep merged across a page break;
        # retry without vertical discipline spans so rows can split.
        logger.warning("Checklist layout overflow with merged disciplines; retrying unmerged")
        return _render(merge_disciplines=False)
