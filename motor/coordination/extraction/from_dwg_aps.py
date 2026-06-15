"""DWG extraction via APS Model Derivative with cache and viewer-dump fallback."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from coordination.extraction.aps_cache import file_cache_key, load_cached_json, save_cached_json
from coordination.extraction.from_aps_viewer_dump import elements_from_viewer_dump
from coordination.extraction.from_autodesk_properties import bulk_elements_from_autodesk_raw
from coordination.selection.level_inference import infer_level_from_view_name
from coordination.core.models_25d import Discipline, Element25D
from coordination.core.nasas_paths import translate_footprint
from coordination.core.registry import ProjectLevelRegistryDocument

logger = logging.getLogger("dupla.coordination.dwg_aps")


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
            min_area_mm2=min_area_m2 * 1_000_000.0,
        )
        if viewer_elements:
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
        except Exception:
            logger.exception("extract_dwg_data fallo para %s", path)
            return []
        save_cached_json(cache_root, key=cache_key, suffix="raw", payload=raw)

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
            min_area_mm2=min_area_m2 * 1_000_000.0,
        )
        if viewer_elements:
            return viewer_elements

    proxy = _fallback_proxy_elements(
        raw,
        path=path,
        discipline=discipline,
        default_level_id=level_id,
        translation_mm=translation_mm,
        coordination_issue_key=coordination_issue_key,
        max_entities=max_entities,
        min_area_m2=min_area_m2,
        level_doc=level_doc,
    )
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
        )
        dx, dy = translation_mm
        for el in bulk:
            fp = translate_footprint(list(el.footprint_coords_mm), dx, dy)
            metadata = dict(el.metadata)
            metadata.update(
                {
                    "coordination_issue_key": coordination_issue_key,
                    "source": "dwg_aps_properties_proxy",
                    "dwg_path": path.name,
                    "geometry_source": "dwg_aps_properties_proxy",
                    "geometry_quality": "proxy",
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
