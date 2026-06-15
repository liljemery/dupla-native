"""Observation plan sheet (GA-FO-08 style) for the final coordination report.

Renders, per level, a schematic plan-region view with numbered revision clouds
placed at each observation's world coordinates and colored by discipline, plus a
"Lista de Chequeo - Planos" table and a number -> observation legend.

The background is schematic (grid + zone footprints), not the real DWG linework;
the cloud-overlay layer is designed so a real full-plan render can be dropped in
behind it later without changing the overlay code.
"""

from __future__ import annotations

import math
import os
import tempfile
from typing import Any, Callable

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer, Table, TableStyle

from app.models.project_clash_item import ProjectClashItem
from app.services.clash_reports.coordination_report_pdf import (
    _CONTENT_W,
    _LS,
    _P,
    PAGE_MARGIN,
    _chip,
    _data_table,
    _esc,
)

# Discipline -> color (matched by an uppercase prefix of the discipline name).
_DISC_COLORS: list[tuple[tuple[str, ...], str]] = [
    (("ARQ",), "#1E88E5"),
    (("EST",), "#E53935"),
    (("MEC", "HVAC", "AIRE"), "#8E24AA"),
    (("ELE", "ELC", "ELECT"), "#FB8C00"),
    (("SAN", "HID", "PLOM", "HIDRO"), "#00897B"),
    (("GAS",), "#6D4C41"),
    (("ESP", "INC", "PCI", "FIRE"), "#C2185B"),
]
_DISC_FALLBACK = "#5E35B1"
_AVAIL_H = _LS[1] - 2 * PAGE_MARGIN - 22 * mm  # usable height below header/footer


def _norm(text: Any) -> str:
    return str(text or "").strip().upper()


def discipline_color(discipline: str | None) -> str:
    key = _norm(discipline)
    for prefixes, color in _DISC_COLORS:
        if any(key.startswith(p) for p in prefixes):
            return color
    return _DISC_FALLBACK


def _obs_text(item: ProjectClashItem) -> str:
    return (item.observation or item.recommended_action or "Revisar el par en planta.").strip()


