"""Unified FOSS CAD extraction: LibreDWG + ezdxf -> cad_facts / Element25D."""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from coordination.core.models_25d import Discipline, Element25D, ZInterval
from coordination.core.nasas_paths import translate_footprint
from coordination.core.units import insunits_to_mm_factor
from coordination.extraction.cad_cache import file_cache_key, load_cached_json, save_cached_json
from coordination.extraction.dxf_geometry import (
    DxfGeometryExtraction,
    DxfGeometryRecord,
    extract_dxf_geometry,
)
from coordination.extraction.companion_dxf import is_readable_dxf, resolve_companion_dxf
from coordination.extraction.libredwg_convert import (
    convert_dwg_to_dxf_resilient,
    display_name_from_storage,
    invalidate_cached_dxf,
    is_binary_dwg,
)

logger = logging.getLogger("dupla.coordination.local_cad")

LOCAL_EXTRACTOR = "local_ezdxf"
DEFAULT_Z_THICKNESS_MM = 250.0


def _conversion_work_dir(path: Path, work_dir: Path | None) -> Path | None:
    if work_dir is None:
        return None
    unique = Path(work_dir) / file_cache_key(path)
    unique.mkdir(parents=True, exist_ok=True)
    return unique


def normalize_to_dxf(
    path: Path,
    *,
    cache_root: Path | None = None,
    work_dir: Path | None = None,
    search_roots: list[Path] | None = None,
) -> tuple[Path, str]:
    """Return (dxf_path, geometry_source_tag)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".dxf":
        return path, "native_dxf"
    if suffix == ".dwg" and is_binary_dwg(path):
        companion = resolve_companion_dxf(path, search_roots=search_roots)
        if companion is not None and is_readable_dxf(companion):
            logger.info("Using companion DXF for %s -> %s", path.name, companion.name)
            return companion, "dxf_companion"
        out_dir = _conversion_work_dir(path, work_dir)
        dxf_path, geometry_source = convert_dwg_to_dxf_resilient(
            path,
            output_dir=out_dir,
            cache_root=cache_root,
        )
        return dxf_path, geometry_source
    if suffix == ".dwg":
        return path, "dwg_text_or_legacy"
    raise ValueError(f"Unsupported CAD extension: {path.suffix}")


def extract_dxf_records(
    path: Path,
    discipline: Discipline | str,
    *,
    cache_root: Path | None = None,
    work_dir: Path | None = None,
    search_roots: list[Path] | None = None,
) -> DxfGeometryExtraction:
    dxf_path, geometry_source = normalize_to_dxf(
        path,
        cache_root=cache_root,
        work_dir=work_dir,
        search_roots=search_roots,
    )
    converted_via_libredwg = geometry_source.startswith("libredwg_")
    try:
        extraction = extract_dxf_geometry(dxf_path, discipline)
    except Exception:
        if converted_via_libredwg and path.suffix.lower() == ".dwg":
            invalidate_cached_dxf(path, cache_root=cache_root, output_dir=dxf_path.parent)
        raise
    extraction.geometry_source = geometry_source
    if extraction.recovered_salvaged:
        extraction.geometry_source = f"{geometry_source}_salvaged"
    return extraction


def _bbox_dict(min_x: float, min_y: float, max_x: float, max_y: float) -> dict[str, dict[str, float]]:
    return {
        "min": {"x": min_x, "y": min_y, "z": 0.0},
        "max": {"x": max_x, "y": max_y, "z": 0.0},
    }


def _record_length_area(record: DxfGeometryRecord) -> tuple[float | None, float | None]:
    min_x, min_y, max_x, max_y = record.model_bounds
    width = abs(max_x - min_x)
    height = abs(max_y - min_y)
    dxftype = record.dxftype.upper()
    if dxftype in {"LINE", "XLINE", "RAY"}:
        return math.hypot(width, height) or None, None
    if dxftype in {"CIRCLE", "ARC"}:
        radius = max(width, height) / 2.0
        return 2.0 * math.pi * radius, math.pi * radius * radius
    area = width * height
    if area <= 0:
        return None, None
    if dxftype in {"LWPOLYLINE", "POLYLINE", "HATCH", "SOLID"}:
        return None, area
    return max(width, height), area


def _insunits_scale_to_meters(insunits: int | None, measurement: int = 1) -> float:
    mm_factor = insunits_to_mm_factor(int(insunits or 0), measurement=measurement)
    if mm_factor <= 0:
        return 1.0
    return mm_factor / 1000.0


def records_to_cad_facts(
    extraction: DxfGeometryExtraction,
    *,
    source_path: Path | str,
) -> dict[str, Any]:
    """Build processor-compatible normalized payload from DXF extraction."""
    source_path = Path(source_path)
    source_file = display_name_from_storage(source_path.name)
    layer_metrics: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "object_count": 0,
            "entity_types": Counter(),
            "sample_names": [],
            "handles": [],
        }
    )
    geometry_hints: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []

    unit_scale = _insunits_scale_to_meters(extraction.insunits)

    for record in extraction.records:
        if not record.is_physical:
            continue
        layer = record.layer or "UNKNOWN"
        metrics = layer_metrics[layer]
        metrics["object_count"] += 1
        metrics["entity_types"][record.dxftype] += 1
        if record.handle and len(metrics["handles"]) < 5:
            metrics["handles"].append(record.handle)

        min_x, min_y, max_x, max_y = record.model_bounds
        min_x *= unit_scale
        min_y *= unit_scale
        max_x *= unit_scale
        max_y *= unit_scale
        length, area = _record_length_area(record)
        if length is not None:
            length *= unit_scale
        if area is not None:
            area *= unit_scale * unit_scale

        hint: dict[str, Any] = {
            "layer": layer,
            "entity_type": record.dxftype,
            "name": record.block_name or record.dxftype,
            "handle": record.handle,
            "length": length,
            "area": area,
            "radius": None,
            "bbox": _bbox_dict(min_x, min_y, max_x, max_y),
            "geometry_source": getattr(extraction, "geometry_source", None) or LOCAL_EXTRACTOR,
            "geometry_quality": record.geometry_quality,
            "source_file": source_file,
        }
        if record.dxftype.upper() == "INSERT" and record.block_name:
            blocks.append(
                {
                    "layer": layer,
                    "entity_type": record.dxftype,
                    "handle": record.handle,
                    "block_name": record.block_name,
                    "bbox": hint["bbox"],
                    "source_file": source_file,
                }
            )
        if record.dxftype.upper() in {"TEXT", "MTEXT"}:
            texts.append(
                {
                    "layer": layer,
                    "entity_type": record.dxftype,
                    "handle": record.handle,
                    "content": "",
                    "bbox": hint["bbox"],
                    "source_file": source_file,
                }
            )
        geometry_hints.append(hint)

    layer_summary: dict[str, dict[str, Any]] = {}
    for layer, metrics in layer_metrics.items():
        entity_types = metrics["entity_types"]
        layer_summary[layer] = {
            "object_count": metrics["object_count"],
            "entity_types": dict(entity_types),
            "dominant_entity_type": entity_types.most_common(1)[0][0] if entity_types else "Entity",
            "sample_names": list(metrics["sample_names"]),
            "handles": list(metrics["handles"]),
        }

    block_frequency = Counter(item.get("block_name") for item in blocks if item.get("block_name"))

    return {
        "project": source_path.name,
        "source_file": source_file,
        "source_files": [source_file],
        "total_objects": len(extraction.records),
        "extractor": LOCAL_EXTRACTOR,
        "geometry_source": getattr(extraction, "geometry_source", None) or LOCAL_EXTRACTOR,
        "recovered_partial": bool(getattr(extraction, "recovered_partial", False)),
        "recovered_salvaged": bool(getattr(extraction, "recovered_salvaged", False)),
        "cad_facts": {
            "layers": layer_summary,
            "texts": texts,
            "dimensions": [],
            "hatches": [],
            "blocks": blocks,
            "geometry_hints": geometry_hints,
        },
        "inventory_hints": {
            "level_markers": [],
            "scale_dimensions": [],
            "block_frequency": [
                {"block_name": name, "count": count} for name, count in block_frequency.most_common(25)
            ],
            "layer_names": sorted(layer_summary.keys()),
        },
        "local_extraction": extraction.to_dict(),
    }


def _footprint_from_bounds(bounds: tuple[float, float, float, float], factor_mm: float) -> list[tuple[float, float]]:
    min_x, min_y, max_x, max_y = bounds
    coords = [
        (min_x * factor_mm, min_y * factor_mm),
        (max_x * factor_mm, min_y * factor_mm),
        (max_x * factor_mm, max_y * factor_mm),
        (min_x * factor_mm, max_y * factor_mm),
    ]
    return coords


def records_to_elements25d(
    extraction: DxfGeometryExtraction,
    discipline: Discipline,
    *,
    level_id: str,
    translation_mm: tuple[float, float],
    path_label: str,
    coordination_issue_key: str,
    max_entities: int = 400,
    min_area_mm2: float = 40_000.0,
    z_thickness_mm: float = DEFAULT_Z_THICKNESS_MM,
) -> list[Element25D]:
    mm_factor = insunits_to_mm_factor(int(extraction.insunits or 0))
    if mm_factor <= 0:
        mm_factor = 1000.0

    out: list[Element25D] = []
    for record in extraction.records:
        if not record.is_physical:
            continue
        min_x, min_y, max_x, max_y = record.model_bounds
        area_native = abs(max_x - min_x) * abs(max_y - min_y)
        area_mm2 = area_native * mm_factor * mm_factor
        if area_mm2 < min_area_mm2:
            continue
        footprint = translate_footprint(
            _footprint_from_bounds(record.model_bounds, mm_factor),
            translation_mm[0],
            translation_mm[1],
        )
        out.append(
            Element25D(
                id=f"local_{path_label}_{record.handle or len(out)}",
                source_ref=f"{path_label}|{LOCAL_EXTRACTOR}:{record.handle}",
                discipline=discipline,
                category=f"{LOCAL_EXTRACTOR}:{record.layer}:{record.dxftype}",
                footprint_coords_mm=footprint,
                z_data=ZInterval(
                    level_id=level_id,
                    z_ref_raw_mm=0.0,
                    thickness_mm=z_thickness_mm,
                    reference_point="bottom",
                ),
                metadata={
                    "coordination_issue_key": coordination_issue_key,
                    "geometry_source": LOCAL_EXTRACTOR,
                    "geometry_quality": record.geometry_quality,
                    "layer": record.layer,
                    "handle": record.handle,
                    "dxftype": record.dxftype,
                },
            )
        )
        if len(out) >= max_entities:
            break
    return out


def extract_cad_facts(
    path: Path | str,
    discipline: Discipline | str = Discipline.ARCH,
    *,
    cache_root: Path | None = None,
    work_dir: Path | None = None,
    search_roots: list[Path] | None = None,
) -> dict[str, Any]:
    path = Path(path)
    cache_key = file_cache_key(path)
    if cache_root is not None:
        cached = load_cached_json(cache_root, key=cache_key, suffix="cad_facts")
        if isinstance(cached, dict) and cached.get("cad_facts"):
            return cached

    extraction = extract_dxf_records(
        path,
        discipline,
        cache_root=cache_root,
        work_dir=work_dir,
        search_roots=search_roots,
    )
    payload = records_to_cad_facts(extraction, source_path=path)
    if cache_root is not None:
        save_cached_json(cache_root, key=cache_key, suffix="cad_facts", payload=payload)
    return payload


def extraction_to_coordinate_profile(
    extraction: DxfGeometryExtraction,
    *,
    rel_path: str,
    min_area_mm2: float = 40_000.0,
) -> dict[str, object]:
    """Real coordinate-audit profile from ezdxf extraction (replaces APS heuristic)."""
    mm_factor = insunits_to_mm_factor(int(extraction.insunits or 0))
    if mm_factor <= 0:
        mm_factor = 1000.0

    physical = [record for record in extraction.records if record.is_physical]
    entity_types: Counter[str] = Counter(record.dxftype for record in physical)
    primary = 0
    mins_x: list[float] = []
    mins_y: list[float] = []
    maxs_x: list[float] = []
    maxs_y: list[float] = []
    for record in physical:
        min_x, min_y, max_x, max_y = record.model_bounds
        area_mm2 = abs(max_x - min_x) * abs(max_y - min_y) * mm_factor * mm_factor
        if area_mm2 >= min_area_mm2:
            primary += 1
        mins_x.append(min_x * mm_factor)
        mins_y.append(min_y * mm_factor)
        maxs_x.append(max_x * mm_factor)
        maxs_y.append(max_y * mm_factor)

    if not physical:
        return {
            "raw_entity_count": 0,
            "raw_primary_candidate_count": 0,
            "raw_annotation_count": 0,
            "raw_bbox_only_count": 0,
            "bounds_mm": [0.0, 0.0, 0.0, 0.0],
            "centroid_mm": [0.0, 0.0],
            "dominant_cluster_bounds_mm": [0.0, 0.0, 0.0, 0.0],
            "dominant_cluster_centroid_mm": [0.0, 0.0],
            "dominant_entity_types": [],
            "units_to_mm_factor": mm_factor,
            "profile_source": LOCAL_EXTRACTOR,
            "rel_path": rel_path,
        }

    bounds_mm = [min(mins_x), min(mins_y), max(maxs_x), max(maxs_y)]
    centroid_mm = [(bounds_mm[0] + bounds_mm[2]) / 2.0, (bounds_mm[1] + bounds_mm[3]) / 2.0]
    dominant_types = [name for name, _count in entity_types.most_common(5)]
    return {
        "raw_entity_count": len(physical),
        "raw_primary_candidate_count": primary,
        "raw_annotation_count": len(physical) - primary,
        "raw_bbox_only_count": 0,
        "bounds_mm": bounds_mm,
        "centroid_mm": centroid_mm,
        "dominant_cluster_bounds_mm": bounds_mm,
        "dominant_cluster_centroid_mm": centroid_mm,
        "dominant_entity_types": dominant_types,
        "units_to_mm_factor": mm_factor,
        "profile_source": LOCAL_EXTRACTOR,
        "rel_path": rel_path,
    }


def extract_elements_from_local_cad(
    path: Path,
    discipline: Discipline,
    *,
    level_id: str,
    translation_mm: tuple[float, float],
    coordination_issue_key: str,
    max_entities: int = 400,
    min_area_mm2: float = 40_000.0,
    cache_root: Path | None = None,
    work_dir: Path | None = None,
    level_doc: Any | None = None,
) -> list[Element25D]:
    del level_doc
    extraction = extract_dxf_records(path, discipline, cache_root=cache_root, work_dir=work_dir)
    return records_to_elements25d(
        extraction,
        discipline,
        level_id=level_id,
        translation_mm=translation_mm,
        path_label=path.stem,
        coordination_issue_key=coordination_issue_key,
        max_entities=max_entities,
        min_area_mm2=min_area_mm2,
    )
