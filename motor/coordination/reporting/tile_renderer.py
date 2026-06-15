"""Generador de tiles SVG georreferenciados para visualización de clashes."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shapely.geometry import MultiPolygon, Polygon, box

from coordination.core.clash import ClashConflict, ClashIncident
from coordination.core.models_25d import Element25D

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from coordination.semantic.vision_validator import VisionTileResult


@dataclass
class TileSpec:
    tile_id: str
    bbox_cad_mm: tuple[float, float, float, float]
    level_id: str
    source_files: list[str]
    incident_id: str | None = None
    semantic_group_id: str | None = None


@dataclass
class RenderedTile:
    tile_id: str
    svg_content: str
    bbox_cad_mm: tuple[float, float, float, float]
    width_px: int
    height_px: int
    scale_mm_per_px: float
    elements_in_tile: list[str]
    texts_in_tile: list[dict[str, Any]]
    incident_id: str | None = None


DISCIPLINE_COLORS = {
    "ARQUITECTURA": "#3B82F6",
    "ESTRUCTURA": "#8B5CF6",
    "FONTANERIA": "#10B981",
    "ELECTRICO": "#F59E0B",
    "SANITARIO": "#06B6D4",
    "GAS": "#EF4444",
    "CLIMATIZACION": "#EC4899",
}
DEFAULT_COLOR = "#6B7280"
CLASH_ZONE_FILL = "#EF4444"
CLASH_ZONE_OPACITY = 0.3
TEXT_LABEL_COLOR = "#1F2937"
GRID_COLOR = "#E5E7EB"
BG_COLOR = "#FFFFFF"
HIGHLIGHT_STROKE_WIDTH = 2.5
NORMAL_STROKE_WIDTH = 0.8
SEVERITY_COLORS = {
    "critical": "#DC2626",
    "major": "#D97706",
    "minor": "#2563EB",
    "noise": "#6B7280",
}
CONFIDENCE_COLORS = {
    "high": "#16A34A",
    "medium": "#CA8A04",
    "low": "#6B7280",
}


def compute_tile_bbox(incident: ClashIncident, padding_factor: float = 0.3) -> tuple[float, float, float, float]:
    """Return an expanded CAD bbox around an incident."""
    min_x, min_y, max_x, max_y = (float(value) for value in incident.plan_bounds_mm)
    width = max_x - min_x
    height = max_y - min_y
    cx, cy = incident.plan_centroid_mm
    if width <= 0:
        width = 2000.0
        min_x = float(cx) - width / 2.0
        max_x = float(cx) + width / 2.0
    if height <= 0:
        height = 2000.0
        min_y = float(cy) - height / 2.0
        max_y = float(cy) + height / 2.0
    pad_x = width * padding_factor
    pad_y = height * padding_factor
    return (min_x - pad_x, min_y - pad_y, max_x + pad_x, max_y + pad_y)


def collect_elements_in_bbox(
    all_elements: list[Element25D],
    bbox_mm: tuple[float, float, float, float],
    level_id: str | None = None,
) -> list[Element25D]:
    """Collect valid element footprints intersecting a CAD bbox."""
    tile_box = box(*bbox_mm)
    found: list[Element25D] = []
    for element in all_elements:
        if level_id is not None and not _element_matches_level(element, level_id):
            continue
        try:
            polygon = _element_polygon(element)
            if polygon is not None and polygon.intersects(tile_box):
                found.append(element)
        except Exception as exc:
            logger.debug("Skipping invalid footprint for tile collection: %s (%s)", element.id, exc)
    return found


def _cad_to_svg(x_cad: float, y_cad: float, min_x: float, max_y: float, scale: float) -> tuple[float, float]:
    sx = (x_cad - min_x) * scale
    sy = (max_y - y_cad) * scale
    return (sx, sy)


def _polygon_to_svg_points(
    coords: list[tuple[float, float]],
    min_x: float,
    max_y: float,
    scale: float,
) -> str:
    points = [_cad_to_svg(float(x), float(y), min_x, max_y, scale) for x, y in coords]
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _escape_svg(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_tile_svg(
    tile_spec: TileSpec,
    elements: list[Element25D],
    texts: list[Any],
    clash_conflicts: list[ClashConflict] | None = None,
    width_px: int = 800,
) -> RenderedTile:
    """Render one georeferenced SVG tile."""
    min_x, min_y, max_x, max_y = tile_spec.bbox_cad_mm
    cad_width = max(max_x - min_x, 1.0)
    cad_height = max(max_y - min_y, 1.0)
    scale = width_px / cad_width
    height_px = max(1, int(round(cad_height * scale)))
    clash_ids = _clash_element_ids(clash_conflicts or [])
    text_payloads = _normalize_texts(texts, elements)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width_px} {height_px}" width="{width_px}" height="{height_px}">',
        f'<rect width="100%" height="100%" fill="{BG_COLOR}"/>',
    ]
    parts.extend(_render_grid(min_x, min_y, max_x, max_y, scale, width_px, height_px))

    for element in elements:
        polygon = _element_polygon(element)
        if polygon is None:
            continue
        color = _discipline_color(element)
        stroke_width = HIGHLIGHT_STROKE_WIDTH if element.id in clash_ids else NORMAL_STROKE_WIDTH
        points = _polygon_to_svg_points(list(polygon.exterior.coords), min_x, max_y, scale)
        parts.append(
            f'<polygon points="{points}" fill="{color}20" stroke="{color}" '
            f'stroke-width="{stroke_width}" vector-effect="non-scaling-stroke"/>'
        )

    parts.extend(_render_clash_zones(clash_conflicts or [], elements, min_x, max_y, scale))
    parts.extend(_render_text_labels(text_payloads, min_x, max_y, scale))
    parts.extend(_render_legend(tile_spec, elements, width_px, height_px, scale))
    parts.extend(_render_scale_bar(min_x, min_y, max_y, scale, height_px))
    parts.append("</svg>")

    return RenderedTile(
        tile_id=tile_spec.tile_id,
        svg_content="\n".join(parts),
        bbox_cad_mm=tile_spec.bbox_cad_mm,
        width_px=width_px,
        height_px=height_px,
        scale_mm_per_px=1.0 / scale,
        elements_in_tile=[element.id for element in elements],
        texts_in_tile=text_payloads,
        incident_id=tile_spec.incident_id,
    )


def render_incident_tile(
    incident: ClashIncident,
    all_elements: list[Element25D],
    all_texts: list[Any] | None = None,
    padding_factor: float = 0.3,
    width_px: int = 800,
) -> RenderedTile:
    """Render the SVG tile for one clash incident."""
    bbox = compute_tile_bbox(incident, padding_factor=padding_factor)
    elements = collect_elements_in_bbox(all_elements, bbox, level_id=incident.level_id)
    conflicts = _incident_conflicts(incident)
    texts = _texts_in_bbox(all_texts or [], bbox)
    tile_spec = TileSpec(
        tile_id=incident.incident_id,
        bbox_cad_mm=bbox,
        level_id=incident.level_id,
        source_files=list(incident.file_pair),
        incident_id=incident.incident_id,
    )
    return render_tile_svg(
        tile_spec=tile_spec,
        elements=elements,
        texts=texts,
        clash_conflicts=conflicts,
        width_px=width_px,
    )


def render_all_incident_tiles(
    incidents: list[ClashIncident],
    all_elements: list[Element25D],
    output_dir: str | Path,
    all_texts: list[Any] | None = None,
    width_px: int = 800,
) -> list[RenderedTile]:
    """Render and write SVG tiles for all incidents."""
    tiles_dir = Path(output_dir) / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[RenderedTile] = []
    for index, incident in enumerate(incidents, start=1):
        tile = render_incident_tile(
            incident=incident,
            all_elements=all_elements,
            all_texts=all_texts,
            width_px=width_px,
        )
        save_tile(tile, tiles_dir / f"{incident.incident_id}.svg")
        rendered.append(tile)
        if index % 10 == 0:
            logger.info("Rendered %d incident tiles", index)
    return rendered


def save_tile(tile: RenderedTile, output_path: str | Path) -> str:
    """Write a rendered SVG tile and return its path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tile.svg_content, encoding="utf-8")
    return str(path)