# --- revision cloud + sheet SVG ------------------------------------------
def _cloud_path(x0: float, y0: float, x1: float, y1: float, bump: float = 13.0) -> str:
    """Scalloped 'revision cloud' path around the rectangle (x0,y0)-(x1,y1)."""
    pts: list[tuple[float, float]] = []

    def edge(ax, ay, bx, by):
        dist = math.hypot(bx - ax, by - ay)
        n = max(1, int(dist / bump))
        for k in range(n):
            t = k / n
            pts.append((ax + (bx - ax) * t, ay + (by - ay) * t))

    edge(x0, y0, x1, y0)
    edge(x1, y0, x1, y1)
    edge(x1, y1, x0, y1)
    edge(x0, y1, x0, y0)
    if not pts:
        return ""
    r = bump * 0.62
    d = [f"M {pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(1, len(pts) + 1):
        px, py = pts[i % len(pts)]
        # sweep flag 1 -> arcs bulge outward for a clockwise perimeter
        d.append(f"A {r:.1f},{r:.1f} 0 0 1 {px:.1f},{py:.1f}")
    d.append("Z")
    return " ".join(d)


def _centroid(it: ProjectClashItem) -> tuple[float, float]:
    cx = it.centroid_x_mm
    cy = it.centroid_y_mm
    if cx is None or cy is None:
        bx0 = it.bounds_minx_mm or 0.0
        by0 = it.bounds_miny_mm or 0.0
        bx1 = it.bounds_maxx_mm or 0.0
        by1 = it.bounds_maxy_mm or 0.0
        cx = (bx0 + bx1) / 2 if cx is None else cx
        cy = (by0 + by1) / 2 if cy is None else cy
    return float(cx), float(cy)


def render_observations_sheet_svg(numbered: list[tuple[int, ProjectClashItem]]) -> str:
    """SVG of a level: schematic plan extent + small numbered clouds at each obs.

    Clouds are anchored at each clash centroid and kept small (markup-style); the
    sheet extent comes from the spread of the centroids so observations read as
    distinct localized clouds, not one region-sized blob.
    """
    W, H, margin = 1400.0, 800.0, 70.0
    cxs = [_centroid(it)[0] for _, it in numbered] or [0.0]
    cys = [_centroid(it)[1] for _, it in numbered] or [0.0]
    span_x = max(cxs) - min(cxs)
    span_y = max(cys) - min(cys)
    # Floor the extent so a single/clustered set of points still gets a sheet.
    base = max(span_x, span_y, 8000.0)
    pad = base * 0.18
    cxm = (max(cxs) + min(cxs)) / 2
    cym = (max(cys) + min(cys)) / 2
    half = base / 2 + pad
    wminx, wmaxx = cxm - half, cxm + half
    wminy, wmaxy = cym - half, cym + half
    world_w, world_h = wmaxx - wminx, wmaxy - wminy
    scale = min((W - 2 * margin) / world_w, (H - 2 * margin) / world_h)
    ox = margin + ((W - 2 * margin) - world_w * scale) / 2
    oy = margin + ((H - 2 * margin) - world_h * scale) / 2

    def mx(x: float) -> float:
        return ox + (x - wminx) * scale

    def my(y: float) -> float:
        return H - (oy + (y - wminy) * scale)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        '<g stroke="#EEF0F2" stroke-width="0.8">',
    ]
    for i in range(1, 14):
        gx = margin + (W - 2 * margin) * i / 14
        parts.append(f'<line x1="{gx:.0f}" y1="{margin:.0f}" x2="{gx:.0f}" y2="{H - margin:.0f}"/>')
    for i in range(1, 9):
        gy = margin + (H - 2 * margin) * i / 9
        parts.append(f'<line x1="{margin:.0f}" y1="{gy:.0f}" x2="{W - margin:.0f}" y2="{gy:.0f}"/>')
    parts.append("</g>")
    parts.append(
        f'<rect x="{margin:.0f}" y="{margin:.0f}" width="{W - 2 * margin:.0f}" height="{H - 2 * margin:.0f}" '
        f'fill="none" stroke="#C9CED4" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="{W / 2:.0f}" y="{H - 30:.0f}" text-anchor="middle" '
        f'font-family="Helvetica, Arial, sans-serif" font-size="13" fill="#B6BCC4">'
        f'Extensión esquemática del plano · ubicación relativa de observaciones</text>'
    )

    cloud_max_w = (W - 2 * margin) * 0.085
    cloud_max_h = (H - 2 * margin) * 0.11
    for number, it in numbered:
        px, py = mx(_centroid(it)[0]), my(_centroid(it)[1])
        # cloud size from the clash footprint, clamped to a markup-sized range
        bw = abs((it.bounds_maxx_mm or 0.0) - (it.bounds_minx_mm or 0.0)) * scale
        bh = abs((it.bounds_maxy_mm or 0.0) - (it.bounds_miny_mm or 0.0)) * scale
        hw = min(max(bw / 2, 30.0), cloud_max_w)
        hh = min(max(bh / 2, 24.0), cloud_max_h)
        cx0, cy0, cx1, cy1 = px - hw, py - hh, px + hw, py + hh
        color = discipline_color(it.discipline_a)
        parts.append(
            f'<path d="{_cloud_path(cx0, cy0, cx1, cy1)}" fill="{color}26" stroke="{color}" stroke-width="2.4"/>'
        )
        bx, by = cx0 + 2, cy0 + 2
        parts.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="12" fill="{color}" stroke="#FFFFFF" stroke-width="1.6"/>')
        parts.append(
            f'<text x="{bx:.1f}" y="{by + 4:.1f}" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="13" font-weight="bold" fill="#FFFFFF">{number}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


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
    scale = min(max_w / drawing.width, max_h / drawing.height)
    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)
    return drawing


# --- tables ---------------------------------------------------------------
def _disc_legend(items, st):
    seen: dict[str, str] = {}
    for it in items:
        for disc in (it.discipline_a, it.discipline_b):
            if disc and disc not in seen:
                seen[disc] = discipline_color(disc)
    if not seen:
        return []
    row = [_chip(d, colors.HexColor(c), st) for d, c in seen.items()]
    t = Table([row], colWidths=[min(40 * mm, _CONTENT_W / max(len(row), 1))] * len(row))
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    return [t, Spacer(1, 4)]


