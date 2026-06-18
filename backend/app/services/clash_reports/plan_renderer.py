"""High-resolution 2D plan renderer for the checklist PDF (B2 path).

APS only exposes a 400px-capped thumbnail and no PDF derivative for DWG, so we
rasterize the plan ourselves from the geometry the Dupla motor extracts
(``plan_geometry.json``: per-file element footprints in CAD millimetres) and draw
the clash zones on top in the same coordinate space. Output is a full-page JPEG
at ~200 DPI (letter landscape) with baked-in header/legend strips.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Letter landscape aspect (792 x 612 pt = 11 x 8.5 in). At ~218 DPI:
CANVAS_W = 2400
CANVAS_H = 1854
HEADER_H = 96
LEGEND_H = 84
MARGIN = 48

_BG = (255, 255, 255)
_STRIP_BG = (26, 26, 26)
_STRIP_FG = (255, 255, 255)
_GRID = (235, 235, 235)
_ELEMENT_DEFAULT = (110, 120, 135)

_DISCIPLINE_COLORS = {
    "ARQUITECTURA": (59, 130, 246),
    "ESTRUCTURA": (139, 92, 246),
    "FONTANERIA": (16, 185, 129),
    "SANITARIO": (6, 182, 212),
    "SANITARIOS": (6, 182, 212),
    "ELECTRICO": (245, 158, 11),
    "ELECTRICIDAD": (245, 158, 11),
    "ELECTRICA": (245, 158, 11),
    "CLIMATIZACION": (236, 72, 153),
    "MECANICA": (236, 72, 153),
    "GAS": (239, 68, 68),
}

_PRIORITY_COLORS = {
    "critical": (220, 50, 50),
    "high": (220, 150, 50),
}
_PRIORITY_DEFAULT = (220, 220, 50)


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1 has no size kwarg
        return ImageFont.load_default()


def _discipline_color(discipline: str | None) -> tuple[int, int, int]:
    return _DISCIPLINE_COLORS.get(str(discipline or "").strip().upper(), _ELEMENT_DEFAULT)


def render_plan_image(
    *,
    file_geometry: dict[str, Any],
    clash_zones: list[dict[str, Any]],
    header_text: str,
    legend_left: str,
    legend_right: str = "GrupoDupla / Dupla Constructora",
) -> bytes | None:
    """Render one full-page plan JPEG from element footprints + clash zones.

    file_geometry: {"discipline", "extents_mm"[4], "elements":[{"discipline","footprint_mm"}]}
    clash_zones: [{"bounds_mm"[4], "centroid_mm"[2], "clash_type"}] for this file.
    Returns JPEG bytes or None if there is nothing renderable.
    """
    elements = file_geometry.get("elements") or []
    extents = file_geometry.get("extents_mm")
    if not extents or len(extents) != 4:
        # Derive extents from clash bounds when geometry is missing.
        extents = _extents_from_zones(clash_zones)
    if not extents or len(extents) != 4:
        return None

    ex_min_x, ex_min_y, ex_max_x, ex_max_y = (float(v) for v in extents)
    span_x = ex_max_x - ex_min_x
    span_y = ex_max_y - ex_min_y
    if span_x <= 0 or span_y <= 0:
        return None

    # Pad extents 3% so geometry/clashes don't touch the edges.
    pad_x, pad_y = span_x * 0.03, span_y * 0.03
    ex_min_x, ex_max_x = ex_min_x - pad_x, ex_max_x + pad_x
    ex_min_y, ex_max_y = ex_min_y - pad_y, ex_max_y + pad_y
    span_x, span_y = ex_max_x - ex_min_x, ex_max_y - ex_min_y

    plot_x0, plot_y0 = MARGIN, HEADER_H + MARGIN
    plot_w = CANVAS_W - 2 * MARGIN
    plot_h = CANVAS_H - HEADER_H - LEGEND_H - 2 * MARGIN
    # Preserve aspect ratio (fit) and center within the plot area.
    scale = min(plot_w / span_x, plot_h / span_y)
    draw_w, draw_h = span_x * scale, span_y * scale
    off_x = plot_x0 + (plot_w - draw_w) / 2
    off_y = plot_y0 + (plot_h - draw_h) / 2

    def to_px(mx: float, my: float) -> tuple[float, float]:
        px = off_x + (mx - ex_min_x) * scale
        py = off_y + (ex_max_y - my) * scale  # flip Y (CAD up vs image down)
        return px, py

    img = Image.new("RGB", (CANVAS_W, CANVAS_H), _BG)
    draw = ImageDraw.Draw(img, "RGBA")

    # Element footprints
    for el in elements:
        footprint = el.get("footprint_mm") or []
        if len(footprint) < 2:
            continue
        color = _discipline_color(el.get("discipline") or file_geometry.get("discipline"))
        pts = [to_px(float(x), float(y)) for x, y in footprint]
        if len(pts) >= 3:
            draw.polygon(pts, outline=color + (200,), fill=color + (40,))
        else:
            draw.line(pts, fill=color + (220,), width=2)

    # Clash zones (semi-transparent rectangles + crosshair + label)
    label_count = 0
    for zone in clash_zones:
        bounds = zone.get("bounds_mm")
        centroid = zone.get("centroid_mm")
        if not bounds or len(bounds) != 4:
            continue
        clash_type = str(zone.get("clash_type") or "").upper()
        color = _PRIORITY_COLORS["critical"] if clash_type == "HARD" else _PRIORITY_DEFAULT
        x0, y0 = to_px(float(bounds[0]), float(bounds[1]))
        x1, y1 = to_px(float(bounds[2]), float(bounds[3]))
        rx0, ry0 = min(x0, x1), min(y0, y1)
        rx1, ry1 = max(x0, x1), max(y0, y1)
        min_size = max(24, CANVAS_W // 80)
        if rx1 - rx0 < min_size:
            cx = (rx0 + rx1) / 2
            rx0, rx1 = cx - min_size / 2, cx + min_size / 2
        if ry1 - ry0 < min_size:
            cy = (ry0 + ry1) / 2
            ry0, ry1 = cy - min_size / 2, cy + min_size / 2
        draw.rectangle([rx0, ry0, rx1, ry1], fill=color + (90,), outline=color + (255,), width=3)
        # Label only the first zones to avoid clutter on dense plans.
        if label_count < 40:
            label_count += 1
            draw.text((rx0 + 6, ry0 + 4), f"C-{label_count:03d}", fill=color + (255,), font=_font(30))
        if centroid and len(centroid) == 2:
            cx, cy = to_px(float(centroid[0]), float(centroid[1]))
            r = 18
            draw.line([(cx - r, cy), (cx + r, cy)], fill=color + (255,), width=2)
            draw.line([(cx, cy - r), (cx, cy + r)], fill=color + (255,), width=2)

    _draw_strips(img, draw, header_text, legend_left, legend_right)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, dpi=(218, 218))
    return buf.getvalue()


def _draw_strips(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    header_text: str,
    legend_left: str,
    legend_right: str,
) -> None:
    # Top header strip
    draw.rectangle([0, 0, CANVAS_W, HEADER_H], fill=_STRIP_BG)
    draw.text((MARGIN, HEADER_H // 2 - 22), header_text, fill=_STRIP_FG, font=_font(44))
    # Bottom legend strip
    draw.rectangle([0, CANVAS_H - LEGEND_H, CANVAS_W, CANVAS_H], fill=_STRIP_BG)
    ly = CANVAS_H - LEGEND_H // 2 - 18
    draw.text((MARGIN, ly), legend_left, fill=_STRIP_FG, font=_font(36))
    right_font = _font(34)
    rw = draw.textlength(legend_right, font=right_font)
    draw.text((CANVAS_W - MARGIN - rw, ly), legend_right, fill=_STRIP_FG, font=right_font)


def _extents_from_zones(clash_zones: list[dict[str, Any]]) -> list[float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for zone in clash_zones:
        b = zone.get("bounds_mm")
        if b and len(b) == 4:
            xs.extend([float(b[0]), float(b[2])])
            ys.extend([float(b[1]), float(b[3])])
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def load_plan_geometry(geometry_path: str | Path) -> dict[str, Any]:
    """Load plan_geometry.json mapping basename -> file geometry. Empty on failure."""
    path = Path(geometry_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read plan_geometry.json: %s", exc)
        return {}
    files = data.get("files") or {}
    return {Path(name).name: geo for name, geo in files.items()}


def load_clash_zones_by_file(
    report_path: str | Path, max_per_file: int = 400
) -> dict[str, list[dict[str, Any]]]:
    """Group clash zones (bounds/centroid/type) by basename from clash_project_report.json."""
    path = Path(report_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read clash_project_report.json: %s", exc)
        return {}
    zones: dict[str, list[dict[str, Any]]] = {}
    for conflict in data.get("conflicts") or []:
        bounds = conflict.get("plan_intersection_bounds_mm")
        if not bounds or len(bounds) != 4:
            continue
        zone = {
            "bounds_mm": bounds,
            "centroid_mm": conflict.get("plan_intersection_centroid_mm"),
            "clash_type": conflict.get("clash_type"),
        }
        for ref in conflict.get("source_refs") or []:
            fname = Path(str(ref).split("|", 1)[0]).name
            bucket = zones.setdefault(fname, [])
            if len(bucket) < max_per_file:
                bucket.append(zone)
    return zones