def render_annotated_tile(
    base_tile: RenderedTile,
    vision_result: "VisionTileResult | None" = None,
    severity: str | None = None,
    action_owner: str | None = None,
) -> RenderedTile:
    """Add review annotations over an existing SVG tile."""
    annotations = _render_annotation_overlay(base_tile, vision_result, severity, action_owner)
    if "</svg>" in base_tile.svg_content:
        svg_content = base_tile.svg_content.replace("</svg>", f"{annotations}\n</svg>", 1)
    else:
        svg_content = base_tile.svg_content + annotations
    return RenderedTile(
        tile_id=base_tile.tile_id,
        svg_content=svg_content,
        bbox_cad_mm=base_tile.bbox_cad_mm,
        width_px=base_tile.width_px,
        height_px=base_tile.height_px,
        scale_mm_per_px=base_tile.scale_mm_per_px,
        elements_in_tile=list(base_tile.elements_in_tile),
        texts_in_tile=list(base_tile.texts_in_tile),
        incident_id=base_tile.incident_id,
    )


def render_all_annotated_tiles(
    base_tiles: list[RenderedTile],
    vision_overrides: dict[str, Any],
    incident_severities: dict[str, Any],
    output_dir: str | Path,
) -> list[RenderedTile]:
    """Render and write annotated SVG tiles beside their base files."""
    tiles_dir = Path(output_dir) / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    annotated_tiles: list[RenderedTile] = []
    for base_tile in base_tiles:
        incident_id = base_tile.incident_id or base_tile.tile_id
        severity_payload = incident_severities.get(incident_id) or {}
        if isinstance(severity_payload, str):
            severity = severity_payload
            action_owner = None
        else:
            severity = severity_payload.get("severity")
            action_owner = severity_payload.get("action_owner")
        annotated = render_annotated_tile(
            base_tile,
            vision_result=vision_overrides.get(incident_id),
            severity=severity,
            action_owner=action_owner,
        )
        save_tile(annotated, tiles_dir / f"{incident_id}_annotated.svg")
        annotated_tiles.append(annotated)
    return annotated_tiles