def _ldc_header_table(meta, st):
    from reportlab.platypus import Table, TableStyle

    rows = [
        [_P("PROYECTO", "cell_head", st), _P(meta.get("project_name", ""), "cell", st),
         _P("No. LISTA DE CHEQUEO", "cell_head", st), _P(f"LDC-{_norm(meta.get('folder_name')) or 'PLANOS'}", "cell", st)],
        [_P("FECHA", "cell_head", st), _P(meta.get("run_date", ""), "cell", st),
         _P("REVISADO POR", "cell_head", st), _P(meta.get("user_display", ""), "cell", st)],
    ]
    t = Table(rows, colWidths=[40 * mm, _CONTENT_W / 2 - 40 * mm, 45 * mm, _CONTENT_W / 2 - 45 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#cfd4da")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#cfd4da")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9aa3af")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _ldc_table(numbered, st):
    by_plan: dict[str, list[tuple[int, ProjectClashItem]]] = {}
    for number, it in numbered:
        by_plan.setdefault(it.dwg_a or "—", []).append((number, it))
    rows = []
    for plan, group in by_plan.items():
        first = group[0][1]
        corr = sorted({g.discipline_b for _, g in group if g.discipline_b})
        # Escaped content joined with literal <br/> so the cell wraps per bullet.
        bullets = "<br/>".join(f"{n}. {_esc(_obs_text(g))}" for n, g in group)
        rows.append([
            _P(first.discipline_a or "—", "cell", st),
            _P(plan, "cell", st),
            _P(first.level_id or "—", "cell", st),
            _P(", ".join(corr) or "—", "cell", st),
            Paragraph(bullets, st["cell"]),
        ])
    return _data_table(
        ["DISCIPLINA", "PLANO", "NIVEL", "CORRELACIÓN", "OBSERVACIONES"],
        rows,
        [28 * mm, 50 * mm, 22 * mm, 40 * mm, 100 * mm],
        st,
    )


def _legend_table(numbered, st):
    rows = [[
        str(n),
        _chip(it.discipline_a or "—", colors.HexColor(discipline_color(it.discipline_a)), st),
        it.level_id or "—",
        it.clash_code,
        _P(_obs_text(it), "cell", st),
    ] for n, it in numbered]
    return _data_table(
        ["Nº", "DISCIPLINA", "NIVEL", "CÓDIGO", "OBSERVACIÓN"],
        rows,
        [12 * mm, 30 * mm, 22 * mm, 28 * mm, 110 * mm],
        st,
    )


def build_observations_flowables(items, meta, st) -> list:
    """Flowables for the observation-plan section (appended to the final report)."""
    if not items:
        return []
    ordered = sorted(items, key=lambda i: (i.level_id or "", i.priority or "P3", i.clash_code))
    numbered_all = list(enumerate(ordered, start=1))

    flow: list = [
        _P("Lista de chequeo — planos y observaciones", "h2", st),
        _P("Gestión de arquitectura y control de planos · GA-FO-08 · observaciones numeradas por plano.", "small", st),
        Spacer(1, 4),
        _ldc_header_table(meta, st),
        Spacer(1, 4),
        _ldc_table(numbered_all, st),
    ]

    by_level: dict[str, list[tuple[int, ProjectClashItem]]] = {}
    for number, it in numbered_all:
        by_level.setdefault(it.level_id or "Sin nivel", []).append((number, it))

    for level, numbered in by_level.items():
        svg = render_observations_sheet_svg(numbered)
        drawing = _sheet_drawing(svg, _CONTENT_W, 360.0)
        sheet: list = [
            _P(f"Plano de observaciones — {level}", "h2", st),
            _P("Nubes de revisión coloreadas por disciplina, numeradas según la leyenda inferior.", "small", st),
            Spacer(1, 4),
        ]
        sheet += _disc_legend([it for _, it in numbered], st)
        sheet.append(
            drawing if drawing is not None
            else _P("Vista de plano no disponible (svglib no instalado).", "small", st)
        )
        # Keep the heading, legend and plan on one page; the index table follows.
        flow += [PageBreak(), KeepTogether(sheet), Spacer(1, 6), _legend_table(numbered, st)]

    return flow
