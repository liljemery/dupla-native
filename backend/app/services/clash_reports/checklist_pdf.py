"""GA-FO-08 — Lista de Chequeo - Planos (control de planos con observaciones de clash)."""

from __future__ import annotations

import os
import re
import tempfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
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

from app.models.project_clash_item import ProjectClashItem
from app.services.clash_reports.plan_background_svg import (
    render_annotated_plan_svg,
    resolve_plan_pdf,
)

_PROCESS_TITLE = "PROCESO: GESTIÓN DE ARQUITECTURA Y CONTROL DE PLANOS"
_CHECKLIST_TITLE = "LISTA DE CHEQUEO - PLANOS"
_FORM_CODE = "GA-FO-08 (04.2025) V.01"

_TABLE_PAGE = landscape(letter)  # 792×612 pt — matches reference checklist pages
_PLAN_PAGE = (1728.0, 1296.0)  # large plan sheets like reference pages 3+
_MARGIN = 12 * mm
_TABLE_FOOTER_H = 16 * mm
_PLAN_FOOTER_H = 10 * mm
_TABLE_W = _TABLE_PAGE[0] - 2 * _MARGIN
_PLAN_W = _PLAN_PAGE[0] - 2 * _MARGIN
_PLAN_H = _PLAN_PAGE[1] - 2 * _MARGIN - _PLAN_FOOTER_H

_DATE_RE = re.compile(r"(\d{2})[.\-/](\d{2})[.\-/](\d{4})")
_PLAN_CODE_RE = re.compile(r"\b([A-Z]{2,4}[-_]?\d{1,3})\b", re.IGNORECASE)

_DISCIPLINE_LABELS: dict[str, str] = {
    "ARQUITECTURA": "ARQUITECTÓNICOS",
    "ARQ": "ARQUITECTÓNICOS",
    "ESTRUCTURA": "ESTRUCTURALES",
    "EST": "ESTRUCTURALES",
    "ELECTRICA": "ELÉCTRICOS",
    "ELECTRICO": "ELÉCTRICOS",
    "ELE": "ELÉCTRICOS",
    "ELC": "ELÉCTRICOS",
    "PLOMERIA": "SANITARIOS",
    "SANITARIO": "SANITARIOS",
    "SAN": "SANITARIOS",
    "HIDRO": "SANITARIOS",
    "MECANICA": "MECÁNICOS",
    "MEC": "MECÁNICOS",
}


def _esc(text: Any) -> str:
    s = str(text if text is not None else "")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _font() -> tuple[str, str]:
    from reportlab.pdfbase.pdfmetrics import getRegisteredFontNames

    names = set(getRegisteredFontNames())
    if "DuplaSans" in names:
        return "DuplaSans", "DuplaSans-Bold"
    return "Helvetica", "Helvetica-Bold"


def _styles() -> dict[str, ParagraphStyle]:
    from app.services.clash_reports import pdf_base  # noqa: F401

    body, bold = _font()
    base = getSampleStyleSheet()
    mk = ParagraphStyle
    return {
        "process": mk("proc", parent=base["Normal"], fontName=bold, fontSize=9, leading=11, alignment=TA_CENTER),
        "title": mk("tit", parent=base["Title"], fontName=bold, fontSize=16, leading=20, alignment=TA_CENTER, spaceAfter=4),
        "project": mk("proj", parent=base["Normal"], fontName=bold, fontSize=12, leading=15, alignment=TA_CENTER),
        "date": mk("dt", parent=base["Normal"], fontName=body, fontSize=10, leading=13, alignment=TA_CENTER, spaceAfter=8),
        "cell": mk("c", parent=base["BodyText"], fontName=body, fontSize=7, leading=9, wordWrap="LTR"),
        "cell_head": mk("ch", parent=base["BodyText"], fontName=bold, fontSize=7, leading=9, textColor=colors.white),
        "small": mk("sm", parent=base["BodyText"], fontName=body, fontSize=7, leading=9, textColor=colors.HexColor("#555555")),
    }


