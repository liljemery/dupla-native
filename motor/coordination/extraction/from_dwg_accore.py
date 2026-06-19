"""Extract 2.5D elements from native DWG files via AutoCAD Core Console."""

from __future__ import annotations

import json
import logging
import math
import subprocess
import sys as _sys
if _sys.platform == "win32":
    from ctypes import create_unicode_buffer, windll
else:
    # accore (AutoCAD Core Console) is Windows-only; stub on other platforms
    windll = None  # type: ignore[assignment]
    def create_unicode_buffer(size: int, *_args, **_kwargs):  # type: ignore[misc]
        raise NotImplementedError("create_unicode_buffer is Windows-only")
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Polygon

from coordination.extraction.from_dwg_com import NON_GEOMETRIC_LAYER_TOKENS
from coordination.core.models_25d import Discipline, Element25D, ZInterval
from coordination.core.nasas_paths import translate_footprint
from coordination.core.units import infer_units_from_geometry

logger = logging.getLogger("dupla.coordination.dwg_accore")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACCORECONSOLE = Path(r"C:\Program Files\Autodesk\AutoCAD 2027\accoreconsole.exe")
DEFAULT_EXTRACTOR_DLL = (
    REPO_ROOT / "aps_integration" / "DuplaExtractor" / "bin" / "Release" / "net10.0-windows" / "DuplaExtractor.dll"
)

ANNOTATION_TYPES = {
    "DBTEXT",
    "MTEXT",
    "MText",
    "Dimension",
    "Leader",
    "MLeader",
    "Point",
}
LINEAR_BUFFER_MM = 25.0
PROFILE_CLUSTER_CELL_MM = 500_000.0
PROFILE_CLUSTER_MAX_SPAN_MM = 10_000_000.0


@dataclass(frozen=True)
class AccorePayloadResult:
    payload: dict[str, Any] | None
    cache_hit: bool


def extractor_available(
    *,
    accoreconsole_path: Path | None = None,
    extractor_dll: Path | None = None,
) -> bool:
    return (accoreconsole_path or DEFAULT_ACCORECONSOLE).is_file() and (
        extractor_dll or DEFAULT_EXTRACTOR_DLL
    ).is_file()


def extract_elements_from_dwg_via_accore(
    path: Path,
    discipline: Discipline,
    *,
    level_id: str,
    translation_mm: tuple[float, float] = (0.0, 0.0),
    min_area_mm2: float = 50_000.0,
    max_entities: int = 400,
    z_thickness_mm: float = 250.0,
    z_ref_mm: float | None = None,
    cache_root: Path | None = None,
    accoreconsole_path: Path | None = None,
    extractor_dll: Path | None = None,
    timeout_seconds: int = 240,
) -> list[Element25D]:
    payload_result = load_accore_payload_via_accore(
        path,
        cache_root=cache_root,
        accoreconsole_path=accoreconsole_path,
        extractor_dll=extractor_dll,
        timeout_seconds=timeout_seconds,
    )
    if not payload_result.payload:
        return []

    return extract_elements_from_accore_payload(
        payload_result.payload,
        path=path,
        discipline=discipline,
        level_id=level_id,
        translation_mm=translation_mm,
        min_area_mm2=min_area_mm2,
        max_entities=max_entities,
        z_thickness_mm=z_thickness_mm,
        z_ref_mm=z_ref_mm,
    )


def profile_dwg_via_accore(
    path: Path,
    *,
    cache_root: Path | None = None,
    accoreconsole_path: Path | None = None,
    extractor_dll: Path | None = None,
    timeout_seconds: int = 240,
) -> dict[str, Any] | None:
    payload_result = load_accore_payload_via_accore(
        path,
        cache_root=cache_root,
        accoreconsole_path=accoreconsole_path,
        extractor_dll=extractor_dll,
        timeout_seconds=timeout_seconds,
    )
    if not payload_result.payload:
        return None
    return profile_accore_payload(payload_result.payload)


