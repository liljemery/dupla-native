"""Render plan sheets for GA-FO-08: PDF/DWG linework + numbered clash callouts."""

from __future__ import annotations

import base64
import json
import math
import re
from pathlib import Path
from typing import Any, Callable

TilePathFn = Callable[[str, bool], Path | None] | None

_MARKER_FILL = "#FFF59D"
_MARKER_STROKE = "#111111"


def resolve_plan_pdf(search_dirs: list[str | Path], dwg_filename: str) -> Path | None:
    """Find a companion PDF for the DWG (same stem or fuzzy token match)."""
    from app.services.clash_reports.companion_pdf import _score_pdf_match, resolve_companion_pdf

    dwg_path = Path(dwg_filename)
    if dwg_path.is_file():
        found = resolve_companion_pdf(dwg_path)
        if found is not None:
            return found

    stem = dwg_path.stem.lower()
    best: tuple[int, Path] | None = None
    for raw in search_dirs:
        root = Path(raw)
        if not root.is_dir():
            continue
        for pdf in root.rglob("*.pdf"):
            score = _score_pdf_match(stem, pdf.stem, dwg_path=dwg_path, pdf_path=pdf)
            if score <= 0:
                continue
            if best is None or score > best[0]:
                best = (score, pdf)
    return best[1] if best else None


