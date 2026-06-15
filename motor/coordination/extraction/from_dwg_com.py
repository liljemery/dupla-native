"""Extract 2.5D elements from native DWG files via AutoCAD/Civil 3D COM."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon

from coordination.core.models_25d import Discipline, Element25D, ZInterval
from coordination.core.nasas_paths import translate_footprint

logger = logging.getLogger("dupla.coordination.dwg_com")

try:
    import win32com.client
    from win32com.client import Dispatch, GetActiveObject

    HAS_WIN32COM = True
except Exception:
    HAS_WIN32COM = False

try:
    import pywintypes
except Exception:
    pywintypes = None


INSUNITS_TO_MM = {
    0: 1.0,
    1: 25.4,
    2: 304.8,
    4: 1.0,
    5: 10.0,
    6: 1000.0,
    7: 1_000_000.0,
    10: 914.4,
    14: 100.0,
}

ANNOTATION_TYPES = {
    "TEXT",
    "MTEXT",
    "DIMENSION",
    "LEADER",
    "MLEADER",
    "POINT",
    "XLINE",
    "RAY",
    "ATTRIBUTE",
    "ATTRIB",
}

NON_GEOMETRIC_LAYER_TOKENS = (
    "anno",
    "text",
    "note",
    "dim",
    "leyenda",
    "legend",
    "defpoints",
    "viewport",
    "vport",
    "tarjeta",
    "title",
    "cajetin",
    "border",
    "frame",
    "revision",
    "sello",
)

_COM_APP_CACHE: Any | None = None


def _app_is_alive(app: Any | None) -> bool:
    if app is None:
        return False
    try:
        _ = app.Name
        return True
    except Exception:
        return False


def _connect_autocad(*, force_new: bool = False) -> Any | None:
    global _COM_APP_CACHE
    if not HAS_WIN32COM:
        logger.warning("win32com no disponible; no se puede usar extractor COM.")
        return None
    if not force_new and _app_is_alive(_COM_APP_CACHE):
        return _COM_APP_CACHE
    if not force_new:
        for prog_id in ("AutoCAD.Application", "AeccXUiLand.AeccApplication"):
            try:
                _COM_APP_CACHE = GetActiveObject(prog_id)
                return _COM_APP_CACHE
            except Exception:
                continue
    try:
        dispatch_ex = getattr(win32com.client, "DispatchEx", None)
        if dispatch_ex is not None:
            app = dispatch_ex("AutoCAD.Application")
            app.Visible = False
            time.sleep(3.0)
            _COM_APP_CACHE = app
            return app
    except Exception:
        pass
    try:
        app = Dispatch("AutoCAD.Application")
        app.Visible = False
        time.sleep(3.0)
        _COM_APP_CACHE = app
        return app
    except Exception as exc:
        logger.warning("No se pudo conectar a AutoCAD/Civil 3D por COM: %s", exc)
        return None


def _is_retryable_com_error(exc: Exception) -> bool:
    if pywintypes is not None and isinstance(exc, pywintypes.com_error):
        if exc.args and exc.args[0] == -2147418111:
            return True
    return "Call was rejected by callee" in str(exc)


def _call_with_retry(func: Any, *args: Any, retries: int = 12, delay_seconds: float = 0.75, **kwargs: Any) -> Any:
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if attempt >= retries - 1 or not _is_retryable_com_error(exc):
                raise
            time.sleep(delay_seconds)
    raise RuntimeError("Retry loop agotado")


def _open_document(app: Any, path: Path) -> tuple[Any | None, bool]:
    target = str(path.resolve()).lower()
    try:
        for index in range(app.Documents.Count):
            doc = app.Documents.Item(index)
            if str(doc.FullName).lower() == target:
                return (doc, False)
    except Exception:
        pass

    try:
        _call_with_retry(app.Documents.Open, str(path.resolve()), True)
        time.sleep(1.0)
        doc = _call_with_retry(lambda: app.ActiveDocument)
        return (doc, True)
    except Exception as exc:
        if _is_retryable_com_error(exc):
            fresh = _connect_autocad(force_new=True)
            if fresh is not None and fresh is not app:
                try:
                    _call_with_retry(fresh.Documents.Open, str(path.resolve()), True, retries=20, delay_seconds=1.0)
                    time.sleep(1.5)
                    doc = _call_with_retry(lambda: fresh.ActiveDocument, retries=20, delay_seconds=1.0)
                    return (doc, True)
                except Exception as fresh_exc:
                    exc = fresh_exc
        logger.warning("No se pudo abrir %s por COM: %s", path.name, exc)
        return (None, False)


def _insunits_to_mm_factor(doc: Any) -> float:
    try:
        insunits = int(doc.GetVariable("INSUNITS"))
    except Exception:
        insunits = 0
    factor = INSUNITS_TO_MM.get(insunits)
    if factor is not None:
        return factor
    try:
        measurement = int(doc.GetVariable("MEASUREMENT"))
    except Exception:
        measurement = 1
    return 1.0 if measurement == 1 else 25.4


def _entity_type(entity: Any) -> str:
    raw = str(getattr(entity, "ObjectName", "AcDbEntity"))
    return raw.replace("AcDb", "").replace("BlockReference", "INSERT").upper()


def _layer_name(entity: Any) -> str:
    return str(getattr(entity, "Layer", "0") or "0")


def _skip_entity(entity_type: str, layer: str) -> bool:
    if entity_type in ANNOTATION_TYPES:
        return True
    layer_lower = layer.lower()
    return any(token in layer_lower for token in NON_GEOMETRIC_LAYER_TOKENS)


def _bbox_footprint_mm(
    *,
    min_pt: Any,
    max_pt: Any,
    factor_mm: float,
    translation_mm: tuple[float, float],
) -> tuple[list[tuple[float, float]], float] | None:
    min_x = float(min_pt[0]) * factor_mm
    min_y = float(min_pt[1]) * factor_mm
    max_x = float(max_pt[0]) * factor_mm
    max_y = float(max_pt[1]) * factor_mm
    if max_x <= min_x or max_y <= min_y:
        return None
    footprint = [
        (min_x, min_y),
        (max_x, min_y),
        (max_x, max_y),
        (min_x, max_y),
    ]
    footprint = translate_footprint(footprint, translation_mm[0], translation_mm[1])
    polygon = Polygon(footprint + [footprint[0]])
    area = float(polygon.area)
    if polygon.is_empty or area <= 0.0:
        return None
    return (footprint, area)


def extract_elements_from_dwg_via_com(
    path: Path,
    discipline: Discipline,
    *,
    level_id: str,
    translation_mm: tuple[float, float] = (0.0, 0.0),
    min_area_mm2: float = 50_000.0,
    max_entities: int = 400,
    z_thickness_mm: float = 250.0,
    z_ref_mm: float | None = None,
) -> list[Element25D]:
    app = _connect_autocad()
    if app is None:
        return []

    doc, opened_here = _open_document(app, path)
    if doc is None:
        return []

    factor_mm = _insunits_to_mm_factor(doc)
    z_base = 0.0 if z_ref_mm is None else float(z_ref_mm)
    candidates: list[tuple[float, Element25D]] = []

    try:
        modelspace = _call_with_retry(lambda: doc.ModelSpace)
        entity_count = int(_call_with_retry(lambda: modelspace.Count))
        for index in range(entity_count):
            try:
                entity = _call_with_retry(modelspace.Item, index)
                entity_type = _entity_type(entity)
                layer = _layer_name(entity)
                if _skip_entity(entity_type, layer):
                    continue

                min_pt, max_pt = _call_with_retry(entity.GetBoundingBox)
                bbox_result = _bbox_footprint_mm(
                    min_pt=min_pt,
                    max_pt=max_pt,
                    factor_mm=factor_mm,
                    translation_mm=translation_mm,
                )
                if bbox_result is None:
                    continue
                footprint, area = bbox_result
                if area < min_area_mm2:
                    continue

                min_z = float(min_pt[2]) * factor_mm if len(min_pt) > 2 else 0.0
                max_z = float(max_pt[2]) * factor_mm if len(max_pt) > 2 else min_z
                thickness = max(max_z - min_z, 0.0)
                if thickness < 1.0:
                    thickness = z_thickness_mm

                handle = str(getattr(entity, "Handle", index))
                candidates.append(
                    (
                        area,
                        Element25D(
                            id=f"dwgcom_{path.stem}_{index}_{handle}",
                            source_ref=f"{path.as_posix()}|{layer}|{entity_type}|{handle}",
                            discipline=discipline,
                            category=f"{entity_type}:{layer}",
                            footprint_coords_mm=footprint,
                            z_data=ZInterval(
                                level_id=level_id,
                                z_ref_raw_mm=min_z + z_base,
                                thickness_mm=thickness,
                                reference_point="bottom",
                            ),
                            metadata={
                                "file": path.name,
                                "layer": layer,
                                "handle": handle,
                                "area_mm2": area,
                                "source": "cad_com",
                                "geometry_source": "dwg_com_bbox",
                                "geometry_quality": "medium",
                                "level_assignment_source": "default_level",
                                "sheet_or_view_name": path.stem,
                            },
                        ),
                    )
                )
            except Exception:
                continue
    finally:
        if opened_here:
            try:
                _call_with_retry(doc.Close, False, retries=6, delay_seconds=0.5)
            except Exception:
                pass

    candidates.sort(key=lambda item: -item[0])
    return [element for _, element in candidates[:max_entities]]