def load_accore_payload_via_accore(
    path: Path,
    *,
    cache_root: Path | None,
    accoreconsole_path: Path | None,
    extractor_dll: Path | None,
    timeout_seconds: int,
) -> AccorePayloadResult:
    accoreconsole = (accoreconsole_path or DEFAULT_ACCORECONSOLE).resolve()
    source_dll = (extractor_dll or DEFAULT_EXTRACTOR_DLL).resolve()
    if not accoreconsole.is_file() or not source_dll.is_file():
        return AccorePayloadResult(payload=None, cache_hit=False)

    root = (cache_root or (REPO_ROOT / "analysis_output" / "accore_cache")).resolve()
    run_dir = root / _safe_stem(path.stem)
    isolate_dir = run_dir / "isolate"
    run_dir.mkdir(parents=True, exist_ok=True)
    isolate_dir.mkdir(parents=True, exist_ok=True)
    output_json = run_dir / "resultados.json"
    script_path = run_dir / "extract.scr"
    stdout_log = run_dir / "accore.stdout.log"
    stderr_log = run_dir / "accore.stderr.log"

    cache_hit = _use_cached_output(output_json, source=path, extractor_dll=source_dll)
    if not cache_hit:
        output_json.unlink(missing_ok=True)
        stdout_log.unlink(missing_ok=True)
        stderr_log.unlink(missing_ok=True)
        script_path.write_text(
            "\n".join(
                [
                    "SECURELOAD",
                    "0",
                    "FILEDIA",
                    "0",
                    "NETLOAD",
                    _short_path(source_dll),
                    "ExtractDuplaData",
                    "QUIT",
                    "Y",
                    "",
                ]
            ),
            encoding="ascii",
        )
        cmd = [
            _short_path(accoreconsole),
            "/isolate",
            "dupla_coordination",
            _short_path(isolate_dir),
            "/i",
            _short_path(path),
            "/s",
            _short_path(script_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd=run_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=timeout_seconds,
                check=False,
            )
        except Exception as exc:
            logger.warning("accoreconsole fallo con %s: %s", path.name, exc)
            return AccorePayloadResult(payload=None, cache_hit=False)
        stdout_log.write_text(result.stdout or "", encoding="utf-8", errors="ignore")
        stderr_log.write_text(result.stderr or "", encoding="utf-8", errors="ignore")
        if result.returncode != 0:
            logger.warning("accoreconsole retorno %s para %s", result.returncode, path.name)
        if not output_json.is_file():
            logger.warning(
                "accoreconsole no produjo resultados.json para %s. stdout=%s stderr=%s",
                path.name,
                _tail_text(result.stdout),
                _tail_text(result.stderr),
            )
            return AccorePayloadResult(payload=None, cache_hit=False)

    try:
        return AccorePayloadResult(
            payload=json.loads(output_json.read_text(encoding="utf-8")),
            cache_hit=cache_hit,
        )
    except Exception as exc:
        logger.warning("No se pudo leer %s: %s", output_json, exc)
        return AccorePayloadResult(payload=None, cache_hit=False)


def _resolve_payload_units_to_mm(payload: dict[str, Any]) -> dict[str, Any]:
    declared_factor_mm = float(payload.get("UnitsToMmFactor") or 1.0)
    geometry_rows = _geometry_rows_from_payload(payload)
    if not geometry_rows:
        return {
            "factor_mm": declared_factor_mm,
            "source": "declared_units_no_geometry_outline",
            "declared_factor_mm": declared_factor_mm,
            "inferred_factor_mm": None,
            "warning": None,
        }
    inferred = infer_units_from_geometry(geometry_rows)
    inferred_factor_mm = inferred.factor_to_meters * 1000.0
    denom = max(abs(declared_factor_mm), abs(inferred_factor_mm), 1e-12)
    disagrees = abs(declared_factor_mm - inferred_factor_mm) / denom > 0.05
    if not disagrees:
        return {
            "factor_mm": declared_factor_mm,
            "source": "declared_units_agree_with_geometry",
            "declared_factor_mm": declared_factor_mm,
            "inferred_factor_mm": inferred_factor_mm,
            "inferred_unit": inferred.unit_label,
            "outline_before": inferred.outline_before,
            "outline_after_m": inferred.outline_after,
            "warning": None,
        }
    warning = {
        "declared_factor_mm": declared_factor_mm,
        "inferred_factor_mm": inferred_factor_mm,
        "inferred_unit": inferred.unit_label,
        "outline_before": inferred.outline_before,
        "outline_after_m": inferred.outline_after,
        "decision": "trusted_geometry_over_declared_units",
    }
    logger.warning(
        "ACCORE unit mismatch: declared %.6g mm/unit, geometry inferred %.6g mm/unit (%s). Using geometry.",
        declared_factor_mm,
        inferred_factor_mm,
        inferred.unit_label,
    )
    return {
        "factor_mm": inferred_factor_mm,
        "source": "geometry_over_declared_units",
        "declared_factor_mm": declared_factor_mm,
        "inferred_factor_mm": inferred_factor_mm,
        "inferred_unit": inferred.unit_label,
        "outline_before": inferred.outline_before,
        "outline_after_m": inferred.outline_after,
        "warning": warning,
    }


def _geometry_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entity in payload.get("Entities") or []:
        if not isinstance(entity, dict):
            continue
        bounds = entity.get("Bounds")
        if not isinstance(bounds, dict):
            continue
        min_pt = bounds.get("Min") or {}
        max_pt = bounds.get("Max") or {}
        try:
            x0 = float(min_pt.get("X") or 0.0)
            y0 = float(min_pt.get("Y") or 0.0)
            x1 = float(max_pt.get("X") or 0.0)
            y1 = float(max_pt.get("Y") or 0.0)
        except Exception:
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        rows.append(
            {
                "model_bounds": [x0, y0, x1, y1],
                "model_center": [(x0 + x1) / 2.0, (y0 + y1) / 2.0],
            }
        )
    return rows


def profile_accore_payload(payload: dict[str, Any]) -> dict[str, Any]:
    unit_resolution = _resolve_payload_units_to_mm(payload)
    factor_mm = unit_resolution["factor_mm"]
    entities = payload.get("Entities") or []
    raw_entity_count = 0
    raw_annotation_count = 0
    raw_primary_candidate_count = 0
    raw_bbox_only_count = 0
    type_counts: dict[str, int] = {}
    layer_counts: dict[str, int] = {}
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")
    have_bounds = False
    cluster_counts: dict[tuple[int, int], int] = {}
    cluster_area_like: dict[tuple[int, int], float] = {}
    cluster_bounds: dict[tuple[int, int], list[float]] = {}

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        raw_entity_count += 1
        entity_type = str(entity.get("Type") or "")
        layer = str(entity.get("Layer") or "0")
        type_counts[entity_type] = type_counts.get(entity_type, 0) + 1
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
        if entity_type in ANNOTATION_TYPES or any(token in layer.lower() for token in NON_GEOMETRIC_LAYER_TOKENS):
            raw_annotation_count += 1
        if entity_type in {"Polyline", "Polyline2d", "Polyline3d", "Circle", "Arc", "Line"}:
            raw_primary_candidate_count += 1
        elif entity_type == "BlockReference" or entity.get("Bounds"):
            raw_bbox_only_count += 1

        bounds = entity.get("Bounds")
        if not isinstance(bounds, dict):
            continue
        min_pt = bounds.get("Min") or {}
        max_pt = bounds.get("Max") or {}
        try:
            bx0 = float(min_pt.get("X") or 0.0) * factor_mm
            by0 = float(min_pt.get("Y") or 0.0) * factor_mm
            bz0 = float(min_pt.get("Z") or 0.0) * factor_mm
            bx1 = float(max_pt.get("X") or 0.0) * factor_mm
            by1 = float(max_pt.get("Y") or 0.0) * factor_mm
            bz1 = float(max_pt.get("Z") or 0.0) * factor_mm
        except Exception:
            continue
        min_x = min(min_x, bx0)
        min_y = min(min_y, by0)
        min_z = min(min_z, bz0)
        max_x = max(max_x, bx1)
        max_y = max(max_y, by1)
        max_z = max(max_z, bz1)
        have_bounds = True

        if entity_type not in {"Polyline", "Polyline2d", "Polyline3d", "Circle", "Arc", "Line"}:
            continue
        span_x = abs(bx1 - bx0)
        span_y = abs(by1 - by0)
        if span_x > PROFILE_CLUSTER_MAX_SPAN_MM or span_y > PROFILE_CLUSTER_MAX_SPAN_MM:
            continue
        centroid_x = (bx0 + bx1) / 2.0
        centroid_y = (by0 + by1) / 2.0
        key = (
            int(math.floor(centroid_x / PROFILE_CLUSTER_CELL_MM)),
            int(math.floor(centroid_y / PROFILE_CLUSTER_CELL_MM)),
        )
        cluster_counts[key] = cluster_counts.get(key, 0) + 1
        cluster_area_like[key] = cluster_area_like.get(key, 0.0) + max(span_x * span_y, max(span_x, span_y, 1.0))
        bounds = cluster_bounds.setdefault(
            key,
            [float("inf"), float("inf"), float("-inf"), float("-inf"), float("inf"), float("-inf")],
        )
        bounds[0] = min(bounds[0], bx0)
        bounds[1] = min(bounds[1], by0)
        bounds[2] = max(bounds[2], bx1)
        bounds[3] = max(bounds[3], by1)
        bounds[4] = min(bounds[4], bz0)
        bounds[5] = max(bounds[5], bz1)

    bounds_mm = None
    centroid_mm = None
    if have_bounds:
        bounds_mm = (min_x, min_y, max_x, max_y, min_z, max_z)
        centroid_mm = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, (min_z + max_z) / 2.0)

    dominant_entity_types = [
        entity_type
        for entity_type, _count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]
    raw_layers_detected = [
        layer for layer, _ in sorted(layer_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:50]
    ]
    dominant_cluster_key = None
    dominant_cluster_bounds = None
    dominant_cluster_centroid = None
    dominant_cluster_entity_count = 0
    if cluster_counts:
        dominant_cluster_key = max(
            cluster_counts,
            key=lambda key: (cluster_counts[key], cluster_area_like.get(key, 0.0), key[0], key[1]),
        )
        dominant_cluster_entity_count = cluster_counts[dominant_cluster_key]
        raw_cluster_bounds = cluster_bounds[dominant_cluster_key]
        dominant_cluster_bounds = tuple(float(value) for value in raw_cluster_bounds)
        dominant_cluster_centroid = (
            (dominant_cluster_bounds[0] + dominant_cluster_bounds[2]) / 2.0,
            (dominant_cluster_bounds[1] + dominant_cluster_bounds[3]) / 2.0,
            (dominant_cluster_bounds[4] + dominant_cluster_bounds[5]) / 2.0,
        )
    return {
        "units_to_mm_factor": factor_mm,
        "unit_resolution": unit_resolution,
        "raw_entity_count": raw_entity_count,
        "raw_annotation_count": raw_annotation_count,
        "raw_primary_candidate_count": raw_primary_candidate_count,
        "raw_bbox_only_count": raw_bbox_only_count,
        "bounds_mm": bounds_mm,
        "centroid_mm": centroid_mm,
        "dominant_cluster_key": dominant_cluster_key,
        "dominant_cluster_entity_count": dominant_cluster_entity_count,
        "dominant_cluster_bounds_mm": dominant_cluster_bounds,
        "dominant_cluster_centroid_mm": dominant_cluster_centroid,
        "dominant_entity_types": dominant_entity_types,
        "raw_layers_detected": raw_layers_detected,
    }