def _render_annotation_overlay(
    base_tile: RenderedTile,
    vision_result: Any,
    severity: str | None,
    action_owner: str | None,
) -> str:
    severity_key = str(severity or "noise").lower()
    severity_color = SEVERITY_COLORS.get(severity_key, SEVERITY_COLORS["noise"])
    border_width = 3 if severity_key in {"critical", "major"} else 2 if severity_key == "minor" else 1
    border_color = "#DC2626" if severity_key in {"critical", "major"} else "#D97706" if severity_key == "minor" else "#6B7280"
    lines = [
        '<g class="dupla-annotations" font-family="Segoe UI,Arial,sans-serif">',
        f'<rect x="1.5" y="1.5" width="{max(base_tile.width_px - 3, 1)}" height="{max(base_tile.height_px - 3, 1)}" '
        f'fill="none" stroke="{border_color}" stroke-width="{border_width}"/>',
    ]

    badge_text = _escape_svg(severity_key.upper())
    badge_width = max(72, len(badge_text) * 8 + 18)
    badge_x = max(8, base_tile.width_px - badge_width - 12)
    lines.append(
        f'<rect x="{badge_x}" y="12" rx="5" ry="5" width="{badge_width}" height="24" fill="{severity_color}"/>'
    )
    lines.append(
        f'<text x="{badge_x + badge_width / 2:.2f}" y="28" text-anchor="middle" font-size="11" '
        f'font-weight="700" fill="#FFFFFF">{badge_text}</text>'
    )

    if vision_result is not None and getattr(vision_result, "clash_assessment", None) is not None:
        assessment = vision_result.clash_assessment
        appears_real = bool(getattr(assessment, "appears_real", False))
        label = "✓ CLASH REAL" if appears_real else "× RUIDO PROBABLE"
        color = "#16A34A" if appears_real else "#6B7280"
        assessment_width = 124 if appears_real else 142
        assessment_x = max(8, base_tile.width_px - assessment_width - 12)
        lines.append(
            f'<rect x="{assessment_x}" y="42" rx="5" ry="5" width="{assessment_width}" height="24" fill="{color}"/>'
        )
        lines.append(
            f'<text x="{assessment_x + assessment_width / 2:.2f}" y="58" text-anchor="middle" font-size="11" '
            f'font-weight="700" fill="#FFFFFF">{_escape_svg(label)}</text>'
        )

    semantic_labels = _semantic_label_rows(base_tile, vision_result)
    if semantic_labels:
        panel_width = min(300, max(180, max(len(row) for row in semantic_labels) * 7 + 22))
        panel_height = 18 + len(semantic_labels) * 20
        panel_x = 12
        panel_y = 12
        lines.append(
            f'<rect x="{panel_x}" y="{panel_y}" rx="5" ry="5" width="{panel_width}" height="{panel_height}" '
            'fill="#FFFFFF" fill-opacity="0.9" stroke="#D1D5DB"/>'
        )
        lines.append(
            f'<text x="{panel_x + 8}" y="{panel_y + 15}" font-size="11" font-weight="700" fill="#111827">Vision</text>'
        )
        cursor_y = panel_y + 34
        for row in semantic_labels:
            color = CONFIDENCE_COLORS.get(row["confidence"], CONFIDENCE_COLORS["low"])
            lines.append(f'<rect x="{panel_x + 8}" y="{cursor_y - 10}" width="8" height="8" fill="{color}"/>')
            lines.append(
                f'<text x="{panel_x + 22}" y="{cursor_y}" font-size="11" fill="#111827">'
                f'{_escape_svg(row["label"])}</text>'
            )
            cursor_y += 20

    if action_owner:
        owner_text = f"→ {action_owner}"
        owner_width = min(300, max(90, len(owner_text) * 7 + 18))
        owner_x = max(8, base_tile.width_px - owner_width - 12)
        owner_y = max(12, base_tile.height_px - 38)
        lines.append(
            f'<rect x="{owner_x}" y="{owner_y}" rx="5" ry="5" width="{owner_width}" height="26" '
            'fill="#111827" fill-opacity="0.82"/>'
        )
        lines.append(
            f'<text x="{owner_x + owner_width - 8}" y="{owner_y + 17}" text-anchor="end" '
            f'font-size="12" fill="#FFFFFF">{_escape_svg(owner_text)}</text>'
        )

    lines.append("</g>")
    return "\n".join(lines)


