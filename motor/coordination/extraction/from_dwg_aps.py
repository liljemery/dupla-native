"""DWG extraction via APS Model Derivative with cache and viewer-dump fallback."""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Any

from coordination.extraction.aps_cache import file_cache_key, load_cached_json, save_cached_json
from coordination.extraction.from_aps_viewer_dump import (
    elements_from_viewer_dump,
    viewer_dump_has_geometry,
)
from coordination.extraction.from_autodesk_properties import (
    bulk_elements_from_autodesk_raw,
    min_area_m2_for_discipline,
)
from coordination.selection.level_inference import infer_level_from_view_name
from coordination.core.models_25d import Discipline, Element25D
from coordination.core.nasas_paths import translate_footprint
from coordination.core.registry import ProjectLevelRegistryDocument

logger = logging.getLogger("dupla.coordination.dwg_aps")
REPO_ROOT = Path(__file__).resolve().parents[3]
VIEWER_ENGINE_SCRIPT = REPO_ROOT / "backend" / "viewer-engine" / "extract_fragments.js"
MAX_VIEWER_FRAGMENT_ELEMENTS = 250_000

# Flag por proceso: cuando APS deniega por cuota (403 ProductAccessRequiresCapacity),
# el resto de archivos de la misma corrida salta APS y va directo al fallback local/PDF.
_APS_CAPACITY_EXHAUSTED = False


def _aps_capacity_exhausted() -> bool:
    return _APS_CAPACITY_EXHAUSTED


def _mark_aps_capacity_exhausted() -> None:
    global _APS_CAPACITY_EXHAUSTED
    _APS_CAPACITY_EXHAUSTED = True


def _save_diagnostics(
    cache_root: Path | None,
    cache_key: str,
    payload: dict[str, Any],
) -> None:
    if cache_root is None:
        return
    save_cached_json(cache_root, key=cache_key, suffix="diagnostics", payload=payload)


def _viewer_artifact_path(cache_root: Path | None, urn: str) -> Path | None:
    if cache_root is None or not urn:
        return None
    return cache_root / f"{urn}.viewer.json"


def _load_viewer_artifact(cache_root: Path | None, *, urn: str, cache_key: str) -> dict[str, Any] | None:
    path = _viewer_artifact_path(cache_root, urn)
    if path is None or not path.is_file():
        return None
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = payload.get("cache_metadata") if isinstance(payload, dict) else None
    if not isinstance(metadata, dict):
        logger.info("APS Viewer artifact stale: missing cache_metadata (%s)", path)
        return None
    if metadata.get("urn") != urn:
        logger.info("APS Viewer artifact stale: urn mismatch (%s)", path)
        return None
    if metadata.get("source_cache_key") != cache_key:
        logger.info(
            "APS Viewer artifact stale: source cache key mismatch path=%s artifact=%s current=%s",
            path,
            metadata.get("source_cache_key"),
            cache_key,
        )
        return None
    return payload


def _token_value(token: str | dict[str, Any]) -> str:
    if isinstance(token, dict):
        return str(token.get("access_token") or "")
    return str(token)


