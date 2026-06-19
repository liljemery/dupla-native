"""Extract 2D footprints from local DWG/DXF files using ezdxf."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import units
from shapely.geometry import Polygon

from coordination.core.models_25d import Discipline, Element25D, ZInterval
from coordination.core.nasas_paths import translate_footprint
from coordination.core.units import insunits_to_mm_factor

logger = logging.getLogger("dupla.coordination.dwg")


def _looks_like_binary_dwg(path: Path) -> bool:
    try:
        with open(path, "rb") as handle:
            head = handle.read(8)
    except OSError:
        return False
    return head.startswith(b"AC10") or head.startswith(b"AC1")


def _insunits_to_mm_factor(doc: Any) -> float:
    try:
        header = getattr(doc, "header", {})
        insunits = int(header.get("$INSUNITS", 0))
        measurement = int(header.get("$MEASUREMENT", 1))
        return insunits_to_mm_factor(insunits, measurement=measurement)
    except Exception:
        pass
    try:
        return float(units.conversion_factor(doc.units, units.MM))
    except Exception:
        return 1.0


def _polyline_footprint_mm(entity: Any, factor: float) -> list[tuple[float, float]] | None:
    try:
        pts = [(p[0] * factor, p[1] * factor) for p in entity.get_points("xy")]
    except Exception:
        return None
    if len(pts) < 3:
        return None
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or poly.area < 1.0:
        return None
    return [(float(x), float(y)) for x, y in poly.exterior.coords[:-1]]


def _circle_footprint_mm(entity: Any, factor: float) -> list[tuple[float, float]] | None:
    try:
        center = entity.dxf.center
        radius = float(entity.dxf.radius) * factor
        cx, cy = float(center.x) * factor, float(center.y) * factor
    except Exception:
        return None
    if radius < 1.0:
        return None
    steps = 24
    return [
        (cx + radius * math.cos(2 * math.pi * i / steps), cy + radius * math.sin(2 * math.pi * i / steps))
        for i in range(steps)
    ]


def extract_elements_from_dwg(
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
    cad_kind = path.suffix.lower().lstrip(".") or "cad"
    if path.suffix.lower() == ".dwg" and _looks_like_binary_dwg(path):
        logger.warning("Omitiendo DWG binario %s (ezdxf requiere DXF legible).", path.name)
        return []

    try:
        doc = ezdxf.readfile(str(path))
    except Exception:
        try:
            from ezdxf import recover

            doc, auditor = recover.readfile(str(path))
            if auditor.has_errors:
                logger.warning("DXF %s: auditor con errores o advertencias", path.name)
        except Exception as exc:
            logger.warning("No se pudo leer %s: %s", path, exc)
            return []

    factor = _insunits_to_mm_factor(doc)
    modelspace = doc.modelspace()
    candidates: list[tuple[float, Element25D]] = []
    z0 = 0.0 if z_ref_mm is None else float(z_ref_mm)

    idx = 0
    for entity in modelspace:
        dxftype = entity.dxftype()
        footprint: list[tuple[float, float]] | None = None
        if dxftype == "LWPOLYLINE" and entity.closed:
            footprint = _polyline_footprint_mm(entity, factor)
        elif dxftype == "POLYLINE":
            try:
                if entity.is_closed:
                    footprint = _polyline_footprint_mm(entity, factor)
            except Exception:
                pass
        elif dxftype == "CIRCLE":
            footprint = _circle_footprint_mm(entity, factor)

        if not footprint:
            continue
        footprint = translate_footprint(footprint, translation_mm[0], translation_mm[1])
        polygon = Polygon(footprint if footprint[0] == footprint[-1] else footprint + [footprint[0]])
        area = float(polygon.area)
        if area < min_area_mm2:
            continue

        layer = getattr(entity.dxf, "layer", "") or "0"
        elevation = z0
        try:
            elevation = float(getattr(entity.dxf, "elevation", 0.0)) * factor + z0
        except Exception:
            pass

        candidates.append(
            (
                area,
                Element25D(
                    id=f"dwg_{path.stem}_{idx}_{layer.replace('|', '_')}",
                    source_ref=f"{path.as_posix()}|{layer}|{dxftype}",
                    discipline=discipline,
                    category=f"{dxftype}:{layer}",
                    footprint_coords_mm=footprint,
                    z_data=ZInterval(
                        level_id=level_id,
                        z_ref_raw_mm=elevation,
                        thickness_mm=z_thickness_mm,
                        reference_point="bottom",
                    ),
                    metadata={
                        "file": path.name,
                        "layer": layer,
                        "area_mm2": area,
                        "source": "cad_ezdxf",
                        "geometry_source": f"{cad_kind}_ezdxf",
                        "geometry_quality": "high",
                        "level_assignment_source": "default_level",
                        "sheet_or_view_name": path.stem,
                    },
                ),
            )
        )
        idx += 1

    candidates.sort(key=lambda item: -item[0])
    return [element for _, element in candidates[:max_entities]]