def _semantic_label_rows(base_tile: RenderedTile, vision_result: Any) -> list[dict[str, str]]:
    if vision_result is None:
        return []
    tile_ids = set(base_tile.elements_in_tile)
    rows: list[dict[str, str]] = []
    for item in getattr(vision_result, "elements_identified", []) or []:
        confidence = str(getattr(item, "confidence", "low") or "low").lower()
        if confidence not in {"high", "medium"}:
            continue
        element_id = str(getattr(item, "element_id", "") or "")
        if element_id and element_id not in tile_ids:
            continue
        semantic_type = str(getattr(item, "semantic_type", "otro") or "otro")
        name = getattr(item, "name", None)
        label = f"{semantic_type}: {name}" if name else semantic_type
        if element_id:
            label = f"{element_id} · {label}"
        rows.append({"label": label, "confidence": confidence})
    return rows


def _element_matches_level(element: Element25D, level_id: str) -> bool:
    metadata = element.metadata or {}
    return (
        metadata.get("level_id") == level_id
        or metadata.get("file_level_id") == level_id
        or level_id in str(metadata.get("file_level_id") or "")
        or element.z_data.level_id == level_id
    )


def _element_polygon(element: Element25D) -> Polygon | None:
    coords = list(element.footprint_coords_mm or [])
    if len(coords) < 3:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    polygon = Polygon(coords)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty or not polygon.is_valid:
        return None
    return polygon


def _discipline_color(element: Element25D) -> str:
    return DISCIPLINE_COLORS.get(str(element.discipline.value), DEFAULT_COLOR)


def _clash_element_ids(conflicts: list[ClashConflict]) -> set[str]:
    ids: set[str] = set()
    for conflict in conflicts:
        ids.add(conflict.element_id_a)
        ids.add(conflict.element_id_b)
    return ids


