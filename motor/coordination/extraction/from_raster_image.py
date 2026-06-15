"""Raster extraction as low-confidence candidate regions instead of full image bounds."""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path

import fitz

from coordination.selection.level_inference import extract_sheet_name, infer_level_from_text
from coordination.core.models_25d import Discipline, Element25D, ZInterval
from coordination.core.nasas_paths import translate_footprint
from coordination.core.registry import ProjectLevelRegistryDocument

logger = logging.getLogger("dupla.coordination.image")

PT_TO_MM = 25.4 / 72.0


def extract_elements_from_image(
    path: Path,
    discipline: Discipline,
    *,
    level_id: str,
    translation_mm: tuple[float, float] = (0.0, 0.0),
    z_ref_mm: float = 0.0,
    z_thickness_mm: float = 50.0,
    level_doc: ProjectLevelRegistryDocument | None = None,
    max_components: int = 16,
) -> list[Element25D]:
    try:
        doc = fitz.open(path)
        page = doc[0]
        page_rect = page.rect
        scale = min(1.0, 768.0 / max(page_rect.width, page_rect.height, 1.0))
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        doc.close()
    except Exception as exc:
        logger.warning("Imagen %s: %s", path, exc)
        return []

    resolution = infer_level_from_text(
        path.name,
        doc=level_doc,
        default_level_id=level_id,
        fallback_source="default_level",
    )
    sheet_name = extract_sheet_name(path.stem, fallback=path.stem)
    boxes = _detect_candidate_boxes(
        pix.width,
        pix.height,
        pix.n,
        pix.samples,
        max_boxes=max_components,
    )
    elements: list[Element25D] = []
    for idx, (x0, y0, x1, y1) in enumerate(boxes):
        coords = [
            (page_rect.width * PT_TO_MM * x0 / pix.width, page_rect.height * PT_TO_MM * y0 / pix.height),
            (page_rect.width * PT_TO_MM * x1 / pix.width, page_rect.height * PT_TO_MM * y0 / pix.height),
            (page_rect.width * PT_TO_MM * x1 / pix.width, page_rect.height * PT_TO_MM * y1 / pix.height),
            (page_rect.width * PT_TO_MM * x0 / pix.width, page_rect.height * PT_TO_MM * y1 / pix.height),
        ]
        coords = translate_footprint(coords, translation_mm[0], translation_mm[1])
        elements.append(
            Element25D(
                id=f"img_{path.stem}_{idx}",
                source_ref=path.as_posix(),
                discipline=discipline,
                category="raster_component",
                footprint_coords_mm=coords,
                z_data=ZInterval(
                    level_id=resolution.level_id,
                    z_ref_raw_mm=z_ref_mm,
                    thickness_mm=z_thickness_mm,
                    reference_point="bottom",
                ),
                metadata={
                    "file": path.name,
                    "source": "raster_components",
                    "geometry_source": "raster_components",
                    "geometry_quality": "low",
                    "level_assignment_source": resolution.source,
                    "sheet_or_view_name": sheet_name,
                    "component_index": idx,
                },
            )
        )
    return elements


def _detect_candidate_boxes(
    width: int,
    height: int,
    channels: int,
    samples: bytes,
    *,
    max_boxes: int,
) -> list[tuple[int, int, int, int]]:
    if width <= 0 or height <= 0 or channels <= 0:
        return []

    block = max(4, min(10, max(width, height) // 120 or 4))
    grid_w = max(1, width // block)
    grid_h = max(1, height // block)
    occupied = [[False for _ in range(grid_w)] for _ in range(grid_h)]

    for gy in range(grid_h):
        for gx in range(grid_w):
            dark = 0
            total = 0
            x_start = gx * block
            y_start = gy * block
            for py in range(y_start, min(y_start + block, height)):
                row_offset = py * width * channels
                for px in range(x_start, min(x_start + block, width)):
                    offset = row_offset + px * channels
                    gray = _gray(samples, offset, channels)
                    total += 1
                    if gray < 210:
                        dark += 1
            occupied[gy][gx] = total > 0 and (dark >= 4 and dark / total >= 0.05)

    components: list[tuple[int, int, int, int, int]] = []
    visited = [[False for _ in range(grid_w)] for _ in range(grid_h)]
    for gy in range(grid_h):
        for gx in range(grid_w):
            if visited[gy][gx] or not occupied[gy][gx]:
                continue
            queue: deque[tuple[int, int]] = deque([(gx, gy)])
            visited[gy][gx] = True
            min_x = max_x = gx
            min_y = max_y = gy
            size = 0
            while queue:
                cx, cy = queue.popleft()
                size += 1
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)
                for nx in range(max(0, cx - 1), min(grid_w, cx + 2)):
                    for ny in range(max(0, cy - 1), min(grid_h, cy + 2)):
                        if visited[ny][nx] or not occupied[ny][nx]:
                            continue
                        visited[ny][nx] = True
                        queue.append((nx, ny))
            components.append((size, min_x, min_y, max_x + 1, max_y + 1))

    components.sort(reverse=True)
    boxes: list[tuple[int, int, int, int]] = []
    page_area = max(width * height, 1)
    for size, min_x, min_y, max_x, max_y in components:
        x0 = min_x * block
        y0 = min_y * block
        x1 = min(max_x * block, width)
        y1 = min(max_y * block, height)
        area = max((x1 - x0) * (y1 - y0), 1)
        area_ratio = area / page_area
        if size < 3 or area_ratio < 0.003 or area_ratio > 0.85:
            continue
        boxes.append((x0, y0, x1, y1))
        if len(boxes) >= max_boxes:
            break
    return _merge_nearby_boxes(boxes, gap=block * 2)


def _gray(samples: bytes, offset: int, channels: int) -> int:
    if channels == 1:
        return samples[offset]
    r = samples[offset]
    g = samples[offset + 1]
    b = samples[offset + 2]
    return (30 * r + 59 * g + 11 * b) // 100


def _merge_nearby_boxes(
    boxes: list[tuple[int, int, int, int]],
    *,
    gap: int,
) -> list[tuple[int, int, int, int]]:
    merged = list(boxes)
    changed = True
    while changed:
        changed = False
        out: list[tuple[int, int, int, int]] = []
        while merged:
            current = merged.pop()
            x0, y0, x1, y1 = current
            idx = 0
            while idx < len(merged):
                ox0, oy0, ox1, oy1 = merged[idx]
                if ox0 <= x1 + gap and ox1 >= x0 - gap and oy0 <= y1 + gap and oy1 >= y0 - gap:
                    x0 = min(x0, ox0)
                    y0 = min(y0, oy0)
                    x1 = max(x1, ox1)
                    y1 = max(y1, oy1)
                    merged.pop(idx)
                    changed = True
                    idx = 0
                    continue
                idx += 1
            out.append((x0, y0, x1, y1))
        merged = out
    merged.sort(key=lambda box: (box[2] - box[0]) * (box[3] - box[1]), reverse=True)
    return merged
