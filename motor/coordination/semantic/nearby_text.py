"""Spatial index for CAD text used to enrich 2.5D coordination elements."""

from __future__ import annotations

import logging
import math
from numbers import Integral
from dataclasses import dataclass
from typing import Any

from shapely.geometry import Point, box
from shapely.strtree import STRtree

logger = logging.getLogger(__name__)

TEXT_ENTITY_TYPES = {"DBTEXT", "MTEXT", "MText", "DBText"}
TEXT_CONTENT_FIELDS = ("TextString", "Content", "Contents", "Text", "Value", "text")


@dataclass(frozen=True)
class CadText:
    content: str
    centroid_mm: tuple[float, float]
    bbox_mm: tuple[float, float, float, float]
    layer: str
    handle: str
    entity_type: str
    source_file: str


def extract_texts_from_accore_payload(
    payload: dict[str, Any],
    units_to_mm: float | None = None,
    source_file: str = "",
    translation_mm: tuple[float, float] = (0.0, 0.0),
) -> list[CadText]:
    """Extract DBText/MText entities from an Accore payload."""
    factor_mm = float(units_to_mm if units_to_mm is not None else payload.get("UnitsToMmFactor") or 1.0)
    texts: list[CadText] = []
    text_entity_count = 0
    content_fields_used: set[str] = set()
    missing_content_count = 0

    for entity in payload.get("Entities") or []:
        if not isinstance(entity, dict):
            continue
        entity_type = str(entity.get("Type") or "")
        if entity_type not in TEXT_ENTITY_TYPES:
            continue
        text_entity_count += 1
        content, field_used = _extract_text_content(entity)
        if not content:
            missing_content_count += 1
            logger.warning("Skipping CAD text entity without readable content in %s: %s", source_file, entity)
            continue
        if field_used:
            content_fields_used.add(field_used)
        bbox_mm = _bbox_from_entity(entity, factor_mm=factor_mm)
        if bbox_mm is None:
            logger.warning("Skipping CAD text entity without usable bounds/point in %s: %s", source_file, entity)
            continue
        dx, dy = translation_mm
        bbox_mm = (bbox_mm[0] + dx, bbox_mm[1] + dy, bbox_mm[2] + dx, bbox_mm[3] + dy)
        centroid = ((bbox_mm[0] + bbox_mm[2]) / 2.0, (bbox_mm[1] + bbox_mm[3]) / 2.0)
        texts.append(
            CadText(
                content=content,
                centroid_mm=centroid,
                bbox_mm=bbox_mm,
                layer=str(entity.get("Layer") or "0"),
                handle=str(entity.get("Handle") or ""),
                entity_type=entity_type,
                source_file=source_file,
            )
        )

    if text_entity_count and missing_content_count == text_entity_count:
        logger.warning(
            "No text content field found in Accore payload for %s. "
            "Text entities have bounds but no TextString/Content/Text field. "
            "The DuplaExtractor DLL may need to be updated to serialize text content. "
            "nearby_text enrichment will be skipped for this file.",
            source_file,
        )
    logger.info(
        "nearby_text extracted %d/%d text entities for %s; content fields: %s",
        len(texts),
        text_entity_count,
        source_file,
        ", ".join(sorted(content_fields_used)) or "none",
    )
    return texts


def build_text_index(texts: list[CadText]) -> STRtree:
    """Build an STRtree over text bounding boxes."""
    return STRtree([box(*text.bbox_mm) for text in texts])


def find_nearby_texts(
    element_centroid_mm: tuple[float, float],
    text_index: STRtree,
    texts: list[CadText],
    radius_mm: float = 1500.0,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Return nearest CAD texts around an element centroid."""
    if not texts:
        return []
    cx, cy = element_centroid_mm
    query_geom = Point(cx, cy).buffer(radius_mm)
    try:
        raw_candidates = list(text_index.query(query_geom))
    except Exception:
        raw_candidates = list(range(len(texts)))

    candidate_indices: list[int] = []
    for candidate in raw_candidates:
        if isinstance(candidate, Integral):
            candidate_indices.append(int(candidate))
            continue
        index_attr = getattr(candidate, "item", None)
        if callable(index_attr):
            try:
                candidate_indices.append(int(candidate.item()))
                continue
            except Exception:
                pass
        # Shapely 1.x returns geometries, not indices. Fall back to a bounded
        # brute-force pass; text lists are small enough for this diagnostic layer.
        candidate_indices = list(range(len(texts)))
        break

    seen: set[int] = set()
    ranked: list[tuple[float, CadText]] = []
    for index in candidate_indices:
        if index in seen or index < 0 or index >= len(texts):
            continue
        seen.add(index)
        text = texts[index]
        distance = math.dist((cx, cy), text.centroid_mm)
        if distance <= radius_mm:
            ranked.append((distance, text))
    ranked.sort(key=lambda item: item[0])
    return [
        {
            "content": text.content,
            "distance_mm": round(distance, 3),
            "layer": text.layer,
            "handle": text.handle,
            "entity_type": text.entity_type,
            "centroid_mm": text.centroid_mm,
        }
        for distance, text in ranked[:max_results]
    ]


def enrich_elements_with_nearby_text(
    elements: list[Any],
    texts: list[CadText],
    radius_mm: float = 1500.0,
    max_results: int = 5,
) -> None:
    """Attach nearest CAD texts to each element's metadata in place."""
    if not elements:
        return
    if not texts:
        for element in elements:
            element.metadata["nearby_texts"] = []
        return
    text_index = build_text_index(texts)
    for element in elements:
        centroid = _element_centroid_mm(element)
        element.metadata["nearby_texts"] = (
            find_nearby_texts(
                centroid,
                text_index,
                texts,
                radius_mm=radius_mm,
                max_results=max_results,
            )
            if centroid is not None
            else []
        )


def _extract_text_content(entity: dict[str, Any]) -> tuple[str, str | None]:
    for field in TEXT_CONTENT_FIELDS:
        value = entity.get(field)
        if value is not None and str(value).strip():
            return str(value).strip(), field
    return ("", None)


def _bbox_from_entity(entity: dict[str, Any], *, factor_mm: float) -> tuple[float, float, float, float] | None:
    bounds = entity.get("Bounds")
    if isinstance(bounds, dict):
        min_pt = bounds.get("Min") or {}
        max_pt = bounds.get("Max") or {}
        try:
            x0 = float(min_pt.get("X") or 0.0) * factor_mm
            y0 = float(min_pt.get("Y") or 0.0) * factor_mm
            x1 = float(max_pt.get("X") or 0.0) * factor_mm
            y1 = float(max_pt.get("Y") or 0.0) * factor_mm
        except Exception:
            return None
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        return (x0, y0, x1, y1)

    for key in ("Center", "Position", "InsertionPoint"):
        point = entity.get(key)
        if not isinstance(point, dict):
            continue
        try:
            x = float(point.get("X") or 0.0) * factor_mm
            y = float(point.get("Y") or 0.0) * factor_mm
        except Exception:
            continue
        return (x, y, x, y)
    return None


def _element_centroid_mm(element: Any) -> tuple[float, float] | None:
    metadata_centroid = getattr(element, "metadata", {}).get("centroid_mm")
    if isinstance(metadata_centroid, (list, tuple)) and len(metadata_centroid) >= 2:
        return (float(metadata_centroid[0]), float(metadata_centroid[1]))
    coords = list(getattr(element, "footprint_coords_mm", []) or [])
    if not coords:
        return None
    return (
        sum(float(point[0]) for point in coords) / len(coords),
        sum(float(point[1]) for point in coords) / len(coords),
    )