def _use_cached_output(output_json: Path, *, source: Path, extractor_dll: Path) -> bool:
    if not output_json.is_file():
        return False
    output_mtime = output_json.stat().st_mtime
    if output_mtime < source.stat().st_mtime:
        return False
    for item in extractor_dll.parent.iterdir():
        if item.is_file() and output_mtime < item.stat().st_mtime:
            return False
    return True


def extract_elements_from_accore_payload(
    payload: dict[str, Any],
    *,
    path: Path,
    discipline: Discipline,
    level_id: str,
    translation_mm: tuple[float, float],
    min_area_mm2: float,
    max_entities: int,
    z_thickness_mm: float,
    z_ref_mm: float | None,
) -> list[Element25D]:
    unit_resolution = _resolve_payload_units_to_mm(payload)
    factor_mm = unit_resolution["factor_mm"]
    z0 = 0.0 if z_ref_mm is None else float(z_ref_mm)
    entities = payload.get("Entities") or []
    candidates: list[tuple[float, Element25D]] = []

    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        entity_type = str(entity.get("Type") or "")
        layer = str(entity.get("Layer") or "0")
        if entity_type in ANNOTATION_TYPES:
            continue
        if any(token in layer.lower() for token in NON_GEOMETRIC_LAYER_TOKENS):
            continue

        footprint = _footprint_from_entity(entity, factor_mm=factor_mm, translation_mm=translation_mm)
        if not footprint or len(footprint) < 3:
            continue

        polygon = Polygon(footprint + [footprint[0]])
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        area = float(polygon.area)
        if polygon.is_empty or area < min_area_mm2:
            continue

        geometry_source = str(entity.get("_geometry_source") or "dwg_accore_bbox")
        geometry_quality = str(entity.get("_geometry_quality") or "medium")
        geometry_role = str(entity.get("_geometry_role") or "primary")
        suppression_reason = entity.get("_suppression_reason")
        bounds = entity.get("Bounds") or {}
        min_pt = (bounds.get("Min") or {}) if isinstance(bounds, dict) else {}
        max_pt = (bounds.get("Max") or {}) if isinstance(bounds, dict) else {}
        min_z = float(min_pt.get("Z") or 0.0) * factor_mm + z0
        max_z = float(max_pt.get("Z") or min_pt.get("Z") or 0.0) * factor_mm + z0
        thickness = max(max_z - min_z, 0.0)
        if thickness < 1.0:
            thickness = z_thickness_mm

        handle = str(entity.get("Handle") or index)
        block_name = str(entity.get("Name") or entity.get("BlockName") or "").strip() or None
        bbox_mm = _bounds_bbox_mm(bounds, factor_mm=factor_mm, translation_mm=translation_mm)
        centroid_mm = _centroid_from_footprint(footprint)
        candidates.append(
            (
                area,
                Element25D(
                    id=f"dwgaccore_{path.stem}_{index}_{handle}",
                    source_ref=f"{path.as_posix()}|{layer}|{entity_type}|{handle}",
                    discipline=discipline,
                    category=f"{entity_type}:{layer}",
                    footprint_coords_mm=footprint,
                    z_data=ZInterval(
                        level_id=level_id,
                        z_ref_raw_mm=min_z,
                        thickness_mm=thickness,
                        reference_point="bottom",
                    ),
                    metadata={
                        "file": path.name,
                        "source_file": path.as_posix(),
                        "layer": layer,
                        "handle": handle,
                        "cad_handle": handle,
                        "entity_type": entity_type,
                        "block_name": block_name,
                        "area_mm2": area,
                        "source": "cad_accore",
                        "unit_resolution": unit_resolution,
                        "geometry_source": geometry_source,
                        "geometry_quality": geometry_quality,
                        "geometry_confidence": _geometry_confidence_label(geometry_quality),
                        "geometry_role": geometry_role,
                        "suppression_reason": suppression_reason,
                        "sheet_or_view_name": path.stem,
                        "bbox_mm": bbox_mm,
                        "centroid_mm": centroid_mm,
                        "level_id": level_id,
                        "discipline": discipline.value,
                    },
                ),
            )
        )

    candidates.sort(key=lambda item: -item[0])
    return [element for _, element in candidates[:max_entities]]