def _normalize_texts(texts: list[Any], elements: list[Element25D]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for text in texts:
        row = _text_to_dict(text)
        if row:
            normalized.append(row)
    if normalized:
        return normalized
    seen: set[tuple[str, tuple[float, float]]] = set()
    for element in elements:
        for item in element.metadata.get("nearby_texts") or []:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            centroid = row.get("centroid_mm")
            if not _valid_centroid(centroid):
                centroid = _element_centroid(element)
                row["centroid_mm"] = centroid
            key = (str(row.get("content") or ""), (float(centroid[0]), float(centroid[1])))
            if key not in seen:
                seen.add(key)
                normalized.append(row)
    return normalized


def _text_to_dict(text: Any) -> dict[str, Any] | None:
    if isinstance(text, dict):
        row = dict(text)
    else:
        row = {
            "content": getattr(text, "content", None),
            "centroid_mm": getattr(text, "centroid_mm", None),
            "layer": getattr(text, "layer", ""),
            "handle": getattr(text, "handle", ""),
            "entity_type": getattr(text, "entity_type", ""),
        }
    if not row.get("content") or not _valid_centroid(row.get("centroid_mm")):
        return None
    return row


def _texts_in_bbox(texts: list[Any], bbox_mm: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    min_x, min_y, max_x, max_y = bbox_mm
    found: list[dict[str, Any]] = []
    for text in texts:
        row = _text_to_dict(text)
        if not row:
            continue
        centroid = row["centroid_mm"]
        x = float(centroid[0])
        y = float(centroid[1])
        if min_x <= x <= max_x and min_y <= y <= max_y:
            found.append(row)
    return found


def _valid_centroid(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) >= 2


def _element_centroid(element: Element25D) -> tuple[float, float]:
    polygon = _element_polygon(element)
    if polygon is None:
        return (0.0, 0.0)
    centroid = polygon.centroid
    return (float(centroid.x), float(centroid.y))


def _render_grid(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    scale: float,
    width_px: int,
    height_px: int,
) -> list[str]:
    interval = _nice_grid_interval((max_x - min_x) / max(width_px, 1))
    lines = [f'<g class="grid" stroke="{GRID_COLOR}" stroke-width="0.6" font-size="9" fill="{GRID_COLOR}">']
    start_x = math.floor(min_x / interval) * interval
    x = start_x
    while x <= max_x:
        sx, _ = _cad_to_svg(x, min_y, min_x, max_y, scale)
        lines.append(f'<line x1="{sx:.2f}" y1="0" x2="{sx:.2f}" y2="{height_px}"/>')
        lines.append(f'<text x="{sx + 2:.2f}" y="11">{int(round(x))}</text>')
        x += interval
    start_y = math.floor(min_y / interval) * interval
    y = start_y
    while y <= max_y:
        _, sy = _cad_to_svg(min_x, y, min_x, max_y, scale)
        lines.append(f'<line x1="0" y1="{sy:.2f}" x2="{width_px}" y2="{sy:.2f}"/>')
        lines.append(f'<text x="2" y="{sy - 2:.2f}">{int(round(y))}</text>')
        y += interval
    lines.append("</g>")
    return lines


def _nice_grid_interval(mm_per_px: float) -> float:
    target = mm_per_px * 120.0
    for interval in (1000.0, 2000.0, 5000.0, 10000.0, 20000.0):
        if interval >= target:
            return interval
    return 50000.0


def _render_clash_zones(
    conflicts: list[ClashConflict],
    elements: list[Element25D],
    min_x: float,
    max_y: float,
    scale: float,
) -> list[str]:
    element_polygons = {element.id: _element_polygon(element) for element in elements}
    lines: list[str] = []
    for conflict in conflicts:
        left = element_polygons.get(conflict.element_id_a)
        right = element_polygons.get(conflict.element_id_b)
        if left is None or right is None:
            min_bx, min_by, max_bx, max_by = conflict.plan_intersection_bounds_mm
            geometry = box(min_bx, min_by, max_bx, max_by)
        else:
            geometry = left.intersection(right)
        for polygon in _iter_polygons(geometry):
            points = _polygon_to_svg_points(list(polygon.exterior.coords), min_x, max_y, scale)
            lines.append(
                f'<polygon points="{points}" fill="{CLASH_ZONE_FILL}" fill-opacity="{CLASH_ZONE_OPACITY}" '
                f'stroke="{CLASH_ZONE_FILL}" stroke-width="1.5" stroke-dasharray="6 4" vector-effect="non-scaling-stroke"/>'
            )
    return lines


def _iter_polygons(geometry: Any) -> list[Polygon]:
    if geometry is None or geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    return [geom for geom in getattr(geometry, "geoms", []) if isinstance(geom, Polygon)]


def _render_text_labels(texts: list[dict[str, Any]], min_x: float, max_y: float, scale: float) -> list[str]:
    lines = [f'<g class="cad-text" fill="{TEXT_LABEL_COLOR}" font-family="Segoe UI,Arial,sans-serif">']
    for item in texts:
        centroid = item.get("centroid_mm")
        if not _valid_centroid(centroid):
            continue
        label = _escape_svg(str(item.get("content") or ""))
        if not label:
            continue
        x, y = _cad_to_svg(float(centroid[0]), float(centroid[1]), min_x, max_y, scale)
        font_size = 10
        rect_width = max(24, len(label) * 6 + 6)
        lines.append(
            f'<rect x="{x - 3:.2f}" y="{y - font_size:.2f}" width="{rect_width}" height="14" '
            'fill="#FFFFFF" fill-opacity="0.78" stroke="#D1D5DB" stroke-width="0.4"/>'
        )
        lines.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{font_size}">{label}</text>')
    lines.append("</g>")
    return lines


def _render_legend(
    tile_spec: TileSpec,
    elements: list[Element25D],
    width_px: int,
    height_px: int,
    scale: float,
) -> list[str]:
    disciplines = sorted({str(element.discipline.value) for element in elements})
    legend_height = 58 + len(disciplines) * 16
    x = 12
    y = max(12, height_px - legend_height - 12)
    lines = [
        f'<g class="legend" font-family="Segoe UI,Arial,sans-serif" font-size="11" fill="#111827">',
        f'<rect x="{x}" y="{y}" width="245" height="{legend_height}" fill="#FFFFFF" fill-opacity="0.9" stroke="#D1D5DB"/>',
        f'<text x="{x + 8}" y="{y + 17}" font-weight="600">{_escape_svg(tile_spec.tile_id)}</text>',
        f'<text x="{x + 8}" y="{y + 34}">Nivel: {_escape_svg(tile_spec.level_id)}</text>',
        f'<text x="{x + 8}" y="{y + 51}">1mm = {scale:.4f}px</text>',
    ]
    cursor_y = y + 68
    for discipline in disciplines:
        color = DISCIPLINE_COLORS.get(discipline, DEFAULT_COLOR)
        lines.append(f'<rect x="{x + 8}" y="{cursor_y - 9}" width="10" height="10" fill="{color}"/>')
        lines.append(f'<text x="{x + 24}" y="{cursor_y}">{_escape_svg(discipline)}</text>')
        cursor_y += 16
    lines.append("</g>")
    return lines


def _render_scale_bar(min_x: float, min_y: float, max_y: float, scale: float, height_px: int) -> list[str]:
    bar_mm = 1000.0 if scale * 1000.0 >= 60.0 else 2000.0
    x0, _ = _cad_to_svg(min_x + 120.0, min_y + 120.0, min_x, max_y, scale)
    y = max(24.0, height_px - 24.0)
    length = bar_mm * scale
    label = "1m" if bar_mm == 1000.0 else "2m"
    return [
        '<g class="scale-bar" stroke="#111827" fill="#111827" font-family="Segoe UI,Arial,sans-serif" font-size="10">',
        f'<line x1="{x0:.2f}" y1="{y:.2f}" x2="{x0 + length:.2f}" y2="{y:.2f}" stroke-width="2"/>',
        f'<line x1="{x0:.2f}" y1="{y - 5:.2f}" x2="{x0:.2f}" y2="{y + 5:.2f}" stroke-width="1"/>',
        f'<line x1="{x0 + length:.2f}" y1="{y - 5:.2f}" x2="{x0 + length:.2f}" y2="{y + 5:.2f}" stroke-width="1"/>',
        f'<text x="{x0 - 2:.2f}" y="{y - 8:.2f}">0</text>',
        f'<text x="{x0 + length - 10:.2f}" y="{y - 8:.2f}">{label}</text>',
        "</g>",
    ]


def _incident_conflicts(incident: ClashIncident) -> list[ClashConflict]:
    conflicts = getattr(incident, "conflicts", None)
    if isinstance(conflicts, list):
        return [item for item in conflicts if isinstance(item, ClashConflict)]
    return [incident.representative_conflict]
