"""Orquesta el volcado de geometría 2D real vía APS Viewer headless (Node/Puppeteer)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("dupla.aps.viewer_geometry")

_MOTOR_ROOT = Path(__file__).resolve().parents[1]
_MONOREPO_ROOT = _MOTOR_ROOT.parent
_DUMP_LOCK = _MONOREPO_ROOT / "var" / "locks" / "viewer_geometry_dump.lock"
_DUMP_SCRIPT_DIR = _MONOREPO_ROOT / "scripts" / "spike_f2d"
_DUMP_JS = _DUMP_SCRIPT_DIR / "dump_geometry.js"

# Coordenadas del Viewer 2D suelen venir en pulgadas (plano 36×24 in ≈ 914×610 mm).
VIEWER_UNITS_TO_MM = 25.4


def dump_script_dir() -> Path:
    return _DUMP_SCRIPT_DIR


def node_modules_ready() -> bool:
    return (_DUMP_SCRIPT_DIR / "node_modules" / "puppeteer").is_dir()


def ensure_node_deps() -> None:
    if node_modules_ready():
        return
    logger.info("Instalando dependencias Node en %s", _DUMP_SCRIPT_DIR)
    subprocess.run(
        ["npm", "install", "--no-audit", "--no-fund"],
        cwd=str(_DUMP_SCRIPT_DIR),
        check=True,
        timeout=300,
    )


def preferred_view_names_from_raw(raw: dict[str, Any] | None, *, max_names: int = 8) -> str:
    """Ordena vistas APS por object_count descendente para el dump Viewer."""
    if not isinstance(raw, dict):
        return ""
    stats = []
    for view in raw.get("views") or []:
        if not isinstance(view, dict):
            continue
        name = str(view.get("name") or "").strip()
        if not name:
            continue
        count = int(view.get("object_count") or view.get("tree_object_count") or 0)
        stats.append((count, name))
    stats.sort(key=lambda item: item[0], reverse=True)
    return ",".join(name for _, name in stats[:max_names])


def run_viewer_geometry_dump(
    *,
    urn: str,
    token: str,
    use_svf1: bool = True,
    timeout_seconds: int = 360,
    max_views: int | None = None,
    preferred_view_names: str = "",
) -> dict[str, Any] | None:
    """Ejecuta dump_geometry.js y devuelve el JSON crudo del Viewer."""
    if not _DUMP_JS.is_file():
        logger.error("No existe %s", _DUMP_JS)
        return None
    ensure_node_deps()

    if max_views is None:
        max_views = max(1, int(os.getenv("APS_VIEWER_MAX_VIEWS", "4")))

    urn_file = _DUMP_SCRIPT_DIR / ("urn_svf1_runtime.json" if use_svf1 else "urn_runtime.json")
    out_file = _DUMP_SCRIPT_DIR / ("dump_svf1_runtime.json" if use_svf1 else "dump_runtime.json")
    urn_file.write_text(json.dumps({"urn": urn}), encoding="utf-8")

    effective_timeout = int(timeout_seconds * max(1.0, max_views / 2.0))

    args = ["node", str(_DUMP_JS), "--urn-file", str(urn_file), "--out", str(out_file)]
    if use_svf1:
        args.append("--svf1")
    else:
        args.append("--svf2")
    args.extend(["--max-views", str(max_views)])
    args.extend(["--dump-timeout-ms", str(effective_timeout * 1000)])
    if preferred_view_names:
        args.extend(["--view-names", preferred_view_names])

    env = {**os.environ, "APS_TOKEN": token}
    env["APS_VIEWER_MAX_VIEWS"] = str(max_views)
    env["APS_VIEWER_GEOMETRY_TIMEOUT"] = str(effective_timeout)
    if preferred_view_names:
        env["APS_VIEWER_VIEW_NAMES"] = preferred_view_names
    if os.getenv("PUPPETEER_EXECUTABLE_PATH"):
        env["PUPPETEER_EXECUTABLE_PATH"] = os.environ["PUPPETEER_EXECUTABLE_PATH"]
    logger.info("Ejecutando volcado Viewer (%s) urn=%s…", "SVF1" if use_svf1 else "SVF2", urn[:24])

    _DUMP_LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock_path = str(_DUMP_LOCK)

    try:
        proc = subprocess.run(
            ["flock", "-x", lock_path, *args],
            cwd=str(_DUMP_SCRIPT_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=effective_timeout + 60,
        )
    except FileNotFoundError:
        proc = subprocess.run(
            args,
            cwd=str(_DUMP_SCRIPT_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=effective_timeout + 60,
        )
    except subprocess.TimeoutExpired:
        logger.error("Timeout en volcado Viewer (%ds)", effective_timeout)
        return None

    if proc.stdout:
        for line in proc.stdout.strip().splitlines()[-20:]:
            logger.info("[viewer-dump] %s", line)
    if proc.returncode != 0 and proc.stderr:
        logger.warning("[viewer-dump stderr] %s", proc.stderr[-2000:])

    if not out_file.is_file():
        return None
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    if payload.get("status") != "done":
        logger.warning("Viewer dump status=%s error=%s", payload.get("status"), payload.get("error"))
        return None
    return payload


def raw_dump_to_viewer_geometry(
    raw_dump: dict[str, Any],
    *,
    units_to_mm: float = VIEWER_UNITS_TO_MM,
    max_objects_per_view: int = 500,
) -> dict[str, Any]:
    """Convierte salida de dump_geometry.js al formato esperado por elements_from_viewer_dump."""
    views_out: list[dict[str, Any]] = []
    for view in raw_dump.get("views") or []:
        objects_in = view.get("objects") or []
        scaled_objects: list[dict[str, Any]] = []
        for obj in objects_in[:max_objects_per_view]:
            primitives = []
            for prim in obj.get("primitives") or []:
                scaled = dict(prim)
                kind = str(prim.get("type") or "").lower()
                if kind == "line":
                    scaled["x1"] = float(prim["x1"]) * units_to_mm
                    scaled["y1"] = float(prim["y1"]) * units_to_mm
                    scaled["x2"] = float(prim["x2"]) * units_to_mm
                    scaled["y2"] = float(prim["y2"]) * units_to_mm
                elif kind == "arc":
                    scaled["cx"] = float(prim["cx"]) * units_to_mm
                    scaled["cy"] = float(prim["cy"]) * units_to_mm
                    if "radius" in prim:
                        scaled["radius"] = float(prim["radius"]) * units_to_mm
                elif kind == "rect":
                    scaled["x"] = float(prim["x"]) * units_to_mm
                    scaled["y"] = float(prim["y"]) * units_to_mm
                    scaled["width"] = float(prim["width"]) * units_to_mm
                    scaled["height"] = float(prim["height"]) * units_to_mm
                elif kind == "quad":
                    pts = []
                    for pt in prim.get("points") or []:
                        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                            continue
                        if pt[0] is None or pt[1] is None:
                            continue
                        pts.append([float(pt[0]) * units_to_mm, float(pt[1]) * units_to_mm])
                    if len(pts) < 3:
                        continue
                    scaled["points"] = pts
                primitives.append(scaled)
            if not primitives:
                continue
            scaled_objects.append(
                {
                    "dbId": obj.get("dbId"),
                    "layer": obj.get("layer") or (view.get("dbLayer") or {}).get(str(obj.get("dbId")), ""),
                    "name": obj.get("name") or "",
                    "handle": obj.get("handle") or "",
                    "primitives": primitives,
                }
            )
        if scaled_objects:
            views_out.append({"name": view.get("name") or "Unnamed view", "objects": scaled_objects})
    return {
        "format": raw_dump.get("format"),
        "units_to_mm": units_to_mm,
        "views": views_out,
    }


def enrich_layers_from_property_db(
    viewer_geom: dict[str, Any],
    *,
    token: str | dict[str, Any],
    model_urn: str,
    cache_path: Path | None = None,
) -> dict[str, Any]:
    from aps_integration.f2d_resources import download_property_database, query_dbid_layers, query_dbid_names

    db_path = download_property_database(token, model_urn, cache_path=cache_path)
    layers = query_dbid_layers(db_path)
    names = query_dbid_names(db_path)
    enriched = 0
    for view in viewer_geom.get("views") or []:
        for obj in view.get("objects") or []:
            db_id = obj.get("dbId")
            if db_id is None:
                continue
            layer = layers.get(int(db_id))
            if layer and (not obj.get("layer") or str(obj.get("layer")) in {"0", ""}):
                obj["layer"] = layer
                enriched += 1
            name = names.get(int(db_id))
            if name and (not obj.get("name") or str(obj.get("name")) in {"0", ""}):
                obj["name"] = name
                enriched += 1
    logger.info("Capas enriquecidas desde PropertyDB: %d objetos", enriched)
    return viewer_geom


def _manifest_has_svf1(manifest: dict | None) -> bool:
    from aps_integration.model_derivative import _iter_manifest_nodes

    if not manifest:
        return False
    for node in _iter_manifest_nodes(manifest):
        mime = str(node.get("mime") or "").lower()
        if mime == "application/autodesk-f2d" and node.get("status") == "success":
            return True
    return False


def ensure_svf1_translation(
    token: str | dict[str, object],
    urn: str,
    *,
    translation_timeout_seconds: int = 1800,
    poll_interval_seconds: int = 10,
) -> bool:
    """Garantiza derivado SVF1 (f2d) para extracción geométrica real."""
    from aps_integration.model_derivative import get_manifest, translate_to_svf1, wait_for_translation

    manifest = get_manifest(token, urn)
    if _manifest_has_svf1(manifest):
        return True
    translate_to_svf1(token, urn, views=("2d",))
    status = wait_for_translation(
        token,
        urn,
        timeout=translation_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    return status == "success"


def extract_viewer_geometry_for_urn(
    *,
    urn: str,
    token: str,
    use_svf1: bool = True,
    timeout_seconds: int = 360,
    max_objects_per_view: int = 500,
    property_db_cache: Path | None = None,
    ensure_svf1: bool = True,
    translation_timeout_seconds: int = 1800,
    raw: dict[str, Any] | None = None,
    max_views: int | None = None,
) -> dict[str, Any] | None:
    """Pipeline completo: dump headless → viewer_geometry normalizado + capas."""
    if use_svf1 and ensure_svf1:
        try:
            if not ensure_svf1_translation(
                token,
                urn,
                translation_timeout_seconds=translation_timeout_seconds,
            ):
                logger.warning("SVF1 translation no completó para urn=%s", urn[:24])
        except Exception as exc:
            logger.warning("No se pudo garantizar SVF1: %s", exc)
            return None

    preferred_views = preferred_view_names_from_raw(raw)
    raw_dump = run_viewer_geometry_dump(
        urn=urn,
        token=token,
        use_svf1=use_svf1,
        timeout_seconds=timeout_seconds,
        max_views=max_views,
        preferred_view_names=preferred_views,
    )
    if raw_dump is None:
        return None
    viewer_geom = raw_dump_to_viewer_geometry(raw_dump, max_objects_per_view=max_objects_per_view)
    total_objects = sum(len(v.get("objects") or []) for v in viewer_geom.get("views") or [])
    if total_objects == 0:
        logger.warning("Viewer dump sin objetos con primitivas")
        return None
    try:
        enrich_layers_from_property_db(
            viewer_geom, token=token, model_urn=urn, cache_path=property_db_cache
        )
    except Exception as exc:
        logger.warning("No se pudo enriquecer capas desde PropertyDB: %s", exc)
    logger.info("viewer_geometry: %d vistas, %d objetos", len(viewer_geom["views"]), total_objects)
    return viewer_geom
