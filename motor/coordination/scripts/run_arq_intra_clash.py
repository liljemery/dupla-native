#!/usr/bin/env python3
"""End-to-end intra-discipline clash test on ARQ (SERENA 18).

ARQ is the reference/identity frame (Phase-1 clean), so this needs no common
frame: it detects conflicting-layer overlaps inside ARQ, self-renders the
cleaned plan with real bbox overlays, and emits a GA-FO-08 PDF.

Run (conda python):
    PYTHONPATH=motor /Users/samuelfernandez/anaconda3/bin/python \
        motor/coordination/scripts/run_arq_intra_clash.py

Optional: a JSON config override file as argv[1] to replace the layer pairs.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

from coordination.core.intra_clash import (
    ClashConfig,
    IntraIncident,
    LayerPairRule,
    detect,
    group_incidents,
    prepare_elements,
)
from coordination.reporting.plan_render import render_incident, render_overview

RUN_DIR = Path("var/coord_outputs/serena18_run")
GEOMETRY_PATH = RUN_DIR / "sanitized_geometry" / "ARQ.sanitized.geometry.json"
OUT_DIR = RUN_DIR / "arq_intra_clash"
PROJECT_NAME = "SERENA 18"
MAX_DETAIL_PAGES = 12

# ── GA-FO-08 "LISTA DE CHEQUEO - PLANOS" institutional form metadata ────────
PROCESO_LINE = "GESTIÓN DE ARQUITECTURA Y CONTROL DE PLANOS"
FORM_CODE = "GA-FO-08 (04.2025) V.01"
LDC_NUMBER = "LDC-SERENA18-01"
REVISOR = "Revisión Técnica Dupla"
DISCIPLINE_LABEL = "ARQUITECTURA"
SHEET_CODE = "ARQ-ID"
CORRELACION = "Intra-disciplina (ARQ)"
SEVERITY_ES = {"critical": "CRÍTICA", "major": "MAYOR", "minor": "MENOR"}


# ── EDITABLE CLASH CRITERION ────────────────────────────────────────────────
# Conflicting layer pairs for this interior-design (ID) ARQ plan. Each rule:
#   (layer_a, layer_b, human label, min_overlap_frac of the smaller bbox, weight)
# This plan has no A-WALL / Columnas structural layers (only I-* interior
# layers + a single I-COLUMN), so the default pairs target interior conflicts.
DEFAULT_PAIRS = [
    # Cross-system interferences (genuinely actionable -> escalated)
    LayerPairRule(
        "I-PLUMB-FIXT", "I-FURN", "Aparato sanitario bajo mobiliario (acceso bloqueado)", 0.40, 1.5
    ),
    LayerPairRule("I-EQUIPMENT", "I-FURN", "Equipo solapado con mobiliario", 0.40, 1.3),
    LayerPairRule("I-EQUIPMENT", "I-MILLWORK", "Equipo solapado con carpinteria", 0.40, 1.2),
    LayerPairRule("I-COLUMN", "I-FURN", "Mobiliario sobre columna", 0.30, 1.5),
    LayerPairRule("I-COLUMN", "I-MILLWORK", "Carpinteria sobre columna", 0.30, 1.5),
    # Duplicate-geometry on the same layer (drafting error -> review)
    LayerPairRule("I-WALL", "I-WALL", "Muro duplicado / solapado", 0.70, 1.2),
    LayerPairRule("I-MILLWORK", "I-MILLWORK", "Carpinteria duplicada", 0.70, 1.2),
    LayerPairRule(
        "I-MILLWORK-FULL-HEIGHT",
        "I-MILLWORK-FULL-HEIGHT",
        "Carpinteria full-height duplicada",
        0.70,
        1.2,
    ),
    LayerPairRule(
        "I-MILLWORK", "I-MILLWORK-FULL-HEIGHT", "Carpinteria solapada (full-height vs normal)", 0.60, 1.1
    ),
    # Furniture-on-furniture: on an interior plan this is mostly expected
    # co-location (chairs under tables, sets). Only near-total duplicates are
    # flagged, demoted to minor (weight < 1) so it never dominates the report.
    LayerPairRule("I-FURN", "I-FURN", "Mobiliario solapado (posible duplicado)", 0.85, 0.5),
]

# Layers excluded from conflict logic (annotation, different Z-plane finishes,
# and "hidden" construction lines that legitimately underlie real objects).
EXCLUDE_LAYERS = {
    "I-FURN-HIDDEN",
    "I-MILLWORK-HIDDEN",
    "I-FLOR-FIN",
    "I-FLOOR-FIN",
    "I-FLOR-STRS-SYMB",
    "A-FLOR-STRS-SYMB",
    "I-CLNG",
    "I-CEILING-MEDIA",
    "I-DRAPERY",
    "I-FURN-RUGS",
    "I-WALL-HATCH-EXISTING",
}


def load_config(argv: list[str]) -> ClashConfig:
    if len(argv) > 1 and Path(argv[1]).is_file():
        raw = json.loads(Path(argv[1]).read_text())
        pairs = [
            LayerPairRule(
                p["layer_a"],
                p["layer_b"],
                p.get("label", f"{p['layer_a']} x {p['layer_b']}"),
                float(p.get("min_overlap_frac", 0.5)),
                float(p.get("weight", 1.0)),
            )
            for p in raw.get("pairs", [])
        ]
        return ClashConfig(
            pairs=pairs,
            exclude_layers=set(raw.get("exclude_layers", [])),
            min_abs_area_m2=float(raw.get("min_abs_area_m2", 0.02)),
            incident_cell_m=float(raw.get("incident_cell_m", 3.0)),
            max_element_area_m2=float(raw.get("max_element_area_m2", 20.0)),
        )
    return ClashConfig(pairs=DEFAULT_PAIRS, exclude_layers=EXCLUDE_LAYERS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tiles_dir = OUT_DIR / "tiles"
    tiles_dir.mkdir(exist_ok=True)

    print("=" * 70)
    print("  ARQ INTRA-DISCIPLINE CLASH — SERENA 18 (identity/reference frame)")
    print("=" * 70)

    # ── Checkpoint 1: load + element counts ────────────────────────────────
    geometry = json.loads(GEOMETRY_PATH.read_text())
    config = load_config(sys.argv)
    elements, prep_meta = prepare_elements(
        geometry, quality_allow=config.quality_allow, max_element_area_m2=config.max_element_area_m2
    )

    print("\n[1] LOAD ARQ NORMALIZED GEOMETRY")
    print(f"    source        : {GEOMETRY_PATH}")
    print(f"    factor->meters: {geometry['unit_sanitation']['factor_to_meters']}")
    print(f"    cleaned size  : {geometry['cleanup']['cleaned_outline_size_m']} m")
    print(f"    oversize guard: bbox area > {config.max_element_area_m2} m^2 dropped as unlocalizable container")
    print(
        f"    elements kept : {prep_meta['kept']} physical good+coarse in main cluster "
        f"(skipped {prep_meta['skipped']})"
    )
    layer_hist = collections.Counter(el.layer for el in elements)
    print("    top layers (physical good+coarse, main cluster):")
    for lyr, n in layer_hist.most_common(18):
        mark = "  <- in criterion" if lyr in config.relevant_layers() and lyr not in config.exclude_layers else ""
        print(f"        {n:5d}  {lyr}{mark}")

    print("\n    CLASH CRITERION (editable conflicting layer pairs):")
    for rule in config.pairs:
        print(
            f"        {rule.layer_a:>24}  x  {rule.layer_b:<24}  "
            f"min_overlap>={rule.min_overlap_frac:.0%}  w={rule.weight}  [{rule.label}]"
        )
    print(f"        excluded layers: {sorted(config.exclude_layers)}")

    # ── Checkpoint 2: detect + group ───────────────────────────────────────
    clashes = detect(elements, config)
    incidents = group_incidents(clashes, cell_m=config.incident_cell_m)
    sev_counts = collections.Counter(inc.severity for inc in incidents)
    print("\n[2] DETECT INTRA-ARQ CLASHES")
    print(f"    raw overlaps  : {len(clashes)}")
    print(f"    incidents     : {len(incidents)}  (severity {dict(sev_counts)})")
    pair_hist = collections.Counter(c.rule_label for c in clashes)
    for label, n in pair_hist.most_common():
        print(f"        {n:5d}  {label}")
    print("    top incidents:")
    for inc in incidents[:8]:
        rep = inc.representative
        print(
            f"        {inc.incident_id} [{inc.severity}] {rep.layer_a} x {rep.layer_b} "
            f"@({inc.centroid_m[0]:.1f},{inc.centroid_m[1]:.1f}) "
            f"overlap={rep.overlap_area_m2:.2f} m^2 ({rep.overlap_frac:.0%}) "
            f"handles {rep.handle_a}/{rep.handle_b}  members={len(inc.members)}"
        )

    # persist machine-readable results
    results = {
        "project": PROJECT_NAME,
        "discipline": "ARQ",
        "frame": "identity (reference)",
        "render_source": "self (ezdxf-derived bbox plan; no APS URN for ARQ)",
        "geometry_source": str(GEOMETRY_PATH),
        "elements_analyzed": prep_meta["kept"],
        "elements_skipped": prep_meta["skipped"],
        "max_element_area_m2": config.max_element_area_m2,
        "criterion": [
            {
                "layer_a": r.layer_a,
                "layer_b": r.layer_b,
                "label": r.label,
                "min_overlap_frac": r.min_overlap_frac,
                "weight": r.weight,
            }
            for r in config.pairs
        ],
        "excluded_layers": sorted(config.exclude_layers),
        "raw_overlaps": len(clashes),
        "incident_count": len(incidents),
        "severity_counts": dict(sev_counts),
        "incidents": [inc.as_dict() for inc in incidents],
    }
    (OUT_DIR / "clash_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))

    # ── Checkpoint 3: render ───────────────────────────────────────────────
    print("\n[3] RENDER (self-render: ezdxf-derived bbox plan, identity frame)")
    overview_png = render_overview(
        elements,
        incidents,
        OUT_DIR / "overview.png",
        title=f"{PROJECT_NAME} — ARQ intra-discipline clashes (plan general)",
    )
    print(f"    overview : {overview_png}")
    detail_pngs: list[tuple[IntraIncident, str]] = []
    for inc in incidents[:MAX_DETAIL_PAGES]:
        png = render_incident(
            inc,
            elements,
            tiles_dir / f"{inc.incident_id}.png",
            title=f"{inc.incident_id} [{inc.severity}] — {inc.representative.rule_label}",
        )
        detail_pngs.append((inc, png))
    print(f"    incident tiles: {len(detail_pngs)} (top {MAX_DETAIL_PAGES} of {len(incidents)})")

    # ── Checkpoint 4: GA-FO-08 PDF ─────────────────────────────────────────
    import datetime as _dt

    sheet_title = Path(geometry.get("source_dwg") or "ARQ").stem
    sheet_mtime = ((geometry.get("source_fingerprint") or {}).get("mtime"))
    sheet_date = _dt.datetime.fromtimestamp(sheet_mtime).strftime("%d.%m.%Y") if sheet_mtime else "—"
    meta = {
        "project": PROJECT_NAME,
        "fecha": _dt.date.today().strftime("%d.%m.%Y"),
        "ldc": LDC_NUMBER,
        "revisor": REVISOR,
        "sheet_code": SHEET_CODE,
        "sheet_title": sheet_title,
        "sheet_date": sheet_date,
        "sheet_rev": "REV. 1",
    }
    pdf_path = build_ga_fo_08(
        incidents=incidents,
        overview_png=overview_png,
        detail_pngs=detail_pngs,
        config=config,
        elements_analyzed=prep_meta["kept"],
        sev_counts=sev_counts,
        pair_hist=pair_hist,
        meta=meta,
    )
    print("\n[4] BUILD GA-FO-08 PDF")
    print(f"    pdf : {pdf_path}")

    # ── Checkpoint 5: summary ──────────────────────────────────────────────
    print("\n[5] CHECKPOINT")
    print(f"    PDF path        : {pdf_path}")
    print(f"    incidents       : {len(incidents)} (severity {dict(sev_counts)})")
    print("    render source   : SELF (ezdxf-derived bbox plan; no APS URN for ARQ)")
    print(f"    results json    : {OUT_DIR / 'clash_results.json'}")
    print("    spot-check (boxes sit on real elements — identity frame, model coords):")
    for inc in incidents[:3]:
        rep = inc.representative
        print(
            f"        {inc.incident_id}: overlap bbox {tuple(round(v,2) for v in rep.overlap_bounds_m)} m "
            f"between #{rep.handle_a} ({rep.layer_a}) and #{rep.handle_b} ({rep.layer_b})"
        )


def build_ga_fo_08(
    *,
    incidents: list[IntraIncident],
    overview_png: str,
    detail_pngs: list[tuple[IntraIncident, str]],
    config: ClashConfig,
    elements_analyzed: int,
    sev_counts: collections.Counter,
    pair_hist: collections.Counter,
    meta: dict,
) -> str:
    """GA-FO-08 'LISTA DE CHEQUEO - PLANOS' institutional form.

    Replicates the Grupo Dupla checklist layout: process header, the 7-column
    table (DISCIPLINA / Nº PLANO-TÍTULO / DESCRIPCIÓN / FECHA / REVISIÓN /
    CORRELACIÓN / OBSERVACIONES) with one row per detected incident, the
    project / Nº-de-lista / revisor footer block, and the
    'GA-FO-08 (04.2025) V.01  ·  Página X de Y' confidential footer line.
    The annotated self-rendered plan sheets follow as the plano pages.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as _canvas
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

    page = landscape(A4)
    pw, ph = page
    margin = 12 * mm
    header_h = 26 * mm
    footer_h = 22 * mm
    content_w = pw - 2 * margin

    base = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=base["Normal"], fontName="Helvetica", fontSize=7.5, leading=9.5)
    cell_b = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold")
    head = ParagraphStyle("head", parent=cell, fontName="Helvetica-Bold", fontSize=7.5, textColor=colors.white, alignment=TA_CENTER)
    cap = ParagraphStyle("cap", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#1F2937"))

    # ── header / footer painted on every page ──────────────────────────────
    class FormCanvas(_canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                self._paint(total)
                super().showPage()
            super().save()

        def _paint(self, total):
            # header
            self.setFillColor(colors.HexColor("#1F2937"))
            self.setFont("Helvetica-Bold", 8)
            self.drawString(margin, ph - margin - 2, f"PROCESO: {PROCESO_LINE}")
            self.setFont("Helvetica-Bold", 14)
            self.drawCentredString(pw / 2, ph - margin - 9 * mm, "LISTA DE CHEQUEO - PLANOS")
            self.setFont("Helvetica-Bold", 10)
            self.drawCentredString(pw / 2, ph - margin - 14 * mm, str(meta["project"]))
            self.setFont("Helvetica", 9)
            self.drawCentredString(pw / 2, ph - margin - 18.5 * mm, str(meta["fecha"]))
            self.setStrokeColor(colors.HexColor("#1F2937"))
            self.setLineWidth(0.8)
            self.line(margin, ph - margin - header_h + 2 * mm, pw - margin, ph - margin - header_h + 2 * mm)

            # footer info block
            fy = footer_h
            self.setStrokeColor(colors.HexColor("#9AA3AF"))
            self.setLineWidth(0.5)
            self.rect(margin, fy - 1 * mm, content_w, 12 * mm, stroke=1, fill=0)
            self.line(pw / 2, fy - 1 * mm, pw / 2, fy + 11 * mm)
            self.line(margin, fy + 5 * mm, pw - margin, fy + 5 * mm)
            self.setFillColor(colors.black)
            self.setFont("Helvetica-Bold", 8)
            self.drawString(margin + 2 * mm, fy + 7 * mm, "PROYECTO:")
            self.setFont("Helvetica", 8)
            self.drawString(margin + 24 * mm, fy + 7 * mm, str(meta["project"]))
            self.setFont("Helvetica-Bold", 8)
            self.drawString(pw / 2 + 2 * mm, fy + 7 * mm, "No. LISTA DE CHEQUEO:")
            self.setFont("Helvetica", 8)
            self.drawString(pw / 2 + 40 * mm, fy + 7 * mm, str(meta["ldc"]))
            self.setFont("Helvetica-Bold", 8)
            self.drawString(margin + 2 * mm, fy + 1 * mm, "FECHA:")
            self.setFont("Helvetica", 8)
            self.drawString(margin + 24 * mm, fy + 1 * mm, str(meta["fecha"]))
            self.setFont("Helvetica-Bold", 8)
            self.drawString(pw / 2 + 2 * mm, fy + 1 * mm, "REVISADO POR:")
            self.setFont("Helvetica", 8)
            self.drawString(pw / 2 + 40 * mm, fy + 1 * mm, str(meta["revisor"]))

            # confidential line
            self.setFont("Helvetica", 7)
            self.setFillColor(colors.HexColor("#6B7280"))
            self.drawString(margin, 6 * mm, "Este documento es confidencial")
            self.drawCentredString(pw / 2, 6 * mm, FORM_CODE)
            self.drawRightString(pw - margin, 6 * mm, f"Página {self._pageNumber} de {total}")

    frame_bottom = footer_h + 18 * mm  # clear the PROYECTO / Nº-LISTA footer block
    frame_top = ph - margin - header_h + 2 * mm
    frame = Frame(
        margin, frame_bottom, content_w, frame_top - frame_bottom,
        id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    pdf_path = OUT_DIR / "GA-FO-08_ARQ_intra_clash.pdf"
    doc = BaseDocTemplate(str(pdf_path), pagesize=page, leftMargin=margin, rightMargin=margin,
                          topMargin=margin + header_h, bottomMargin=footer_h)
    doc.addPageTemplates([PageTemplate(id="form", frames=[frame])])

    story: list = []

    # ── checklist table: one row per incident ──────────────────────────────
    headers = [
        "DISCIPLINA",
        "NÚMERO DE PLANO /\nTÍTULO DEL PLANO",
        "DESCRIPCIÓN DE\nPLANOS Y/O CAMBIOS",
        "FECHA DEL\nPLANO",
        "REVISIÓN",
        "CORRELACIÓN CON\nDEMÁS DISCIPLINAS",
        "OBSERVACIONES",
    ]
    rows = [[Paragraph(h.replace("\n", "<br/>"), head) for h in headers]]
    for i, inc in enumerate(incidents, start=1):
        rep = inc.representative
        first = i == 1
        plano = (
            f"{meta['sheet_code']}<br/>{meta['sheet_title']}" if first else "&nbsp;"
        )
        obs = (
            f"<b>{inc.incident_id}</b> [<b>{SEVERITY_ES.get(inc.severity, inc.severity.upper())}</b>] "
            f"{rep.layer_a} ↔ {rep.layer_b}: solape {rep.overlap_area_m2:.2f} m² ({rep.overlap_frac:.0%}) · "
            f"ubicación X≈{inc.centroid_m[0]:.1f} Y≈{inc.centroid_m[1]:.1f} m · "
            f"handles {rep.handle_a}/{rep.handle_b} · {len(inc.members)} elem. en zona"
        )
        rows.append([
            Paragraph(DISCIPLINE_LABEL if first else "&nbsp;", cell_b),
            Paragraph(plano, cell),
            Paragraph(rep.rule_label, cell),
            Paragraph(meta["sheet_date"], cell),
            Paragraph(meta["sheet_rev"], cell),
            Paragraph(CORRELACION, cell),
            Paragraph(obs, cell),
        ])

    col_w = [26 * mm, 34 * mm, 34 * mm, 18 * mm, 16 * mm, 30 * mm, content_w - 158 * mm]
    table = Table(rows, colWidths=col_w, repeatRows=1, splitByRow=1)
    tstyle = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA3AF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6F8")]),
    ]
    story.append(table)

    # ── annotated plan sheets (self-render) ────────────────────────────────
    story.append(NextPageTemplate("form"))
    story.append(PageBreak())
    story.append(Paragraph(f"PLANO: {meta['sheet_code']} — {meta['sheet_title']} (vista general de incidencias)", cap))
    story.append(Spacer(1, 2 * mm))
    story.append(Image(overview_png, width=153 * mm, height=118 * mm))
    story.append(Paragraph(
        "Render propio derivado de ezdxf (bounding-box del modelo limpio, marco identidad ARQ). "
        "No es la lámina APS; geométricamente real.", cell))

    for inc, png in detail_pngs:
        rep = inc.representative
        story.append(PageBreak())
        story.append(Paragraph(
            f"{inc.incident_id} [{SEVERITY_ES.get(inc.severity, inc.severity.upper())}] — {rep.rule_label}", cap))
        story.append(Paragraph(
            f"Capas: {rep.layer_a} ↔ {rep.layer_b} · ubicación ({inc.centroid_m[0]:.2f}, {inc.centroid_m[1]:.2f}) m · "
            f"solape {rep.overlap_area_m2:.2f} m² ({rep.overlap_frac:.0%}) · handles {rep.handle_a}/{rep.handle_b}", cell))
        story.append(Spacer(1, 2 * mm))
        story.append(Image(png, width=125 * mm, height=116 * mm))

    table.setStyle(TableStyle(tstyle))
    doc.build(story, canvasmaker=FormCanvas)
    return str(pdf_path)


if __name__ == "__main__":
    main()