def _footprint_from_entity(
    entity: dict[str, Any],
    *,
    factor_mm: float,
    translation_mm: tuple[float, float],
) -> list[tuple[float, float]] | None:
    entity_type = str(entity.get("Type") or "")

    if entity_type in {"Polyline", "Polyline2d", "Polyline3d"}:
        vertices = entity.get("Vertices") or []
        closed = bool(entity.get("Closed"))
        if closed:
            footprint = _polygon_from_vertices(vertices, factor_mm=factor_mm)
            if footprint:
                entity["_geometry_source"] = "dwg_accore_polyline"
                entity["_geometry_quality"] = "high"
                entity["_geometry_role"] = "primary"
                return translate_footprint(footprint, translation_mm[0], translation_mm[1])
        footprint = _buffered_line_from_vertices(vertices, factor_mm=factor_mm, width_mm=LINEAR_BUFFER_MM)
        if footprint:
            entity["_geometry_source"] = "dwg_accore_line"
            entity["_geometry_quality"] = "high"
            entity["_geometry_role"] = "primary"
            return translate_footprint(footprint, translation_mm[0], translation_mm[1])

    if entity_type == "Circle":
        center = entity.get("Center") or {}
        radius = float(entity.get("Radius") or 0.0) * factor_mm
        if radius > 0.0:
            cx = float(center.get("X") or 0.0) * factor_mm
            cy = float(center.get("Y") or 0.0) * factor_mm
            footprint = [
                (
                    cx + radius * math.cos(2.0 * math.pi * step / 24.0),
                    cy + radius * math.sin(2.0 * math.pi * step / 24.0),
                )
                for step in range(24)
            ]
            entity["_geometry_source"] = "dwg_accore_circle"
            entity["_geometry_quality"] = "high"
            entity["_geometry_role"] = "primary"
            return translate_footprint(footprint, translation_mm[0], translation_mm[1])

    if entity_type == "Arc":
        center = entity.get("Center") or {}
        radius = float(entity.get("Radius") or 0.0) * factor_mm
        start = float(entity.get("StartAngle") or 0.0)
        end = float(entity.get("EndAngle") or 0.0)
        footprint = _buffered_arc(
            center_x=float(center.get("X") or 0.0) * factor_mm,
            center_y=float(center.get("Y") or 0.0) * factor_mm,
            radius=radius,
            start_angle=start,
            end_angle=end,
            width_mm=LINEAR_BUFFER_MM,
        )
        if footprint:
            entity["_geometry_source"] = "dwg_accore_arc"
            entity["_geometry_quality"] = "high"
            entity["_geometry_role"] = "primary"
            return translate_footprint(footprint, translation_mm[0], translation_mm[1])

    if entity_type == "Line":
        start_point = entity.get("StartPoint") or {}
        end_point = entity.get("EndPoint") or {}
        footprint = _buffered_line(
            (
                float(start_point.get("X") or 0.0) * factor_mm,
                float(start_point.get("Y") or 0.0) * factor_mm,
            ),
            (
                float(end_point.get("X") or 0.0) * factor_mm,
                float(end_point.get("Y") or 0.0) * factor_mm,
            ),
            width_mm=LINEAR_BUFFER_MM,
        )
        if footprint:
            entity["_geometry_source"] = "dwg_accore_line"
            entity["_geometry_quality"] = "high"
            entity["_geometry_role"] = "primary"
            return translate_footprint(footprint, translation_mm[0], translation_mm[1])

    if entity_type == "BlockReference" or entity.get("Bounds"):
        footprint = _bbox_from_bounds(entity.get("Bounds"), factor_mm=factor_mm)
        if footprint:
            entity["_geometry_source"] = "dwg_accore_bbox"
            entity["_geometry_quality"] = "medium"
            entity["_geometry_role"] = "suppressed"
            entity["_suppression_reason"] = (
                "container_bbox" if entity_type == "BlockReference" else "bounds_fallback"
            )
            return translate_footprint(footprint, translation_mm[0], translation_mm[1])

    return None