def _extract_viewer_artifact(
    *,
    cache_root: Path | None,
    urn: str,
    token: str | dict[str, Any],
    cache_key: str,
    timeout_seconds: int,
) -> dict[str, Any] | None:
    path = _viewer_artifact_path(cache_root, urn)
    if path is None:
        return None
    access_token = _token_value(token)
    if not access_token:
        logger.warning("No APS token available for headless Viewer fragment extraction")
        return None
    if not VIEWER_ENGINE_SCRIPT.is_file():
        logger.warning("Headless Viewer fragment extractor not found: %s", VIEWER_ENGINE_SCRIPT)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "node",
        str(VIEWER_ENGINE_SCRIPT),
        "--urn",
        urn,
        "--token",
        access_token,
        "--output",
        str(path),
        "--all-viewables",
        "1",
        "--timeout",
        str(max(timeout_seconds, 60) * 1000),
    ]
    logger.info("Running APS headless fragment extractor -> %s", path)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(VIEWER_ENGINE_SCRIPT.parent),
            text=True,
            capture_output=True,
            timeout=max(timeout_seconds, 60),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("APS headless fragment extractor failed before completion: %s", exc)
        return None
    if result.stdout:
        for line in result.stdout.splitlines():
            logger.info("viewer-engine: %s", line)
    if result.stderr:
        for line in result.stderr.splitlines():
            logger.warning("viewer-engine: %s", line)
    if result.returncode != 0:
        logger.warning("APS headless fragment extractor exited with code %s", result.returncode)
        return None
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = dict(payload.get("cache_metadata") or {})
    metadata.update({"urn": urn, "source_cache_key": cache_key})
    payload["cache_metadata"] = metadata
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def _load_or_extract_viewer_artifact(
    *,
    cache_root: Path | None,
    raw: dict[str, Any],
    token: str | dict[str, Any],
    cache_key: str,
    timeout_seconds: int,
) -> dict[str, Any] | None:
    urn = str(raw.get("urn") or "")
    if not urn:
        return None
    cached = _load_viewer_artifact(cache_root, urn=urn, cache_key=cache_key)
    if cached is not None:
        return cached
    return _extract_viewer_artifact(
        cache_root=cache_root,
        urn=urn,
        token=token,
        cache_key=cache_key,
        timeout_seconds=timeout_seconds,
    )


def _convert_viewer_to_elements(
    viewer_dump: dict[str, Any],
    *,
    discipline: Discipline,
    level_doc: ProjectLevelRegistryDocument | None,
    level_id: str,
    translation_mm: tuple[float, float],
    path_label: str,
    coordination_issue_key: str,
    max_entities: int,
    min_area_mm2: float,
) -> list[Element25D]:
    """Convierte viewer dump; reintenta con fast_footprint si el objeto es muy pesado."""
    common = dict(
        discipline=discipline,
        level_doc=level_doc,
        default_level_id=level_id,
        translation_mm=translation_mm,
        path_label=path_label,
        coordination_issue_key=coordination_issue_key,
        max_entities=max_entities,
        min_area_mm2=min_area_mm2,
    )
    elements = elements_from_viewer_dump(viewer_dump, **common)
    if elements or not viewer_dump_has_geometry(viewer_dump):
        return elements
    logger.info("Reintentando conversión viewer con fast_footprint para %s", path_label)
    return elements_from_viewer_dump(viewer_dump, fast_footprint=True, **common)


