"""Rich "Informe de Coordinación de Clashes" PDF (DU-FO-CLASH-01).

Mirrors the branded Dupla coordination deliverable: a cover with KPIs, a
priority summary with a doughnut, the correction lifecycle flow bar, the check
matrix, per-clash comparison plates with embedded plan-view tiles, the
chronological log, the corrected-plan handover flow, and the alias legend.

Everything is driven by live workflow rows (items + events + corrections), so a
re-download after a UI change reflects the new state. The same builder produces
the per-run report (``final=False``) and the closing report (``final=True``).
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.domain.clash_coordinates import location_from_mm
from app.domain.clash_workflow_enums import (
    CORRECTION_TARGET_LABELS_ES,
    ClashStatus,
    CorrectionTarget,
    EventType,
    ReviewerDecision,
    Severity,
    decision_label,
    status_label,
)
from app.models.project_clash_item import ProjectClashItem

# --- palette --------------------------------------------------------------
BRAND_RED = colors.HexColor("#C8102E")
DARK = colors.HexColor("#2b3648")
GRID = colors.HexColor("#9aa3af")
MUTED = colors.HexColor("#6b7280")
LIGHT = colors.HexColor("#eceef1")

SEV_COLORS = {
    "critical": colors.HexColor("#E53935"),
    "high": colors.HexColor("#FB8C00"),
    "medium": colors.HexColor("#F4B400"),
    "low": colors.HexColor("#1E88E5"),
}
SEV_ES = {"critical": "Crítica", "high": "Alta", "medium": "Media", "low": "Baja"}

PAGE_MARGIN = 16 * mm
FOOTER_H = 12 * mm
_LS = landscape(A4)
_CONTENT_W = _LS[0] - 2 * PAGE_MARGIN

_EVENT_LABELS_ES = {
    EventType.INGESTED.value: "Ingestado",
    EventType.STATUS_CHANGE.value: "Cambio de estado",
    EventType.DECISION.value: "Decisión",
    EventType.ASSIGNMENT.value: "Asignación",
    EventType.COMMENT.value: "Comentario",
    EventType.CORRECTION_UPLOAD.value: "Corrección cargada",
    EventType.REANALYSIS.value: "Reanálisis",
}

# Correction lifecycle stages and the status -> stage mapping.
LIFECYCLE = ["Detectado", "Revisado", "Cargado", "Re-análisis", "Resuelto"]
_STATUS_STAGE = {
    ClashStatus.DETECTED.value: 0,
    ClashStatus.NEEDS_REVIEW.value: 1,
    ClashStatus.CORRECTION_REQUIRED.value: 1,
    ClashStatus.FALSE_POSITIVE.value: 1,
    ClashStatus.CORRECTION_UPLOADED.value: 2,
    ClashStatus.PENDING_REANALYSIS.value: 3,
    ClashStatus.RESOLVED.value: 4,
    ClashStatus.STILL_PRESENT.value: 4,
    ClashStatus.CLOSED.value: 4,
}


def _font() -> tuple[str, str, str]:
    from reportlab.pdfbase.pdfmetrics import getRegisteredFontNames

    names = set(getRegisteredFontNames())
    if "DuplaSans" in names:
        return "DuplaSans", "DuplaSans-Bold", names and ("DuplaSansMono" if "DuplaSansMono" in names else "Courier")
    return "Helvetica", "Helvetica-Bold", "Courier"


def _styles() -> dict[str, ParagraphStyle]:
    # Importing pdf_base registers the bundled unicode font if available.
    from app.services.clash_reports import pdf_base  # noqa: F401

    body, bold, mono = _font()
    base = getSampleStyleSheet()
    mk = ParagraphStyle
    return {
        "cover_title": mk("ct", parent=base["Title"], fontName=bold, fontSize=30, leading=34, textColor=colors.white),
        "cover_sub": mk("cs", parent=base["Normal"], fontName=body, fontSize=13, leading=17, textColor=colors.white),
        "cover_small": mk("csm", parent=base["Normal"], fontName=body, fontSize=9, leading=12, textColor=colors.white),
        "h2": mk("h2", parent=base["Heading2"], fontName=bold, fontSize=14, leading=18, textColor=BRAND_RED, spaceAfter=4),
        "h3": mk("h3", parent=base["Heading3"], fontName=bold, fontSize=10.5, leading=14, textColor=DARK, spaceBefore=4, spaceAfter=2),
        "body": mk("b", parent=base["BodyText"], fontName=body, fontSize=9.5, leading=13),
        "small": mk("s", parent=base["BodyText"], fontName=body, fontSize=8, leading=10.5, textColor=MUTED),
        "kpi_label": mk("kl", parent=base["Normal"], fontName=bold, fontSize=8, leading=10, textColor=MUTED),
        "kpi_value": mk("kv", parent=base["Normal"], fontName=bold, fontSize=26, leading=28, textColor=DARK),
        "cell": mk("c", parent=base["BodyText"], fontName=body, fontSize=8, leading=10),
        "cell_mono": mk("cm", parent=base["BodyText"], fontName=mono, fontSize=7, leading=9, textColor=MUTED),
        "cell_head": mk("ch", parent=base["BodyText"], fontName=bold, fontSize=7.5, leading=9.5, textColor=colors.white),
        "chip": mk("cp", parent=base["BodyText"], fontName=bold, fontSize=8, leading=10, textColor=colors.white, alignment=1),
    }


def _esc(text: Any) -> str:
    s = str(text if text is not None else "")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _P(text: Any, style: str, st: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(_esc(text), st[style])


# --- data helpers ---------------------------------------------------------
def _kpis(items: list[ProjectClashItem]) -> dict[str, int]:
    total = len(items)
    crit_high = sum(1 for i in items if i.severity in ("critical", "high"))
    pending = sum(
        1
        for i in items
        if i.status in (ClashStatus.DETECTED.value, ClashStatus.NEEDS_REVIEW.value)
        and not i.reviewer_decision
    )
    return {"total": total, "crit_high": crit_high, "pending": pending}


def _zoom_command(item: ProjectClashItem) -> str:
    loc = location_from_mm(
        centroid_mm=(item.centroid_x_mm or 0.0, item.centroid_y_mm or 0.0),
        bounds_mm=(
            item.bounds_minx_mm or 0.0,
            item.bounds_miny_mm or 0.0,
            item.bounds_maxx_mm or 0.0,
            item.bounds_maxy_mm or 0.0,
        ),
    )
    payload = loc.ui_payload()
    return str(payload.get("autocad_zoom_window_command") or "")


def _status_text(value: str | None) -> str:
    try:
        return status_label(ClashStatus(value))
    except (ValueError, TypeError):
        return value or "—"


def _decision_text(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return decision_label(ReviewerDecision(value))
    except ValueError:
        return value


def _dwg_to_fix(item: ProjectClashItem) -> str:
    if not item.reviewer_decision:
        return "DWG a corregir: pendiente de decisión del revisor"
    try:
        dec = ReviewerDecision(item.reviewer_decision)
    except ValueError:
        return "—"
    target = {
        ReviewerDecision.CORRECT_DWG_A: CorrectionTarget.DWG_A,
        ReviewerDecision.CORRECT_DWG_B: CorrectionTarget.DWG_B,
        ReviewerDecision.CORRECT_BOTH: CorrectionTarget.BOTH,
    }.get(dec)
    if target is None:
        return _decision_text(item.reviewer_decision)
    return f"Corregir {CORRECTION_TARGET_LABELS_ES[target]}"


def _carga_state(item: ProjectClashItem) -> tuple[str, colors.Color]:
    if item.corrections:
        latest = max(item.corrections, key=lambda c: c.uploaded_at or datetime.min)
        if latest.result:
            return ("Reanalizado", colors.HexColor("#2e7d32"))
        return ("Corrección cargada", colors.HexColor("#1565c0"))
    return ("Pendiente de carga", BRAND_RED)


# --- table builders -------------------------------------------------------
def _data_table(headers, rows, col_widths, st, *, header_bg=DARK, zebra=True):
    head = [_P(h, "cell_head", st) for h in headers]
    body = []
    for r in rows:
        cells = [c if isinstance(c, Paragraph) else _P(c, "cell", st) for c in r]
        body.append(cells)
    data = [head, *body]
    total = sum(col_widths)
    if total > _CONTENT_W:
        col_widths = [w * _CONTENT_W / total for w in col_widths]
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if zebra:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]))
    t = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT", splitByRow=1)
    t.setStyle(TableStyle(style))
    return t


def _chip(text: str, color: colors.Color, st: dict) -> Paragraph:
    """A pill-style label rendered as a colored paragraph (no nested table)."""
    style = ParagraphStyle(
        "chip_x", parent=st["chip"], backColor=color, borderPadding=(2, 3, 2, 3), borderRadius=2
    )
    return Paragraph(_esc(text), style)


# --- cover ----------------------------------------------------------------
def _kpi_cards(items, st) -> Table:
    k = _kpis(items)
    cards = [
        ("TOTAL CLASHES", str(k["total"]), colors.HexColor("#2e7d32")),
        ("CRÍTICOS + ALTOS", str(k["crit_high"]), BRAND_RED),
        ("PENDIENTES DE DECISIÓN", str(k["pending"]), colors.HexColor("#F4B400")),
    ]
    cells = []
    for label, value, top in cards:
        inner = Table(
            [[_P(label, "kpi_label", st)], [_P(value, "kpi_value", st)]],
            colWidths=[(_CONTENT_W - 16 * mm) / 3],
        )
        inner.setStyle(
            TableStyle(
                [
                    ("LINEABOVE", (0, 0), (-1, 0), 3, top),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, 0), 8),
                    ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
                ]
            )
        )
        cells.append(inner)
    row = Table([cells], colWidths=[(_CONTENT_W) / 3] * 3)
    row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    return row


def _cover(meta, items, st, final: bool) -> list:
    title = str(meta.get("project_name") or "Proyecto")
    emission = str(meta.get("run_date") or "")
    subtitle = "Comparación DWG vs DWG, revisión en obra y entrega de planos corregidos"
    band = Table(
        [
            [_P(title, "cover_title", st)],
            [_P("Informe Final de Coordinación de Clashes" if final else "Informe de Coordinación de Clashes", "cover_sub", st)],
            [_P(subtitle, "cover_small", st)],
            [_P(f"Fecha de emisión · {emission}", "cover_small", st)],
        ],
        colWidths=[_CONTENT_W],
    )
    band.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_RED),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, 0), 16),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 12),
            ]
        )
    )
    contents = [
        "Resumen de clashes por prioridad",
        "Matriz de chequeo (tabla principal y tabla de corrección)",
        "Láminas de comparación DWG A vs DWG B",
        "Bitácora de validación y corrección",
        "Entrega de planos corregidos",
    ]
    if final:
        contents.append("Lista de chequeo y plano de observaciones (nubes por disciplina)")
    contents.append("Leyenda de alias de archivos")
    items_flow = [_P("Contenido del entregable", "h3", st)]
    for i, c in enumerate(contents, 1):
        items_flow.append(_P(f"{i}.  {c}", "body", st))
    return [
        band,
        Spacer(1, 14),
        _kpi_cards(items, st),
        Spacer(1, 16),
        *items_flow,
        NextPageTemplate("content"),
        PageBreak(),
    ]


# --- priority summary + doughnut + lifecycle ------------------------------
def _doughnut(counts: dict[str, int]):
    try:
        from reportlab.graphics.charts.doughnut import Doughnut
        from reportlab.graphics.shapes import Drawing, String
    except Exception:
        return None
    data = [counts.get(s, 0) for s in ("critical", "high", "medium", "low")]
    if sum(data) == 0:
        return None
    d = Drawing(150, 120)
    dn = Doughnut()
    dn.x, dn.y, dn.width, dn.height = 15, 5, 110, 110
    dn.data = data
    dn.innerRadiusFraction = 0.55
    for idx, sev in enumerate(("critical", "high", "medium", "low")):
        dn.slices[idx].fillColor = SEV_COLORS[sev]
        dn.slices[idx].strokeColor = colors.white
    d.add(dn)
    d.add(String(75, 0, "Distribución por prioridad", fontSize=7, fillColor=MUTED, textAnchor="middle"))
    return d


def _priority_summary(items, st) -> list:
    by_sev: dict[str, list[ProjectClashItem]] = {"critical": [], "high": [], "medium": [], "low": []}
    for i in items:
        by_sev[i.severity if i.severity in by_sev else "low"].append(i)
    rows = []
    counts = {}
    for sev in ("critical", "high", "medium", "low"):
        group = by_sev.get(sev, [])
        counts[sev] = len(group)
        codes = ", ".join(g.clash_code for g in group) or "—"
        pairs = "; ".join(
            f"{g.dwg_a or '—'} ↔ {g.dwg_b or '—'}" for g in group[:3]
        ) or "—"
        rows.append([_chip(SEV_ES[sev], SEV_COLORS[sev], st), str(len(group)), _P(codes, "cell", st), _P(pairs, "cell", st)])

    table = _data_table(
        ["PRIORIDAD", "CANTIDAD", "CÓDIGOS", "PARES DWG COMPARADOS"],
        rows,
        [30 * mm, 22 * mm, 70 * mm, 100 * mm],
        st,
        zebra=False,
    )
    flow = [
        _P("Resumen de clashes por prioridad", "h2", st),
        _P("Distribución de códigos para planificación de revisión en obra y coordinación entre disciplinas.", "small", st),
        Spacer(1, 6),
        table,
        Spacer(1, 10),
    ]
    doughnut = _doughnut(counts)
    if doughnut is not None:
        flow.append(doughnut)
        flow.append(Spacer(1, 8))
    flow += [
        *_lifecycle_bar(items, st),
        NextPageTemplate("content"),
        PageBreak(),
    ]
    return flow


def _lifecycle_bar(items, st) -> list:
    stage_counts = [0] * len(LIFECYCLE)
    for i in items:
        stage_counts[_STATUS_STAGE.get(i.status, 0)] += 1
    active = stage_counts.index(max(stage_counts)) if items else 0
    cells = []
    style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]
    for idx, name in enumerate(LIFECYCLE):
        is_active = idx == active
        label = f"{name}" + (f" ({stage_counts[idx]})" if stage_counts[idx] else "")
        cells.append(Paragraph(_esc(label), ParagraphStyle(
            "lc", parent=st["body"], alignment=1, fontSize=9,
            textColor=colors.white if is_active else DARK,
            fontName=_font()[1] if is_active else _font()[0],
        )))
        bg = BRAND_RED if is_active else LIGHT
        col = idx
        style.append(("BACKGROUND", (col, 0), (col, 0), bg))
    bar = Table([cells], colWidths=[_CONTENT_W / len(LIFECYCLE)] * len(LIFECYCLE), rowHeights=[10 * mm])
    style += [("BOX", (0, 0), (-1, -1), 0.5, GRID), ("INNERGRID", (0, 0), (-1, -1), 2, colors.white)]
    bar.setStyle(TableStyle(style))
    return [
        _P("Ciclo de vida de corrección", "h3", st),
        bar,
        _P("Detectado → Revisado → Corrección cargada → Pendiente re-análisis → Resuelto / Aún presente", "small", st),
    ]


# --- check matrix ---------------------------------------------------------
def _check_matrix(items, st) -> list:
    main_rows = []
    for i in items:
        ubic = f"X: {i.centroid_x_mm or 0:.0f} · Y: {i.centroid_y_mm or 0:.0f} mm"
        main_rows.append([
            i.clash_code,
            _P(i.dwg_a or "—", "cell", st),
            _P(i.dwg_b or "—", "cell", st),
            i.level_id or "—",
            _chip(SEV_ES.get(i.severity, "Baja"), SEV_COLORS.get(i.severity, SEV_COLORS["low"]), st),
            _P(ubic, "cell_mono", st),
            _P(i.observation or i.recommended_action or "—", "cell", st),
            _P(_decision_text(i.reviewer_decision) if i.reviewer_decision else _status_text(i.status), "cell", st),
        ])
    corr_rows = []
    for i in items:
        carga_txt, carga_col = _carga_state(i)
        corr_rows.append([
            i.clash_code,
            _P(_dwg_to_fix(i), "cell", st),
            _chip(_status_text(i.status), DARK, st),
            _chip(carga_txt, carga_col, st),
            _P((i.corrections[-1].revision_name if i.corrections else "—"), "cell", st),
        ])
    return [
        _P("Matriz de chequeo — coordinación de planos", "h2", st),
        _P("La tabla de corrección registra el DWG a corregir y los estados en Dupla.", "small", st),
        Spacer(1, 4),
        _P("Tabla principal", "h3", st),
        _data_table(
            ["CÓDIGO", "PLANO A", "PLANO B", "NIVEL", "PRIORIDAD", "UBICACIÓN", "OBSERVACIÓN", "DECISIÓN"],
            main_rows,
            [20 * mm, 38 * mm, 38 * mm, 18 * mm, 24 * mm, 36 * mm, 50 * mm, 30 * mm],
            st,
        ),
        Spacer(1, 8),
        _P("Tabla de corrección y carga", "h3", st),
        _data_table(
            ["CÓDIGO", "DWG A CORREGIR", "ESTADO CORRECCIÓN", "ESTADO CARGA", "REVISIÓN"],
            corr_rows,
            [20 * mm, 90 * mm, 32 * mm, 32 * mm, 36 * mm],
            st,
        ),
        NextPageTemplate("content"),
        PageBreak(),
    ]


# --- comparison plates ----------------------------------------------------
def _tile_drawing(
    output_dir: str | None,
    clash_code: str,
    *,
    annotated: bool,
    max_w: float,
    tile_path: Callable[[str, bool], Path | None] | None = None,
):
    tile: Path | None = None
    if tile_path is not None:
        tile = tile_path(clash_code, annotated)
    if tile is None and output_dir:
        name = f"{clash_code}_annotated.svg" if annotated else f"{clash_code}.svg"
        tile = Path(output_dir) / "tiles" / name
        if not tile.is_file():
            alt = Path(output_dir) / "tiles" / (f"{clash_code}.svg" if annotated else f"{clash_code}_annotated.svg")
            tile = alt if alt.is_file() else tile
    if tile is None or not tile.is_file():
        return None
    try:
        from svglib.svglib import svg2rlg

        d = svg2rlg(str(tile))
        if d is None or not d.width:
            return None
        scale = max_w / d.width
        d.width *= scale
        d.height *= scale
        d.scale(scale, scale)
        return d
    except Exception:
        return None


def _plate(
    item,
    output_dir,
    st,
    *,
    tile_path: Callable[[str, bool], Path | None] | None = None,
) -> list:
    header = Table(
        [[
            _P(f"{item.clash_code} · Solapamiento constructivo · {item.layer_a or '—'} / {item.layer_b or '—'}", "h3", st),
            Paragraph(_esc(f"Prioridad {SEV_ES.get(item.severity, 'Baja')}"), ParagraphStyle("ph", parent=st["h3"], textColor=colors.white, alignment=2)),
        ]],
        colWidths=[_CONTENT_W * 0.7, _CONTENT_W * 0.3],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#dbe4f0")),
        ("LINEABOVE", (0, 0), (-1, 0), 2, colors.HexColor("#3b6fb0")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#3b6fb0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    info = _P(
        f"DWG A: {item.dwg_a or '—'} | DWG B: {item.dwg_b or '—'} · Nivel: {item.level_id or '—'} · "
        f"Comando AutoCAD: {_zoom_command(item)}",
        "small", st,
    )
    half = (_CONTENT_W - 6 * mm) / 2
    a = _tile_drawing(output_dir, item.clash_code, annotated=True, max_w=half, tile_path=tile_path)
    b = _tile_drawing(output_dir, item.clash_code, annotated=False, max_w=half, tile_path=tile_path)
    a_cell = a if a is not None else _P("Vista DWG A no disponible", "small", st)
    b_cell = b if b is not None else _P("Vista DWG B no disponible", "small", st)
    tiles = Table(
        [[_P(f"DWG A — {item.dwg_a or '—'}", "small", st), _P(f"DWG B — {item.dwg_b or '—'}", "small", st)],
         [a_cell, b_cell]],
        colWidths=[half, half],
    )
    tiles.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 1), (-1, 1), 0.5, GRID)]))
    action = Table(
        [[_P(f"ACCIÓN REQUERIDA: {item.observation or item.recommended_action or 'Revisar el par en planta.'}", "small", st),
          _P("[ ] Real    [ ] Falso positivo    [ ] Pendiente", "small", st)]],
        colWidths=[_CONTENT_W * 0.7, _CONTENT_W * 0.3],
    )
    action.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, BRAND_RED), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fdeeee")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return [header, Spacer(1, 2), info, Spacer(1, 2), tiles, Spacer(1, 3), action, Spacer(1, 10)]


def _plates(
    items,
    output_dir,
    st,
    *,
    tile_path: Callable[[str, bool], Path | None] | None = None,
) -> list:
    if not items:
        return []
    flow = [_P("Láminas de comparación DWG A vs DWG B", "h2", st), Spacer(1, 4)]
    for item in items:
        flow.extend(_plate(item, output_dir, st, tile_path=tile_path))
    flow += [NextPageTemplate("content"), PageBreak()]
    return flow


# --- bitácora -------------------------------------------------------------
def _bitacora(items, st) -> list:
    pairs = []
    for item in items:
        for ev in item.events:
            pairs.append((ev, item.clash_code))
    pairs.sort(key=lambda p: p[0].created_at or datetime.max)
    rows = []
    for ev, code in pairs:
        when = ev.created_at.strftime("%Y-%m-%d %H:%M") if ev.created_at else "—"
        detail = []
        if ev.decision:
            detail.append(_decision_text(ev.decision))
        if ev.previous_status or ev.new_status:
            detail.append(f"{_status_text(ev.previous_status)} → {_status_text(ev.new_status)}")
        if ev.comment:
            detail.append(ev.comment)
        rows.append([
            code,
            _EVENT_LABELS_ES.get(ev.event_type, ev.event_type),
            _P(" · ".join(d for d in detail if d) or "—", "cell", st),
            ev.actor or "—",
            when,
        ])
    if not rows:
        rows = [["—", "—", _P("Sin eventos registrados todavía.", "cell", st), "—", "—"]]
    return [
        _P("Bitácora de validación y corrección", "h2", st),
        _P("Registre la decisión del revisor, el DWG corregido y el avance del estado de corrección.", "small", st),
        Spacer(1, 4),
        _data_table(
            ["CÓDIGO", "EVENTO", "DETALLE", "RESP.", "FECHA"],
            rows,
            [22 * mm, 34 * mm, 120 * mm, 44 * mm, 28 * mm],
            st,
        ),
        NextPageTemplate("content"),
        PageBreak(),
    ]


# --- handover flow + alias ------------------------------------------------
def _handover(st) -> list:
    steps = [
        "Dupla detecta clashes comparando un par de archivos DWG (DWG A vs DWG B) en la misma corrida de análisis.",
        "El arquitecto o coordinador revisa este informe, localiza cada punto en AutoCAD y corrige el DWG afectado.",
        "El DWG corregido debe subirse de nuevo en Dupla, en la sección de Clashes, vinculado al código y a la corrida correspondiente.",
        "No sobrescriba el DWG original del proyecto: Dupla conserva el archivo base y registra la corrección como una revisión aparte.",
        "Tras la carga, Dupla actualizará el estado del clash. Un re-análisis posterior confirmará si el conflicto quedó resuelto.",
    ]
    flow = [
        _P("Entrega de planos corregidos", "h2", st),
        *[_P(s, "body", st) for s in steps],
        Spacer(1, 6),
        _P("Pasos operativos", "h3", st),
        _P("1. Revise cada código en las láminas DWG A vs DWG B y en la matriz de chequeo.", "body", st),
        _P("2. En AutoCAD, abra el par original (DWG A y DWG B) y aplique el comando Z W indicado.", "body", st),
        _P("3. Corrija en AutoCAD el DWG señalado en «DWG a corregir» (no reemplace el archivo original).", "body", st),
        _P("4. Guarde una revisión identificable (ej.: ARQ_P1_REV_S-A1.dwg) y súbala en Clashes.", "body", st),
        _P("5. Registre la decisión del revisor (Real / Falso positivo / Pendiente) y el avance en la bitácora.", "body", st),
        _P("6. Espere el re-análisis de Dupla para confirmar Resuelto o Aún presente.", "body", st),
        NextPageTemplate("content"),
        PageBreak(),
    ]
    return flow


def _alias_legend(items, st) -> list:
    names = []
    seen = set()
    for i in items:
        for n in (i.dwg_a, i.dwg_b):
            if n and n not in seen:
                seen.add(n)
                names.append(n)
    rows = [[_P(n, "cell", st), _P(n, "cell", st)] for n in names] or [["—", "—"]]
    return [
        _P("Leyenda de archivos y alias", "h2", st),
        _P("Alias usado en tablas y láminas visuales · ruta completa en el proyecto.", "small", st),
        Spacer(1, 4),
        _data_table(["ALIAS", "ARCHIVO / RUTA"], rows, [90 * mm, 150 * mm], st),
    ]


# --- doc template ---------------------------------------------------------
class _CoordDoc(BaseDocTemplate):
    def __init__(self, buf, *, breadcrumb: str, revision_label: str, total_hint: int = 7) -> None:
        self._breadcrumb = breadcrumb
        self._revision_label = revision_label
        super().__init__(
            buf, pagesize=_LS,
            leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
            topMargin=PAGE_MARGIN + 8 * mm, bottomMargin=PAGE_MARGIN + FOOTER_H,
        )
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[frame], onPage=self._cover_page),
            PageTemplate(id="content", frames=[frame], onPage=self._content_page),
        ])

    def _footer(self, canvas, doc):
        pw, _ = doc.pagesize
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.setStrokeColor(BRAND_RED)
        canvas.setLineWidth(1)
        canvas.line(PAGE_MARGIN, 13 * mm, pw - PAGE_MARGIN, 13 * mm)
        canvas.drawString(PAGE_MARGIN, 9 * mm, f"DU-FO-CLASH-01 · {self._revision_label} · Exportado: {datetime.now().date().isoformat()}")
        canvas.drawCentredString(pw / 2, 9 * mm, "Este documento es confidencial")
        canvas.drawRightString(pw - PAGE_MARGIN, 9 * mm, f"Pág. {doc.page} · Sistema Dupla")

    def _cover_page(self, canvas, doc):
        self._footer(canvas, doc)

    def _content_page(self, canvas, doc):
        pw, ph = doc.pagesize
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(PAGE_MARGIN, ph - 12 * mm, self._breadcrumb)
        canvas.drawRightString(pw - PAGE_MARGIN, ph - 12 * mm, "Run · fast_compare")
        canvas.setStrokeColor(BRAND_RED)
        canvas.setLineWidth(1)
        canvas.line(PAGE_MARGIN, ph - 14 * mm, pw - PAGE_MARGIN, ph - 14 * mm)
        canvas.restoreState()
        self._footer(canvas, doc)


def build_coordination_report_pdf(
    *,
    meta: dict[str, Any],
    items: list[ProjectClashItem],
    output_dir: str | None = None,
    final: bool = False,
    revision_label: str = "V.01",
    tile_path: Callable[[str, bool], Path | None] | None = None,
) -> bytes:
    st = _styles()
    ordered = sorted(items, key=lambda i: (i.priority or "P3", i.clash_code))
    breadcrumb = f"Proyecto · {meta.get('project_name', '')}"

    story: list = []
    story += _cover(meta, ordered, st, final)
    story += _priority_summary(ordered, st)
    story += _check_matrix(ordered, st)
    story += _plates(ordered, output_dir, st, tile_path=tile_path)
    story += _bitacora(ordered, st)
    story += _handover(st)
    if final:
        from app.services.clash_reports.observations_plan_pdf import build_observations_flowables

        obs = build_observations_flowables(ordered, meta, st)
        if obs:
            # _handover already ends on a fresh page; avoid a leading blank page.
            story += [*obs, NextPageTemplate("content"), PageBreak()]
    story += _alias_legend(ordered, st)

    buf = BytesIO()
    doc = _CoordDoc(buf, breadcrumb=breadcrumb, revision_label=revision_label)
    # First page uses the cover template.
    from reportlab.platypus import NextPageTemplate as _NPT

    story.insert(0, _NPT("cover"))
    doc.build(story)
    return buf.getvalue()
