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


def resolve_viewer_dump(cache_root: str | Path | None, dwg_filename: str) -> dict[str, Any] | None:
    if not cache_root:
        return None
    root = Path(cache_root)
    if not root.is_dir():
        return None
    target = Path(dwg_filename).name.lower()
    for diag_path in root.glob("*.diagnostics.json"):
        try:
            diag = json.loads(diag_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(diag.get("path") or "").lower() != target:
            continue
        key = diag_path.name.split(".diagnostics.json")[0]
        viewer_path = root / f"{key}.viewer.json"
        if viewer_path.is_file():
            try:
                payload = json.loads(viewer_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            if isinstance(payload, dict):
                return payload
    return None


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


def _primitive_segments(primitive: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    kind = str(primitive.get("type") or "").lower()
    if kind == "line":
        return [
            (
                float(primitive["x1"]),
                float(primitive["y1"]),
                float(primitive["x2"]),
                float(primitive["y2"]),
            )
        ]
    if kind == "rect":
        x, y = float(primitive["x"]), float(primitive["y"])
        w, h = float(primitive["width"]), float(primitive["height"])
        return [(x, y, x + w, y), (x + w, y, x + w, y + h), (x + w, y + h, x, y + h), (x, y + h, x, y)]
    if kind == "quad":
        pts = [(float(px), float(py)) for px, py in primitive.get("points") or []]
        if len(pts) < 2:
            return []
        return [(pts[i][0], pts[i][1], pts[(i + 1) % len(pts)][0], pts[(i + 1) % len(pts)][1]) for i in range(len(pts))]
    if kind == "arc":
        cx, cy = float(primitive["cx"]), float(primitive["cy"])
        radius = float(primitive["radius"])
        start, end = float(primitive.get("start", 0.0)), float(primitive.get("end", 2.0 * math.pi))
        steps = max(12, int(abs(end - start) / (math.pi / 18)))
        pts = [(cx + radius * math.cos(start + (end - start) * (k / steps)), cy + radius * math.sin(start + (end - start) * (k / steps))) for k in range(steps + 1)]
        return [(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)]
    return []


def _collect_segments(viewer_dump: dict[str, Any], *, level_id: str | None = None) -> list[tuple[float, float, float, float]]:
    segments: list[tuple[float, float, float, float]] = []
    level_key = str(level_id or "").strip().upper()
    for view in viewer_dump.get("views") or []:
        if not isinstance(view, dict):
            continue
        view_name = str(view.get("name") or "").upper()
        if level_key and level_key not in view_name and view_name not in level_key and level_key not in ("", "SIN NIVEL", "—"):
            continue
        for obj in view.get("objects") or []:
            if not isinstance(obj, dict):
                continue
            for primitive in obj.get("primitives") or []:
                if isinstance(primitive, dict):
                    segments.extend(_primitive_segments(primitive))
    if not segments and level_key:
        return _collect_segments(viewer_dump, level_id=None)
    return segments


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
    viewer = resolve_viewer_dump(cache_root, dwg_name)
    segments = _collect_segments(viewer, level_id=level_id) if viewer else []
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