def _is_transient_translation_failure(cached_diag: dict[str, Any]) -> bool:
    prior_error = str(cached_diag.get("aps_error") or "")
    prior_result = str(cached_diag.get("result") or "")
    if prior_result != "empty":
        return False
    if "Translation failed for URN" not in prior_error:
        return False
    if "AutoCAD-InvalidFile" in prior_error or "invalid and cannot be viewed" in prior_error:
        return False
    return True


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
    from aps_integration.model_derivative import ApsCapacityError, extract_dwg_data
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

    # Si una corrida ya tocó el límite de cuota de APS, no reintentamos por archivo:
    # cada intento gasta una subida + un 403 inútil. Vamos directo al fallback local/PDF.
    if _aps_capacity_exhausted():
        diagnostics["aps_error"] = "quota_exceeded (cuota APS agotada en esta corrida)"
        diagnostics["result"] = "quota_exceeded"
        _save_diagnostics(cache_root, cache_key, diagnostics)
        logger.warning("APS omitido por cuota agotada (run): %s", path.name)
        return []

    cached_diag = load_cached_json(cache_root, key=cache_key, suffix="diagnostics")
    if isinstance(cached_diag, dict):
        prior_error = str(cached_diag.get("aps_error") or "")
        prior_result = str(cached_diag.get("result") or "")
        if "AutoCAD-InvalidFile" in prior_error or "invalid and cannot be viewed" in prior_error:
            diagnostics["aps_error"] = prior_error
            diagnostics["result"] = "invalid_file_cached"
            _save_diagnostics(cache_root, cache_key, diagnostics)
            logger.warning("APS omitido (DWG inválido en caché): %s", path.name)
            return []
        if _is_transient_translation_failure(cached_diag):
            logger.info("Reintentando traducción APS tras fallo transitorio: %s", path.name)
        elif (
            prior_result == "empty"
            and not load_cached_json(cache_root, key=cache_key, suffix="raw")
            and (
                "Translation failed for URN" in prior_error
                or "AutoCAD-InvalidFile" in prior_error
            )
        ):
            diagnostics.update({k: cached_diag.get(k) for k in ("aps_error", "view_stats") if cached_diag.get(k)})
            diagnostics["result"] = "invalid_file_cached"
            _save_diagnostics(cache_root, cache_key, diagnostics)
            logger.warning("APS omitido (fallo previo en caché): %s", path.name)
            return []

    cached_viewer = load_cached_json(cache_root, key=cache_key, suffix="viewer")
    if isinstance(cached_viewer, dict):
        viewer_elements = _convert_viewer_to_elements(
            cached_viewer,
            discipline=discipline,
            level_doc=level_doc,
            level_id=level_id,
            translation_mm=translation_mm,
            path_label=path.stem,
            coordination_issue_key=coordination_issue_key,
            max_entities=max(max_entities, MAX_VIEWER_FRAGMENT_ELEMENTS),
            min_area_mm2=effective_min_area * 1_000_000.0,
        )
        if viewer_elements:
            diagnostics["viewer_elements"] = len(viewer_elements)
            diagnostics["result"] = "viewer_cache"
            _save_diagnostics(cache_root, cache_key, diagnostics)
            logger.info("APS Viewer cache %s -> %d elementos exactos", path.name, len(viewer_elements))
            return viewer_elements
        logger.info("Caché viewer sin elementos útiles para %s; reintentando volcado", path.name)

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
        except ApsCapacityError as exc:
            _mark_aps_capacity_exhausted()
            logger.error(
                "APS sin cuota para %s — se usará fallback local/PDF. %s",
                path.name,
                exc,
            )
            diagnostics["aps_error"] = str(exc)
            diagnostics["result"] = "quota_exceeded"
            _save_diagnostics(cache_root, cache_key, diagnostics)
            return []
        except Exception as exc:
            logger.exception("extract_dwg_data fallo para %s", path)
            diagnostics["aps_error"] = str(exc)
            diagnostics["result"] = "empty"
            if "AutoCAD-InvalidFile" in str(exc) or "invalid and cannot be viewed" in str(exc):
                diagnostics["result"] = "invalid_file"
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
    diagnostics["urn"] = raw.get("urn") if isinstance(raw, dict) else None

    viewer_dump = raw.get("viewer_geometry") if isinstance(raw, dict) else None
    if not isinstance(viewer_dump, dict):
        viewer_dump = _load_or_extract_viewer_artifact(
            cache_root=cache_root,
            raw=raw,
            token=token,
            cache_key=cache_key,
            timeout_seconds=translation_timeout_seconds,
        )

    if not isinstance(viewer_dump, dict):
        viewer_dump = load_cached_json(cache_root, key=cache_key, suffix="viewer")

    if not isinstance(viewer_dump, dict) or not (viewer_dump.get("views") or []):
        viewer_dump = _try_extract_viewer_geometry(
            raw,
            token=token,
            path=path,
            cache_root=cache_root,
            cache_key=cache_key,
            diagnostics=diagnostics,
        )

    if isinstance(viewer_dump, dict):
        save_cached_json(cache_root, key=cache_key, suffix="viewer", payload=viewer_dump)
        viewer_elements = _convert_viewer_to_elements(
            viewer_dump,
            discipline=discipline,
            level_doc=level_doc,
            level_id=level_id,
            translation_mm=translation_mm,
            path_label=path.stem,
            coordination_issue_key=coordination_issue_key,
            max_entities=max(max_entities, MAX_VIEWER_FRAGMENT_ELEMENTS),
            min_area_mm2=effective_min_area * 1_000_000.0,
        )
        if viewer_elements:
            diagnostics["viewer_elements"] = len(viewer_elements)
            diagnostics["result"] = "viewer_geometry"
            _save_diagnostics(cache_root, cache_key, diagnostics)
            return viewer_elements
        if viewer_dump_has_geometry(viewer_dump):
            logger.warning(
                "Viewer dump con geometría pero 0 elementos convertidos para %s — omitiendo proxy",
                path.name,
            )
            diagnostics["result"] = "viewer_empty"
            _save_diagnostics(cache_root, cache_key, diagnostics)
            return []

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
    logger.info("APS DWG %s -> %d elementos proxy fallback (%s)", path.name, len(proxy), discipline.value)
    return proxy


