"""DWG extraction via APS Model Derivative with cache and viewer-dump fallback."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from coordination.extraction.aps_cache import file_cache_key, load_cached_json, save_cached_json
from coordination.extraction.from_aps_viewer_dump import elements_from_viewer_dump
from coordination.extraction.from_autodesk_properties import (
    bulk_elements_from_autodesk_raw,
    min_area_m2_for_discipline,
)
from coordination.selection.level_inference import infer_level_from_view_name
from coordination.core.models_25d import Discipline, Element25D
from coordination.core.nasas_paths import translate_footprint
from coordination.core.registry import ProjectLevelRegistryDocument

logger = logging.getLogger("dupla.coordination.dwg_aps")


def _save_diagnostics(
    cache_root: Path | None,
    cache_key: str,
    payload: dict[str, Any],
) -> None:
    if cache_root is None:
        return
    save_cached_json(cache_root, key=cache_key, suffix="diagnostics", payload=payload)


def extract_elements_from_dwg_via_aps(
    path: Path,
    discipline: Discipline,
    *,
    level_id: str,
    translation_mm: tuple[float, float],
    token: str | dict[str, Any],
    bucket_name: str,
    coordination_issue_key: str,
    max_entities: int = 400,
    min_area_m2: float = 3.0,
    translation_timeout_seconds: int = 3600,
    poll_interval_seconds: int = 10,
    max_property_wait_seconds: int = 3600,
    cache_root: Path | None = None,
    level_doc: ProjectLevelRegistryDocument | None = None,
) -> list[Element25D]:
    """Upload the DWG, reuse APS translation data, and prefer cached Viewer geometry."""
    from aps_integration.model_derivative import extract_dwg_data
    from aps_integration.oss_manager import upload_file_to_bucket

    cache_key = file_cache_key(path)
    effective_min_area = min(min_area_m2, min_area_m2_for_discipline(discipline))
    diagnostics: dict[str, Any] = {
        "source": "dwg_aps",
        "path": path.name,
        "discipline": discipline.value,
        "min_area_m2": effective_min_area,
        "viewer_elements": 0,
        "proxy_elements": 0,
        "aps_error": None,
    }

    cached_viewer = load_cached_json(cache_root, key=cache_key, suffix="viewer")
    if isinstance(cached_viewer, dict):
        viewer_elements = elements_from_viewer_dump(
            cached_viewer,
            discipline=discipline,
            level_doc=level_doc,
            default_level_id=level_id,
            translation_mm=translation_mm,
            path_label=path.stem,
            coordination_issue_key=coordination_issue_key,
            max_entities=max_entities,
            min_area_mm2=effective_min_area * 1_000_000.0,
        )
        if viewer_elements:
            diagnostics["viewer_elements"] = len(viewer_elements)
            diagnostics["result"] = "viewer_cache"
            _save_diagnostics(cache_root, cache_key, diagnostics)
            logger.info("APS Viewer cache %s -> %d elementos", path.name, len(viewer_elements))
            return viewer_elements

    raw = load_cached_json(cache_root, key=cache_key, suffix="raw")
    if raw is None:
        suffix = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
        object_name = upload_file_to_bucket(
            token,
            bucket_name,
            str(path),
            unique_suffix=suffix,
        )
        if not object_name:
            logger.warning("No se pudo subir DWG a APS: %s", path)
            diagnostics["aps_error"] = "upload_failed"
            diagnostics["result"] = "empty"
            _save_diagnostics(cache_root, cache_key, diagnostics)
            return []
        try:
            raw = extract_dwg_data(
                token,
                bucket_name,
                object_name,
                views=("2d",),
                translation_timeout_seconds=translation_timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                max_property_wait_seconds=max_property_wait_seconds,
            )
        except Exception as exc:
            logger.exception("extract_dwg_data fallo para %s", path)
            diagnostics["aps_error"] = str(exc)
            diagnostics["result"] = "empty"
            _save_diagnostics(cache_root, cache_key, diagnostics)
            return []
        save_cached_json(cache_root, key=cache_key, suffix="raw", payload=raw)

    view_stats = []
    for view in raw.get("views") or []:
        if isinstance(view, dict):
            view_stats.append(
                {
                    "name": view.get("name"),
                    "object_count": view.get("object_count"),
                    "tree_object_count": view.get("tree_object_count"),
                    "properties_fetched": view.get("properties_fetched"),
                    "objects_with_area": view.get("objects_with_area"),
                    "deep_fetch_used": view.get("deep_fetch_used"),
                }
            )
    diagnostics["view_stats"] = view_stats

    viewer_dump = raw.get("viewer_geometry") if isinstance(raw, dict) else None
    if isinstance(viewer_dump, dict):
        save_cached_json(cache_root, key=cache_key, suffix="viewer", payload=viewer_dump)
        viewer_elements = elements_from_viewer_dump(
            viewer_dump,
            discipline=discipline,
            level_doc=level_doc,
            default_level_id=level_id,
            translation_mm=translation_mm,
            path_label=path.stem,
            coordination_issue_key=coordination_issue_key,
            max_entities=max_entities,
            min_area_mm2=effective_min_area * 1_000_000.0,
        )
        if viewer_elements:
            diagnostics["viewer_elements"] = len(viewer_elements)
            diagnostics["result"] = "viewer_geometry"
            _save_diagnostics(cache_root, cache_key, diagnostics)
            return viewer_elements

    proxy = _fallback_proxy_elements(
        raw,
        path=path,
        discipline=discipline,
        default_level_id=level_id,
        translation_mm=translation_mm,
        coordination_issue_key=coordination_issue_key,
        max_entities=max_entities,
        min_area_m2=effective_min_area,
        level_doc=level_doc,
    )
    diagnostics["proxy_elements"] = len(proxy)
    diagnostics["result"] = "proxy" if proxy else "empty"
    _save_diagnostics(cache_root, cache_key, diagnostics)
    logger.info("APS DWG %s -> %d elementos proxy (%s)", path.name, len(proxy), discipline.value)
    return proxy


def _fallback_proxy_elements(
    raw: dict[str, Any],
    *,
    path: Path,
    discipline: Discipline,
    default_level_id: str,
    translation_mm: tuple[float, float],
    coordination_issue_key: str,
    max_entities: int,
    min_area_m2: float,
    level_doc: ProjectLevelRegistryDocument | None,
) -> list[Element25D]:
    views = raw.get("views") or []
    out: list[Element25D] = []
    remaining = max_entities
    for view in views:
        if remaining <= 0:
            break
        view_name = str(view.get("name") or "Unnamed view")
        level_resolution = infer_level_from_view_name(
            view_name,
            doc=level_doc,
            default_level_id=default_level_id,
        )
        bulk = bulk_elements_from_autodesk_raw(
            {"views": [view]},
            level_id=level_resolution.level_id,
            min_area_m2=min_area_m2,
            max_entities=remaining,
            default_discipline=discipline,
        )
        dx, dy = translation_mm
        for el in bulk:
            fp = translate_footprint(list(el.footprint_coords_mm), dx, dy)
            metadata = dict(el.metadata)
            quality = str(metadata.get("geometry_quality") or "proxy")
            metadata.update(
                {
                    "coordination_issue_key": coordination_issue_key,
                    "source": "dwg_aps_properties_proxy",
                    "dwg_path": path.name,
                    "geometry_source": "dwg_aps_properties_proxy",
                    "geometry_quality": quality,
                    "level_assignment_source": level_resolution.source,
                    "sheet_or_view_name": view_name,
                }
            )
            out.append(
                el.model_copy(
                    update={
                        "discipline": discipline,
                        "footprint_coords_mm": fp,
                        "metadata": metadata,
                        "id": f"aps_dwg_{path.stem}_{el.id}",
                        "source_ref": f"{path.as_posix()}|{el.source_ref}",
                    }
                )
            )
            remaining -= 1
            if remaining <= 0:
                break
    return out
