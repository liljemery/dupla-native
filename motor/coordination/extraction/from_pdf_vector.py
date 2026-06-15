"""Vector PDF extraction using path-level clusters instead of page-size bounds."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from coordination.selection.level_inference import (
    extract_sheet_name,
    infer_level_from_pdf_page,
)
from coordination.core.models_25d import Discipline, Element25D, ZInterval
from coordination.core.nasas_paths import translate_footprint
from coordination.core.registry import ProjectLevelRegistryDocument

logger = logging.getLogger("dupla.coordination.pdf")

PT_TO_MM = 25.4 / 72.0


def extract_elements_from_pdf(
    path: Path,
    discipline: Discipline,
    *,
    level_id: str,
    translation_mm: tuple[float, float] = (0.0, 0.0),
    page_z_step_mm: float = 0.0,
    max_pages: int = 500,
    z_thickness_mm: float = 200.0,
    level_doc: ProjectLevelRegistryDocument | None = None,
    allow_page_fallback: bool = False,
    max_clusters_per_page: int = 24,
) -> list[Element25D]:
    elements: list[Element25D] = []
    try:
        doc = fitz.open(path)
    except Exception as exc:
        logger.warning("PDF %s: %s", path, exc)
        return []

    for page_index in range(min(len(doc), max_pages)):
        page = doc[page_index]
        page_text = page.get_text("text") or ""
        page_label = ""
        try:
            page_label = page.get_label() or ""
        except Exception:
            page_label = ""
        level_resolution, z_base = infer_level_from_pdf_page(
            page_text=page_text,
            page_label=page_label,
            file_name=path.name,
            doc=level_doc,
            default_level_id=level_id,
            page_index=page_index,
            page_z_step_mm=page_z_step_mm,
        )
        sheet_name = extract_sheet_name(page_text, fallback=f"{path.stem} page {page_index + 1}")

        try:
            drawings = page.get_drawings()
        except Exception as exc:
            logger.warning("PDF %s page %d: get_drawings failed: %s", path.name, page_index + 1, exc)
            drawings = []

        valid_clusters = _valid_clusters(page, drawings)
        for cluster_index, cluster in enumerate(valid_clusters[:max_clusters_per_page]):
            coords = [
                (cluster.x0 * PT_TO_MM, cluster.y0 * PT_TO_MM),
                (cluster.x1 * PT_TO_MM, cluster.y0 * PT_TO_MM),
                (cluster.x1 * PT_TO_MM, cluster.y1 * PT_TO_MM),
                (cluster.x0 * PT_TO_MM, cluster.y1 * PT_TO_MM),
            ]
            coords = translate_footprint(coords, translation_mm[0], translation_mm[1])
            elements.append(
                Element25D(
                    id=f"pdf_{path.stem}_p{page_index}_c{cluster_index}",
                    source_ref=f"{path.as_posix()}#page={page_index + 1}",
                    discipline=discipline,
                    category="pdf_vector_cluster",
                    footprint_coords_mm=coords,
                    z_data=ZInterval(
                        level_id=level_resolution.level_id,
                        z_ref_raw_mm=z_base,
                        thickness_mm=z_thickness_mm,
                        reference_point="bottom",
                    ),
                    metadata={
                        "file": path.name,
                        "page": page_index + 1,
                        "source": "pdf_vector",
                        "geometry_source": "pdf_vector_cluster",
                        "geometry_quality": "medium",
                        "level_assignment_source": level_resolution.source,
                        "sheet_or_view_name": sheet_name,
                        "cluster_index": cluster_index,
                    },
                )
            )

        if not valid_clusters and allow_page_fallback:
            pr = page.rect
            coords = [
                (0.0, 0.0),
                (pr.width * PT_TO_MM, 0.0),
                (pr.width * PT_TO_MM, pr.height * PT_TO_MM),
                (0.0, pr.height * PT_TO_MM),
            ]
            coords = translate_footprint(coords, translation_mm[0], translation_mm[1])
            elements.append(
                Element25D(
                    id=f"pdf_{path.stem}_p{page_index}_fallback",
                    source_ref=f"{path.as_posix()}#page={page_index + 1}",
                    discipline=discipline,
                    category="pdf_page_fallback",
                    footprint_coords_mm=coords,
                    z_data=ZInterval(
                        level_id=level_resolution.level_id,
                        z_ref_raw_mm=z_base,
                        thickness_mm=z_thickness_mm,
                        reference_point="bottom",
                    ),
                    metadata={
                        "file": path.name,
                        "page": page_index + 1,
                        "source": "pdf_vector",
                        "geometry_source": "pdf_page_fallback",
                        "geometry_quality": "proxy",
                        "level_assignment_source": level_resolution.source,
                        "sheet_or_view_name": sheet_name,
                    },
                )
            )
    doc.close()
    return elements


def _valid_clusters(page: fitz.Page, drawings: list[dict[str, Any]]) -> list[fitz.Rect]:
    page_rect = page.rect
    page_area = max(page_rect.width * page_rect.height, 1.0)
    filtered_drawings = []
    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None:
            filtered_drawings.append(drawing)
            continue
        rect = fitz.Rect(rect)
        area_ratio = (rect.width * rect.height) / page_area
        if _looks_like_page_border(rect, page_rect, area_ratio):
            continue
        if _looks_like_title_block(rect, page_rect):
            continue
        if _looks_like_margin_stamp(rect, page_rect):
            continue
        filtered_drawings.append(drawing)
    clusters: list[fitz.Rect] = []
    try:
        raw_clusters = page.cluster_drawings(
            drawings=filtered_drawings,
            x_tolerance=6.0,
            y_tolerance=6.0,
            final_filter=True,
        )
    except Exception:
        raw_clusters = []

    for cluster in raw_clusters:
        if not isinstance(cluster, fitz.Rect):
            cluster = fitz.Rect(cluster)
        area_ratio = (cluster.width * cluster.height) / page_area
        if area_ratio < 0.003:
            continue
        if _looks_like_page_border(cluster, page_rect, area_ratio):
            continue
        if _looks_like_title_block(cluster, page_rect):
            continue
        if _looks_like_margin_stamp(cluster, page_rect):
            continue
        if not _cluster_has_path_content(cluster, filtered_drawings):
            continue
        clusters.append(cluster)
    clusters.sort(key=lambda rect: rect.width * rect.height, reverse=True)
    return clusters


def _cluster_has_path_content(cluster: fitz.Rect, drawings: list[dict[str, Any]]) -> bool:
    relevant = 0
    for drawing in drawings:
        rects = _drawing_item_rects(drawing)
        if any(rect.intersects(cluster) for rect in rects):
            relevant += 1
            if relevant >= 1:
                return True
    return False


def _drawing_item_rects(drawing: dict[str, Any]) -> list[fitz.Rect]:
    rects: list[fitz.Rect] = []
    for item in drawing.get("items") or []:
        kind = item[0]
        if kind == "l":
            p1, p2 = item[1], item[2]
            rects.append(fitz.Rect(min(p1.x, p2.x), min(p1.y, p2.y), max(p1.x, p2.x), max(p1.y, p2.y)))
        elif kind == "re":
            rects.append(fitz.Rect(item[1]))
        elif kind == "qu":
            quad = item[1]
            xs = [quad.ul.x, quad.ur.x, quad.lr.x, quad.ll.x]
            ys = [quad.ul.y, quad.ur.y, quad.lr.y, quad.ll.y]
            rects.append(fitz.Rect(min(xs), min(ys), max(xs), max(ys)))
        elif kind == "c":
            pts = item[1:]
            xs = [point.x for point in pts]
            ys = [point.y for point in pts]
            rects.append(fitz.Rect(min(xs), min(ys), max(xs), max(ys)))
    if not rects and drawing.get("rect") is not None:
        rects.append(fitz.Rect(drawing["rect"]))
    return rects


def _looks_like_page_border(cluster: fitz.Rect, page_rect: fitz.Rect, area_ratio: float) -> bool:
    margin = 12.0
    touches = 0
    if abs(cluster.x0 - page_rect.x0) <= margin:
        touches += 1
    if abs(cluster.y0 - page_rect.y0) <= margin:
        touches += 1
    if abs(cluster.x1 - page_rect.x1) <= margin:
        touches += 1
    if abs(cluster.y1 - page_rect.y1) <= margin:
        touches += 1
    return touches >= 3 and area_ratio >= 0.45


def _looks_like_title_block(cluster: fitz.Rect, page_rect: fitz.Rect) -> bool:
    width_ratio = cluster.width / max(page_rect.width, 1.0)
    height_ratio = cluster.height / max(page_rect.height, 1.0)
    touches_bottom = abs(cluster.y1 - page_rect.y1) <= 18.0
    touches_right = abs(cluster.x1 - page_rect.x1) <= 18.0
    return touches_bottom and touches_right and width_ratio >= 0.2 and height_ratio <= 0.22


def _looks_like_margin_stamp(cluster: fitz.Rect, page_rect: fitz.Rect) -> bool:
    width_ratio = cluster.width / max(page_rect.width, 1.0)
    height_ratio = cluster.height / max(page_rect.height, 1.0)
    touches_left = abs(cluster.x0 - page_rect.x0) <= 18.0
    touches_right = abs(cluster.x1 - page_rect.x1) <= 18.0
    touches_top = abs(cluster.y0 - page_rect.y0) <= 18.0
    touches_bottom = abs(cluster.y1 - page_rect.y1) <= 18.0
    return (touches_left or touches_right or touches_top or touches_bottom) and width_ratio <= 0.12 and height_ratio <= 0.12