def _resolve_access_token(token: str | dict[str, Any]) -> str:
    if isinstance(token, dict):
        return str(token.get("access_token") or token.get("token") or "")
    return str(token)


def _try_extract_viewer_geometry(
    raw: dict[str, Any],
    *,
    token: str | dict[str, Any],
    path: Path,
    cache_root: Path | None,
    cache_key: str,
    diagnostics: dict[str, Any],
) -> dict[str, Any] | None:
    """Volcado headless SVF1/SVF2 cuando no hay viewer_geometry en caché."""
    import os

    urn = str(raw.get("urn") or "")
    if not urn:
        return None
    if os.getenv("APS_VIEWER_GEOMETRY_DUMP", "true").lower() in {"0", "false", "no"}:
        return None

    try:
        from aps_integration.viewer_geometry import extract_viewer_geometry_for_urn
    except ImportError:
        logger.warning("aps_integration.viewer_geometry no disponible")
        return None

    access_token = _resolve_access_token(token)
    if not access_token:
        return None

    use_svf1 = os.getenv("APS_VIEWER_GEOMETRY_FORMAT", "svf1").lower() in {"svf1", "svf", "1", "true"}
    timeout = int(os.getenv("APS_VIEWER_GEOMETRY_TIMEOUT", "360"))

    logger.info("Volcando geometría Viewer (%s) para %s", "SVF1" if use_svf1 else "SVF2", path.name)
    diagnostics["viewer_dump_attempted"] = True
    diagnostics["viewer_dump_format"] = "svf1" if use_svf1 else "svf2"

    viewer_geom = extract_viewer_geometry_for_urn(
        urn=urn,
        token=access_token,
        use_svf1=use_svf1,
        timeout_seconds=timeout,
        max_objects_per_view=int(os.getenv("APS_VIEWER_MAX_OBJECTS_PER_VIEW", "500")),
        property_db_cache=(cache_root / f"{cache_key}.props.db") if cache_root else None,
        raw=raw,
    )
    if viewer_geom is None:
        diagnostics["viewer_dump_result"] = "empty"
        return None

    save_cached_json(cache_root, key=cache_key, suffix="viewer", payload=viewer_geom)
    diagnostics["viewer_dump_result"] = "ok"
    diagnostics["viewer_dump_views"] = len(viewer_geom.get("views") or [])
    return viewer_geom


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
                    "source": "proxy_FALLBACK",
                    "dwg_path": path.name,
                    "geometry_source": "proxy_FALLBACK",
                    "geometry_quality": "proxy",
                    "coordinate_unit": "millimeters",
                    "fallback_from": "dwg_aps_properties_proxy",
                    "fallback_reason": "no_aps_fragment_geometry",
                    "legacy_proxy_quality": quality,
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