def _p(text: Any, style: str, st: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(_esc(text), st[style])


def _discipline_label(raw: str | None) -> str:
    key = str(raw or "").strip().upper()
    if not key:
        return "—"
    for prefix, label in _DISCIPLINE_LABELS.items():
        if key.startswith(prefix):
            return label
    return key


def _plan_code_from_name(filename: str) -> str:
    stem = Path(filename).stem.upper()
    match = _PLAN_CODE_RE.search(stem)
    if match:
        return match.group(1).replace("_", "-")
    # Abbreviated stem (max 12 chars) when no code pattern found.
    clean = re.sub(r"[^A-Z0-9]+", "-", stem).strip("-")
    return clean[:12] or "PLANO"


def _title_from_name(filename: str, level_id: str | None) -> str:
    stem = Path(filename).stem
    level = (level_id or "").strip()
    if level and level.lower() not in stem.lower():
        return f"{stem} — {level}"
    return stem


def _date_from_filename(filename: str) -> str:
    match = _DATE_RE.search(filename)
    if match:
        d, m, y = match.groups()
        return f"{d}.{m}.{y}"
    return "—"


def _observation_text(obs: dict[str, Any]) -> str:
    text = (obs.get("observation") or obs.get("recommended_action") or "").strip()
    if text:
        return text
    layer_a = obs.get("layer_a") or "—"
    layer_b = obs.get("layer_b") or "—"
    return f"Verificar solapamiento entre capas {layer_a} y {layer_b}."


def _incident_to_obs(inc: dict[str, Any]) -> dict[str, Any]:
    rep = inc.get("representative_conflict") or {}
    pair = inc.get("file_pair") or ["", ""]
    if not isinstance(pair, list):
        pair = ["", ""]
    while len(pair) < 2:
        pair.append("")
    bounds = inc.get("plan_bounds_mm") or rep.get("plan_intersection_bounds_mm") or [0, 0, 0, 0]
    centroid = inc.get("plan_centroid_mm") or rep.get("plan_intersection_centroid_mm") or [0, 0]
    layers = rep.get("raw_layers") or []
    b = bounds if isinstance(bounds, list) and len(bounds) == 4 else [0, 0, 0, 0]
    return {
        "dwg_a": Path(str(pair[0])).name if pair[0] else "—",
        "dwg_b": Path(str(pair[1])).name if len(pair) > 1 and pair[1] else "—",
        "level_id": str(inc.get("level_id") or "") or None,
        "discipline_a": str(rep.get("discipline_a") or "") or None,
        "discipline_b": str(rep.get("discipline_b") or "") or None,
        "layer_a": str(layers[0]) if layers else None,
        "layer_b": str(layers[1]) if len(layers) > 1 else None,
        "observation": None,
        "recommended_action": "Revisar el par directamente en planta.",
        "centroid_x_mm": float(centroid[0]) if len(centroid) > 0 else 0.0,
        "centroid_y_mm": float(centroid[1]) if len(centroid) > 1 else 0.0,
        "bounds_minx_mm": float(b[0]),
        "bounds_miny_mm": float(b[1]),
        "bounds_maxx_mm": float(b[2]),
        "bounds_maxy_mm": float(b[3]),
        "plan_bounds_mm": b,
        "clash_code": str(inc.get("incident_id") or ""),
    }


def _item_to_obs(item: ProjectClashItem) -> dict[str, Any]:
    return {
        "dwg_a": item.dwg_a or "—",
        "dwg_b": item.dwg_b or "—",
        "level_id": item.level_id,
        "discipline_a": item.discipline_a,
        "discipline_b": item.discipline_b,
        "layer_a": item.layer_a,
        "layer_b": item.layer_b,
        "observation": item.observation,
        "recommended_action": item.recommended_action,
        "centroid_x_mm": item.centroid_x_mm or 0.0,
        "centroid_y_mm": item.centroid_y_mm or 0.0,
        "bounds_minx_mm": item.bounds_minx_mm,
        "bounds_miny_mm": item.bounds_miny_mm,
        "bounds_maxx_mm": item.bounds_maxx_mm,
        "bounds_maxy_mm": item.bounds_maxy_mm,
        "clash_code": item.clash_code,
    }


def _group_table_rows(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group observations by (discipline, plan file) for the 8-column checklist table."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for obs in observations:
        key = (_discipline_label(obs.get("discipline_a")), obs.get("dwg_a") or "—")
        groups.setdefault(key, []).append(obs)
    rows: list[dict[str, Any]] = []
    for (discipline, plan), group in sorted(groups.items()):
        first = group[0]
        correl = sorted({_discipline_label(o.get("discipline_b")) for o in group if o.get("discipline_b")})
        correl = [c for c in correl if c != "—"]
        bullets = [_observation_text(o) for o in group]
        obs_html = (
            "El plano presenta las siguientes observaciones:<br/>"
            + "<br/>".join(f"- {_esc(b)}" for b in bullets)
        )
        rows.append(
            {
                "discipline": discipline,
                "plan_code": _plan_code_from_name(plan),
                "plan_title": _title_from_name(plan, first.get("level_id")),
                "description": "Coordinación de clashes detectados automáticamente.",
                "plan_date": _date_from_filename(plan),
                "revision": "REV. 1",
                "correlation": ", ".join(correl) if correl else "Demás disciplinas del proyecto",
                "observations": obs_html,
                "plan_file": plan,
                "level_id": first.get("level_id"),
                "group_obs": group,
            }
        )
    return rows


def _checklist_table(rows: list[dict[str, Any]], st: dict[str, ParagraphStyle]) -> Table:
    headers = [
        "DISCIPLINA",
        "NÚMERO DE PLANO",
        "TÍTULO DEL PLANO",
        "DESCRIPCIÓN DE PLANOS Y/O CAMBIOS",
        "FECHA DEL PLANO",
        "REVISIÓN",
        "CORRELACIÓN CON DEMÁS DISCIPLINAS",
        "OBSERVACIONES",
    ]
    col_widths = [22 * mm, 18 * mm, 32 * mm, 28 * mm, 18 * mm, 14 * mm, 32 * mm, 66 * mm]
    head = [_p(h, "cell_head", st) for h in headers]
    body = []
    for row in rows:
        body.append(
            [
                _p(row["discipline"], "cell", st),
                _p(row["plan_code"], "cell", st),
                _p(row["plan_title"], "cell", st),
                _p(row["description"], "cell", st),
                _p(row["plan_date"], "cell", st),
                _p(row["revision"], "cell", st),
                _p(row["correlation"], "cell", st),
                Paragraph(row["observations"], st["cell"]),
            ]
        )
    data = [head, *body]
    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT", splitByRow=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#888888")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _meta_footer_table(meta: dict[str, Any], st: dict[str, ParagraphStyle]) -> Table:
    folder = str(meta.get("folder_name") or "PLANOS").upper().replace(" ", "")
    folder_short = re.sub(r"[^A-Z0-9]", "", folder)[:12] or "PLANOS"
    ldc = meta.get("checklist_number") or f"LDC-{folder_short}-05"
    rows = [
        [
            _p("PROYECTO:", "cell", st),
            _p(meta.get("project_name", ""), "cell", st),
            _p("No. LISTA DE CHEQUEO:", "cell", st),
            _p(ldc, "cell", st),
        ],
        [
            _p("FECHA:", "cell", st),
            _p(meta.get("run_date", ""), "cell", st),
            _p("REVISADO POR:", "cell", st),
            _p(meta.get("user_display", ""), "cell", st),
        ],
    ]
    t = Table(rows, colWidths=[28 * mm, 60 * mm, 38 * mm, 60 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#cfd4da")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#cfd4da")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9aa3af")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return t


def _sheet_drawing(svg_str: str, max_w: float, max_h: float):
    try:
        from svglib.svglib import svg2rlg
    except Exception:
        return None
    tmp = tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False, encoding="utf-8")
    try:
        tmp.write(svg_str)
        tmp.close()
        drawing = svg2rlg(tmp.name)
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    if drawing is None or not drawing.width:
        return None
    scale = min(max_w / drawing.width, max_h / drawing.height) * 0.98
    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)
    return drawing


class _GaFo08Doc(BaseDocTemplate):
    def __init__(
        self,
        buffer: BytesIO,
        *,
        meta: dict[str, Any],
        table_page_count: int,
    ) -> None:
        self._meta = meta
        self._table_page_count = max(table_page_count, 1)
        self._on_plan_section = False
        super().__init__(
            buffer,
            pagesize=_TABLE_PAGE,
            leftMargin=_MARGIN,
            rightMargin=_MARGIN,
            topMargin=_MARGIN,
            bottomMargin=_MARGIN + _TABLE_FOOTER_H,
            title="Lista de Chequeo - Planos",
        )
        table_frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="table",
        )
        plan_frame = Frame(
            _MARGIN,
            _MARGIN + _PLAN_FOOTER_H,
            _PLAN_PAGE[0] - 2 * _MARGIN,
            _PLAN_PAGE[1] - 2 * _MARGIN - _PLAN_FOOTER_H,
            id="plan",
        )
        self.addPageTemplates(
            [
                PageTemplate(id="table", frames=[table_frame], pagesize=_TABLE_PAGE, onPage=self._on_table_page),
                PageTemplate(id="plan", frames=[plan_frame], pagesize=_PLAN_PAGE, onPage=self._on_plan_page),
            ]
        )

    def _on_table_page(self, canvas, doc) -> None:
        pw, _ = doc.pagesize
        canvas.saveState()
        body, _ = _font()
        canvas.setFont(body, 7)
        canvas.setFillColor(colors.HexColor("#555555"))
        page_label = f"Página {doc.page} de {self._table_page_count}"
        canvas.drawCentredString(pw / 2, 7 * mm, f"Este documento es confidencial  {_FORM_CODE}  {page_label}")
        canvas.restoreState()

    def _on_plan_page(self, canvas, doc) -> None:
        pw, _ = doc.pagesize
        canvas.saveState()
        body, _ = _font()
        canvas.setFont(body, 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawCentredString(pw / 2, 5 * mm, f"Este documento es confidencial  {_FORM_CODE}")
        canvas.restoreState()


def _table_header_block(meta: dict[str, Any], st: dict[str, ParagraphStyle]) -> list[Any]:
    return [
        _p(_PROCESS_TITLE, "process", st),
        Spacer(1, 2),
        _p(_CHECKLIST_TITLE, "title", st),
        Spacer(1, 4),
        _p(meta.get("project_name", ""), "project", st),
        _p(meta.get("run_date", ""), "date", st),
        Spacer(1, 4),
    ]


def _build_story(
    observations: list[dict[str, Any]],
    meta: dict[str, Any],
    *,
    cache_root: str | None,
    logo_path: str | None,
    job_output_dir: str | None = None,
    tile_path: Callable[[str, bool], Path | None] | None = None,
    pdf_search_dirs: list[str | Path] | None = None,
) -> list[Any]:
    st = _styles()
    table_rows = _group_table_rows(observations)
    if not table_rows:
        table_rows = [
            {
                "discipline": "—",
                "plan_code": "—",
                "plan_title": "Sin observaciones",
                "description": "—",
                "plan_date": "—",
                "revision": "—",
                "correlation": "—",
                "observations": "No se detectaron clashes en esta corrida.",
                "plan_file": "—",
                "level_id": None,
                "group_obs": [],
            }
        ]

    story: list[Any] = []
    if logo_path and Path(logo_path).is_file():
        try:
            story.append(Image(logo_path, width=40 * mm, height=12 * mm, kind="proportional"))
            story.append(Spacer(1, 4))
        except Exception:
            pass

    story.extend(_table_header_block(meta, st))
    story.append(_checklist_table(table_rows, st))
    story.append(Spacer(1, 8))
    story.append(_meta_footer_table(meta, st))

    numbered_all: list[tuple[int, dict[str, Any]]] = []
    counter = 1
    for row in table_rows:
        for obs in row.get("group_obs") or []:
            numbered_all.append((counter, obs))
            counter += 1

    by_sheet: dict[tuple[str, str | None], list[tuple[int, dict[str, Any]]]] = {}
    for number, obs in numbered_all:
        key = (obs.get("dwg_a") or "—", obs.get("level_id"))
        by_sheet.setdefault(key, []).append((number, obs))

    search_dirs: list[str | Path] = list(pdf_search_dirs or [])
    if job_output_dir:
        search_dirs.append(job_output_dir)

    plan_sheets = [(k, v) for k, v in sorted(by_sheet.items()) if k[0] != "—"]
    if plan_sheets:
        story.append(NextPageTemplate("plan"))
        story.append(PageBreak())

    for idx, ((plan_file, level_id), numbered) in enumerate(plan_sheets):
        pdf_bg = resolve_plan_pdf(search_dirs, plan_file)
        svg = render_annotated_plan_svg(
            numbered=numbered,
            dwg_name=plan_file,
            level_id=level_id,
            cache_root=cache_root,
            width=_PLAN_PAGE[0],
            height=_PLAN_PAGE[1],
            pdf_background_path=pdf_bg,
            tile_path=tile_path,
        )
        drawing = _sheet_drawing(svg, _PLAN_W, _PLAN_H)
        if drawing is not None:
            story.append(drawing)
        else:
            story.append(_p("Vista de plano no disponible.", "small", st))
        if idx < len(plan_sheets) - 1:
            story.append(PageBreak())

    return story


def build_checklist_pdf(
    *,
    incidents: list[dict[str, Any]] | None = None,
    items: list[ProjectClashItem] | None = None,
    project_name: str,
    checklist_number: str | None = None,
    reviewer_name: str = "Revisión Técnica",
    export_date: str | date | None = None,
    folder_name: str | None = None,
    logo_grupodupla_path: str | None = None,
    logo_constructora_path: str | None = None,
    aps_token: str | None = None,
    job_cache_dir: str | None = None,
    file_discipline_hints: dict[str, str] | None = None,
    job_output_dir: str | None = None,
    tile_path: Callable[[str, bool], Path | None] | None = None,
    pdf_search_dirs: list[str | Path] | None = None,
) -> bytes:
    """Build the GA-FO-08 checklist PDF from motor incidents or workflow items."""
    del aps_token, logo_constructora_path, file_discipline_hints  # reserved for future APS live fetch

    if items:
        observations = [_item_to_obs(it) for it in items]
    elif incidents:
        observations = [_incident_to_obs(inc) for inc in incidents if isinstance(inc, dict)]
    else:
        observations = []

    if export_date is None:
        run_date = datetime.now().date().isoformat()
    elif isinstance(export_date, date):
        run_date = export_date.isoformat()
    else:
        run_date = str(export_date)

    meta = {
        "project_name": project_name,
        "folder_name": folder_name or project_name,
        "user_display": reviewer_name,
        "run_date": run_date,
        "checklist_number": checklist_number,
    }

    cache_root = job_cache_dir
    if cache_root:
        # Prefer APS cache sibling when job dir is the coordination output root.
        sibling = Path(cache_root).parent / "aps_cache"
        if sibling.is_dir():
            cache_root = str(sibling)

    story = _build_story(
        observations,
        meta,
        cache_root=cache_root,
        logo_path=logo_grupodupla_path,
        job_output_dir=job_output_dir or job_cache_dir,
        tile_path=tile_path,
        pdf_search_dirs=pdf_search_dirs,
    )

    table_pages = max(1, (len(_group_table_rows(observations)) + 1) // 2)
    story.insert(0, NextPageTemplate("table"))

    buf = BytesIO()
    doc = _GaFo08Doc(buf, meta=meta, table_page_count=table_pages)
    doc.build(story)
    return buf.getvalue()


def build_checklist_pdf_from_items(
    *,
    items: list[ProjectClashItem],
    meta: dict[str, Any],
    cache_root: str | None = None,
    logo_path: str | None = None,
    job_output_dir: str | None = None,
    tile_path: Callable[[str, bool], Path | None] | None = None,
    pdf_search_dirs: list[str | Path] | None = None,
) -> bytes:
    """Convenience wrapper used by ClashExportService."""
    folder = meta.get("folder_name") or meta.get("project_name") or "PLANOS"
    folder_key = re.sub(r"[^A-Z0-9]", "", str(folder).upper())[:12] or "PLANOS"
    return build_checklist_pdf(
        items=items,
        project_name=str(meta.get("project_name") or "Proyecto"),
        checklist_number=meta.get("checklist_number") or f"LDC-{folder_key}-05",
        reviewer_name=str(meta.get("user_display") or "Revisión Técnica"),
        export_date=meta.get("run_date"),
        folder_name=str(folder),
        logo_grupodupla_path=logo_path,
        job_cache_dir=cache_root,
        job_output_dir=job_output_dir,
        tile_path=tile_path,
        pdf_search_dirs=pdf_search_dirs,
    )
