"""Generate plan-view SVG tiles when the coordination run did not produce them."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _esc(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_placeholder_tile_svg(incident: dict[str, Any], *, annotated: bool) -> str:
    rep = incident.get("representative_conflict") or {}
    bounds = incident.get("plan_bounds_mm") or rep.get("plan_intersection_bounds_mm") or []
    centroid = incident.get("plan_centroid_mm") or rep.get("plan_intersection_centroid_mm") or []

    if len(bounds) == 4:
        minx, miny, maxx, maxy = (_f(b) for b in bounds)
    else:
        minx, miny, maxx, maxy = 0.0, 0.0, 1000.0, 1000.0
    if maxx <= minx:
        maxx = minx + 1000.0
    if maxy <= miny:
        maxy = miny + 1000.0
    if len(centroid) == 2:
        cx, cy = _f(centroid[0]), _f(centroid[1])
    else:
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    if not (minx <= cx <= maxx and miny <= cy <= maxy):
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0

    width, height = 800.0, 586.0
    margin = 70.0
    world_w = maxx - minx
    world_h = maxy - miny
    pad = max(world_w, world_h) * 0.45
    wx0, wy0, wx1, wy1 = minx - pad, miny - pad, maxx + pad, maxy + pad
    scale = min((width - 2 * margin) / (wx1 - wx0), (height - 2 * margin) / (wy1 - wy0))

    def mx(x: float) -> float:
        return margin + (x - wx0) * scale

    def my(y: float) -> float:
        return height - (margin + (y - wy0) * scale)

    def rect_points(x0: float, y0: float, x1: float, y1: float) -> str:
        pts = [(mx(x0), my(y0)), (mx(x1), my(y0)), (mx(x1), my(y1)), (mx(x0), my(y1))]
        return " ".join(f"{px:.2f},{py:.2f}" for px, py in pts)

    off = max(world_w, world_h) * 0.18
    a_box = rect_points(minx - off, miny - off, maxx + off * 0.3, maxy + off * 0.3)
    b_box = rect_points(minx - off * 0.3, miny - off * 0.3, maxx + off, maxy + off)
    clash_box = rect_points(minx, miny, maxx, maxy)
    ccx, ccy = mx(cx), my(cy)

    disc_a = _esc(rep.get("discipline_a") or "DWG A")
    disc_b = _esc(rep.get("discipline_b") or "DWG B")
    incident_id = _esc(incident.get("incident_id") or "incident")
    level_id = _esc(incident.get("level_id") or "—")
    area = _f(rep.get("plan_intersection_area_mm2"))
    depth = rep.get("overlap_depth_z_mm")
    depth_txt = f"{_f(depth):.0f} mm" if depth is not None else "—"

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
    ]
    grid = ['<g stroke="#E5E7EB" stroke-width="0.6">']
    for i in range(1, 8):
        gx = margin + (width - 2 * margin) * i / 8
        gy = margin + (height - 2 * margin) * i / 8
        grid.append(f'<line x1="{gx:.1f}" y1="{margin:.1f}" x2="{gx:.1f}" y2="{height - margin:.1f}"/>')
        grid.append(f'<line x1="{margin:.1f}" y1="{gy:.1f}" x2="{width - margin:.1f}" y2="{gy:.1f}"/>')
    grid.append("</g>")
    parts.extend(grid)
    parts.append(f'<polygon points="{a_box}" fill="#3B82F622" stroke="#3B82F6" stroke-width="1.4"/>')
    parts.append(f'<polygon points="{b_box}" fill="#F59E0B22" stroke="#F59E0B" stroke-width="1.4"/>')
    parts.append(f'<polygon points="{clash_box}" fill="#EF444433" stroke="#EF4444" stroke-width="2.4"/>')
    parts.append(f'<circle cx="{ccx:.2f}" cy="{ccy:.2f}" r="5" fill="#EF4444"/>')
    parts.append(
        f'<line x1="{ccx - 11:.2f}" y1="{ccy:.2f}" x2="{ccx + 11:.2f}" y2="{ccy:.2f}" '
        f'stroke="#991B1B" stroke-width="1.2"/>'
    )
    parts.append(
        f'<line x1="{ccx:.2f}" y1="{ccy - 11:.2f}" x2="{ccx:.2f}" y2="{ccy + 11:.2f}" '
        f'stroke="#991B1B" stroke-width="1.2"/>'
    )
    if annotated:
        parts.append(
            '<g font-family="Helvetica, Arial, sans-serif">'
            f'<text x="16" y="28" font-size="15" font-weight="bold" fill="#111827">{incident_id}</text>'
            f'<text x="16" y="48" font-size="12" fill="#374151">Nivel {level_id} · '
            f'área {area:,.0f} mm² · solape {depth_txt}</text>'
            "</g>"
        )
        ly = height - 64
        parts.append(
            f'<g font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#374151">'
            f'<rect x="14" y="{ly - 16:.0f}" width="14" height="10" fill="#3B82F622" stroke="#3B82F6"/>'
            f'<text x="34" y="{ly - 7:.0f}">{disc_a}</text>'
            f'<rect x="14" y="{ly + 2:.0f}" width="14" height="10" fill="#F59E0B22" stroke="#F59E0B"/>'
            f'<text x="34" y="{ly + 11:.0f}">{disc_b}</text>'
            f'<rect x="14" y="{ly + 20:.0f}" width="14" height="10" fill="#EF444433" stroke="#EF4444"/>'
            f'<text x="34" y="{ly + 29:.0f}">Zona de conflicto</text>'
            f"</g>"
        )
        parts.append(
            f'<text x="{width - 14:.0f}" y="{height - 14:.0f}" text-anchor="end" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="9" fill="#9CA3AF">'
            f"DUPLA · vista de planta</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts)


def ensure_placeholder_tiles(tiles_root: Path, primary_payload: dict[str, Any]) -> int:
    """Write missing ``tiles/*.svg`` under ``tiles_root/tiles/``. Returns files written."""
    tiles_dir = tiles_root / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for inc in primary_payload.get("incidents") or []:
        if not isinstance(inc, dict):
            continue
        incident_id = str(inc.get("incident_id") or "").strip()
        if not incident_id:
            continue
        annotated_path = tiles_dir / f"{incident_id}_annotated.svg"
        plain_path = tiles_dir / f"{incident_id}.svg"
        if not annotated_path.is_file():
            annotated_path.write_text(
                render_placeholder_tile_svg(inc, annotated=True), encoding="utf-8"
            )
            written += 1
        if not plain_path.is_file():
            plain_path.write_text(render_placeholder_tile_svg(inc, annotated=False), encoding="utf-8")
            written += 1
    return written