def rasterize_pdf_page(pdf_path: str | Path, *, page_index: int = 0, zoom: float = 2.0) -> bytes | None:
    """Rasterize a PDF page to PNG bytes (requires PyMuPDF)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None
    path = Path(pdf_path)
    if not path.is_file():
        return None
    try:
        doc = fitz.open(str(path))
        if page_index >= len(doc):
            page_index = 0
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")
    except Exception:
        return None


def _obs_bounds(obs: dict[str, Any]) -> tuple[float, float, float, float] | None:
    keys = ("bounds_minx_mm", "bounds_miny_mm", "bounds_maxx_mm", "bounds_maxy_mm")
    if all(obs.get(k) is not None for k in keys):
        return (
            float(obs["bounds_minx_mm"]),
            float(obs["bounds_miny_mm"]),
            float(obs["bounds_maxx_mm"]),
            float(obs["bounds_maxy_mm"]),
        )
    raw = obs.get("plan_bounds_mm")
    if isinstance(raw, list) and len(raw) == 4:
        return tuple(float(v) for v in raw)  # type: ignore[return-value]
    cx = float(obs.get("centroid_x_mm") or 0.0)
    cy = float(obs.get("centroid_y_mm") or 0.0)
    if cx or cy:
        pad = 2500.0
        return (cx - pad, cy - pad, cx + pad, cy + pad)
    return None


def _sheet_extent(
    numbered: list[tuple[int, dict[str, Any]]],
    segments: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for x1, y1, x2, y2 in segments:
        xs.extend([x1, x2])
        ys.extend([y1, y2])
    for _, obs in numbered:
        box = _obs_bounds(obs)
        if box:
            xs.extend([box[0], box[2]])
            ys.extend([box[1], box[3]])
        else:
            xs.append(float(obs.get("centroid_x_mm") or 0.0))
            ys.append(float(obs.get("centroid_y_mm") or 0.0))
    if not xs:
        return (0.0, 0.0, 100_000.0, 100_000.0)
    pad = max(max(xs) - min(xs), max(ys) - min(ys), 20_000.0) * 0.06
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def _marker_svg(x: float, y: float, number: int) -> list[str]:
    """Reference-style yellow callout with bold black number."""
    r = 20.0
    return [
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{_MARKER_FILL}" '
        f'stroke="{_MARKER_STROKE}" stroke-width="2.2"/>',
        f'<text x="{x:.1f}" y="{y + 6:.1f}" text-anchor="middle" '
        f'font-family="Helvetica, Arial, sans-serif" font-size="17" font-weight="bold" '
        f'fill="{_MARKER_STROKE}">{number}</text>',
    ]


def render_annotated_plan_svg(
    *,
    numbered: list[tuple[int, dict[str, Any]]],
    dwg_name: str,
    level_id: str | None,
    cache_root: str | Path | None,
    width: float = 1728.0,
    height: float = 1296.0,
    margin: float = 24.0,
    pdf_background_path: str | Path | None = None,
    tile_path: TilePathFn = None,
) -> str:
    """Full-bleed plan sheet matching GA-FO-08 reference (large page + numbered callouts)."""
    del cache_root, dwg_name, level_id
    segments: list[tuple[float, float, float, float]] = []
    xmin, ymin, xmax, ymax = _sheet_extent(numbered, segments)
    world_w = max(xmax - xmin, 1.0)
    world_h = max(ymax - ymin, 1.0)
    scale = min((width - 2 * margin) / world_w, (height - 2 * margin) / world_h)
    ox = margin + ((width - 2 * margin) - world_w * scale) / 2
    oy = margin + ((height - 2 * margin) - world_h * scale) / 2

    def mx(x: float) -> float:
        return ox + (x - xmin) * scale

    def my(y: float) -> float:
        return height - (oy + (y - ymin) * scale)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" height="{height:.0f}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
    ]

    png_bg: bytes | None = None
    if pdf_background_path:
        png_bg = rasterize_pdf_page(pdf_background_path, zoom=2.5)
    if png_bg:
        b64 = base64.b64encode(png_bg).decode("ascii")
        parts.append(
            f'<image x="{margin:.1f}" y="{margin:.1f}" width="{width - 2 * margin:.1f}" '
            f'height="{height - 2 * margin:.1f}" preserveAspectRatio="xMidYMid meet" '
            f'xlink:href="data:image/png;base64,{b64}"/>'
        )
    elif segments:
        parts.append('<g stroke="#1a1a1a" stroke-width="0.45" fill="none" stroke-linecap="round">')
        for x1, y1, x2, y2 in segments[:25000]:
            parts.append(f'<line x1="{mx(x1):.2f}" y1="{my(y1):.2f}" x2="{mx(x2):.2f}" y2="{my(y2):.2f}"/>')
        parts.append("</g>")
    elif tile_path:
        # Fallback: stitch annotated clash tiles when no PDF/viewer background.
        for number, obs in numbered:
            code = str(obs.get("clash_code") or "")
            tile = tile_path(code, True) if code else None
            if tile and tile.is_file():
                try:
                    svg_text = tile.read_text(encoding="utf-8")
                    # Embed tile centered on clash centroid.
                    cx, cy = mx(float(obs.get("centroid_x_mm") or 0.0)), my(float(obs.get("centroid_y_mm") or 0.0))
                    tw, th = 280.0, 200.0
                    inner = re.sub(r"<\?xml[^>]*\?>", "", svg_text)
                    inner = re.sub(r"<!DOCTYPE[^>]*>", "", inner)
                    inner = inner.replace("<svg", f'<svg x="{cx - tw / 2:.1f}" y="{cy - th / 2:.1f}" width="{tw:.0f}" height="{th:.0f}"', 1)
                    parts.append(inner)
                except OSError:
                    pass
    else:
        parts.append(f'<rect x="{margin}" y="{margin}" width="{width - 2 * margin}" height="{height - 2 * margin}" fill="#FAFAFA" stroke="#CCCCCC"/>')

    # Clash zones (light red) + numbered callouts.
    for number, obs in numbered:
        box = _obs_bounds(obs)
        if box:
            x0, y0, x1, y1 = mx(box[0]), my(box[3]), mx(box[2]), my(box[1])
            parts.append(
                f'<rect x="{min(x0,x1):.1f}" y="{min(y0,y1):.1f}" '
                f'width="{abs(x1-x0):.1f}" height="{abs(y1-y0):.1f}" '
                f'fill="#EF444433" stroke="#DC2626" stroke-width="1.5" stroke-dasharray="6,4"/>'
            )
        px = mx(float(obs.get("centroid_x_mm") or 0.0))
        py = my(float(obs.get("centroid_y_mm") or 0.0))
        parts.extend(_marker_svg(px, py, number))

    parts.append("</svg>")
    return "\n".join(parts)