def _polygon_from_vertices(vertices: list[Any], *, factor_mm: float) -> list[tuple[float, float]] | None:
    points: list[tuple[float, float]] = []
    for vertex in vertices:
        if not isinstance(vertex, dict):
            continue
        points.append((float(vertex.get("X") or 0.0) * factor_mm, float(vertex.get("Y") or 0.0) * factor_mm))
    if len(points) < 3:
        return None
    if points[0] == points[-1]:
        points = points[:-1]
    if len(points) < 3:
        return None
    polygon = Polygon(points + [points[0]])
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.geom_type == "MultiPolygon":
        polygon = max(polygon.geoms, key=lambda item: item.area, default=polygon)
    if polygon.is_empty or polygon.area <= 0.0:
        return None
    return [(float(x), float(y)) for x, y in polygon.exterior.coords[:-1]]


def _bbox_from_bounds(bounds: Any, *, factor_mm: float) -> list[tuple[float, float]] | None:
    if not isinstance(bounds, dict):
        return None
    min_pt = bounds.get("Min") or {}
    max_pt = bounds.get("Max") or {}
    min_x = float(min_pt.get("X") or 0.0) * factor_mm
    min_y = float(min_pt.get("Y") or 0.0) * factor_mm
    max_x = float(max_pt.get("X") or 0.0) * factor_mm
    max_y = float(max_pt.get("Y") or 0.0) * factor_mm
    if max_x <= min_x or max_y <= min_y:
        return None
    return [
        (min_x, min_y),
        (max_x, min_y),
        (max_x, max_y),
        (min_x, max_y),
    ]


def _bounds_bbox_mm(
    bounds: Any,
    *,
    factor_mm: float,
    translation_mm: tuple[float, float] = (0.0, 0.0),
) -> tuple[float, float, float, float] | None:
    if not isinstance(bounds, dict):
        return None
    min_pt = bounds.get("Min") or {}
    max_pt = bounds.get("Max") or {}
    min_x = float(min_pt.get("X") or 0.0) * factor_mm
    min_y = float(min_pt.get("Y") or 0.0) * factor_mm
    max_x = float(max_pt.get("X") or 0.0) * factor_mm
    max_y = float(max_pt.get("Y") or 0.0) * factor_mm
    if max_x <= min_x or max_y <= min_y:
        return None
    dx, dy = translation_mm
    return (min_x + dx, min_y + dy, max_x + dx, max_y + dy)


def _centroid_from_footprint(footprint: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not footprint:
        return None
    polygon = Polygon(footprint + [footprint[0]])
    if polygon.is_empty:
        return None
    centroid = polygon.centroid
    return (float(centroid.x), float(centroid.y))


def _geometry_confidence_label(geometry_quality: str) -> str:
    label = str(geometry_quality or "medium").lower()
    if label in {"high", "exact"}:
        return "high"
    if label in {"medium", "proxy"}:
        return "medium"
    return "low"


def _buffered_line_from_vertices(
    vertices: list[Any],
    *,
    factor_mm: float,
    width_mm: float,
) -> list[tuple[float, float]] | None:
    points: list[tuple[float, float]] = []
    for vertex in vertices:
        if not isinstance(vertex, dict):
            continue
        points.append((float(vertex.get("X") or 0.0) * factor_mm, float(vertex.get("Y") or 0.0) * factor_mm))
    if len(points) < 2:
        return None
    return _buffered_linestring(points, width_mm=width_mm)


def _buffered_line(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    width_mm: float,
) -> list[tuple[float, float]] | None:
    if start == end:
        return None
    return _buffered_linestring([start, end], width_mm=width_mm)


def _buffered_arc(
    *,
    center_x: float,
    center_y: float,
    radius: float,
    start_angle: float,
    end_angle: float,
    width_mm: float,
) -> list[tuple[float, float]] | None:
    if radius <= 0.0:
        return None
    end = end_angle
    if end <= start_angle:
        end += 2.0 * math.pi
    steps = max(8, int(abs(end - start_angle) / (math.pi / 18.0)))
    points = [
        (
            center_x + radius * math.cos(start_angle + (end - start_angle) * step / steps),
            center_y + radius * math.sin(start_angle + (end - start_angle) * step / steps),
        )
        for step in range(steps + 1)
    ]
    return _buffered_linestring(points, width_mm=width_mm)


def _buffered_linestring(
    points: list[tuple[float, float]],
    *,
    width_mm: float,
) -> list[tuple[float, float]] | None:
    line = LineString(points)
    if line.is_empty or line.length <= 0.0:
        return None
    polygon = line.buffer(width_mm, cap_style=2, join_style=2)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.geom_type == "MultiPolygon":
        polygon = max(polygon.geoms, key=lambda item: item.area, default=polygon)
    if polygon.is_empty or polygon.area <= 0.0:
        return None
    return [(float(x), float(y)) for x, y in polygon.exterior.coords[:-1]]


def _safe_stem(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value)
    return cleaned[:80] or "dwg"


def _short_path(path: Path) -> str:
    raw = str(path.resolve())
    size = windll.kernel32.GetShortPathNameW(raw, None, 0)
    if size <= 0:
        return raw
    buffer = create_unicode_buffer(size)
    result = windll.kernel32.GetShortPathNameW(raw, buffer, size)
    return buffer.value if result > 0 else raw


def _tail_text(value: str | None, *, max_chars: int = 400) -> str:
    text = (value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]
