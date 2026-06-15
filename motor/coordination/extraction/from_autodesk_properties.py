"""
Extrae candidatos 2.5D desde la exportación de propiedades APS (viewer 2D).

Limitación: el JSON de propiedades suele traer área y elevación pero **no** vértices XY.
La huella se aproxima como **polígono cuadrado equivalente** (misma área) centrado en el
origen del dibujo, solo para **prototipos** o smoke tests hasta exista geometría completa
(DXF local, IFC o visión con polígonos).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coordination.core.models_25d import Discipline, Element25D, ZInterval
from coordination.core.units import to_mm


@dataclass(frozen=True)
class AutodeskEntityPick:
    external_id: str
    object_name: str
    layer: str
    entity_type: str
    area_m2: float
    elevation_m: float


def _parse_float_field(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", ".")
    s = re.sub(r"\s*m\s*$", "", s, flags=re.I)
    try:
        return float(s)
    except ValueError:
        return None


def _classify_layer(layer: str) -> str | None:
    u = layer.upper()
    if u.startswith("EL") and len(u) <= 4 and u[2:].isdigit():
        return "mep"
    if any(x in u for x in ("SANIT", "PLUMB", "MECH", "HVAC", "FIRE", "SPRINK")):
        return "mep"
    if any(
        x in u
        for x in (
            "A-WALL",
            "S-STRS",
            "STRUCT",
            "SE-2",
            "SE-3",
            "SE-4",
            "SE-2-MADERA",
            "SE-3-MADERA",
            "MURO",
            "MUROS",
            "COLUMN",
        )
    ):
        return "struct"
    return None


def _is_closed_polyline(props: dict[str, Any]) -> bool:
    misc = props.get("Misc") or {}
    return str(misc.get("Closed", "")).lower() == "yes"


def pick_best_entities(
    autodesk_raw: dict[str, Any],
    *,
    min_area_m2: float = 1.0,
) -> tuple[AutodeskEntityPick | None, AutodeskEntityPick | None]:
    """Elige la entidad de mayor área por disciplina (polilínea cerrada o hatch)."""
    views = autodesk_raw.get("views") or []
    if not views:
        return None, None
    objs = views[0].get("objects") or []
    best: dict[str, tuple[float, AutodeskEntityPick]] = {}
    for o in objs:
        props = o.get("properties")
        if not isinstance(props, dict):
            continue
        general = props.get("General") or {}
        layer = str(general.get("Layer") or "")
        disc = _classify_layer(layer)
        if not disc:
            continue
        et = str(general.get("Name ") or "").strip()
        geo = props.get("Geometry") or {}
        area = _parse_float_field(geo.get("Area"))
        if area is None or area < min_area_m2:
            continue
        if et == "Polyline" and not _is_closed_polyline(props):
            continue
        if et not in ("Polyline", "Hatch", "Circle"):
            continue
        elev = _parse_float_field(geo.get("Elevation")) or 0.0
        ext = str(o.get("externalId") or "")
        name = str(o.get("name") or ext)
        pick = AutodeskEntityPick(
            external_id=ext,
            object_name=name,
            layer=layer,
            entity_type=et,
            area_m2=area,
            elevation_m=elev,
        )
        cur = best.get(disc)
        if cur is None or area > cur[0]:
            best[disc] = (area, pick)
    m = best.get("mep")
    s = best.get("struct")
    return (s[1] if s else None, m[1] if m else None)


def square_footprint_mm(area_m2: float) -> list[tuple[float, float]]:
    """Cuadrado centrado en (0,0) con la misma área que el cierre original."""
    side = math.sqrt(max(area_m2, 1e-9)) * 1000.0
    h = side / 2.0
    return [(-h, -h), (h, -h), (h, h), (-h, h)]


def picks_to_elements(
    struct: AutodeskEntityPick | None,
    mep: AutodeskEntityPick | None,
    *,
    level_id: str,
    z_struct_mm: tuple[float, float] | None = None,
    z_mep_mm: tuple[float, float] | None = None,
) -> list[Element25D]:
    """
    Convierte picks en Element25D.

    z_* son (z_ref_raw_mm, thickness_mm) cuando la elevación APS es de planta (0).
    """
    out: list[Element25D] = []
    z_s = z_struct_mm or (2650.0, 600.0)
    z_m = z_mep_mm or (2750.0, 350.0)

    if struct:
        zr, th = z_s
        if abs(struct.elevation_m) > 1e-6:
            zr = to_mm(struct.elevation_m, "m")
            th = max(200.0, min(800.0, math.sqrt(struct.area_m2) * 50))
        out.append(
            Element25D(
                id=f"nasas_struct_{struct.external_id}",
                source_ref=f"autodesk_raw:{struct.object_name}",
                discipline=Discipline.STRUC,
                category=f"{struct.entity_type}:{struct.layer}",
                footprint_coords_mm=square_footprint_mm(struct.area_m2),
                z_data=ZInterval(
                    level_id=level_id,
                    z_ref_raw_mm=zr,
                    thickness_mm=th,
                    reference_point="bottom",
                ),
                metadata={
                    "nasas_layer": struct.layer,
                    "footprint_model": "square_equivalent_centered_origin",
                    "area_m2": struct.area_m2,
                },
            )
        )
    if mep:
        zr, th = z_m
        if abs(mep.elevation_m) > 1e-6:
            zr = to_mm(mep.elevation_m, "m")
            th = max(150.0, min(600.0, math.sqrt(mep.area_m2) * 40))
        out.append(
            Element25D(
                id=f"nasas_mep_{mep.external_id}",
                source_ref=f"autodesk_raw:{mep.object_name}",
                discipline=Discipline.MEP_ELEC,
                category=f"{mep.entity_type}:{mep.layer}",
                footprint_coords_mm=square_footprint_mm(mep.area_m2),
                z_data=ZInterval(
                    level_id=level_id,
                    z_ref_raw_mm=zr,
                    thickness_mm=th,
                    reference_point="bottom",
                ),
                metadata={
                    "nasas_layer": mep.layer,
                    "footprint_model": "square_equivalent_centered_origin",
                    "area_m2": mep.area_m2,
                },
            )
        )
    return out


def load_autodesk_raw(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def discipline_from_autodesk_layer(layer: str) -> Discipline:
    """Disciplina Dupla a partir de nombre de capa APS."""
    u = layer.upper()
    if any(x in u for x in ("SANIT", "AGUA", "DRENAJE", "HIDRO", "FONTAN", "PLOMB")):
        return Discipline.MEP_PLUMBING
    if u.startswith("EL") or "ELEC" in u or "LIGHT" in u:
        return Discipline.MEP_ELEC
    if any(x in u for x in ("MECH", "HVAC", "CLIM", "DUCT", "AIRE")):
        return Discipline.MEP_HVAC
    c = _classify_layer(layer)
    if c == "struct":
        return Discipline.STRUC
    if c == "mep":
        return Discipline.MEP_ELEC
    return Discipline.ARCH


def _footprint_square_mm_at(area_m2: float, cx: float, cy: float, scale: float = 0.12) -> list[tuple[float, float]]:
    side = math.sqrt(max(area_m2, 1e-9)) * 1000.0 * scale
    h = side / 2.0
    return [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]


def bulk_elements_from_autodesk_raw(
    autodesk_raw: dict[str, Any],
    *,
    level_id: str,
    min_area_m2: float = 3.0,
    max_entities: int = 500,
    grid_n: int = 140,
    grid_step_mm: float = 5_000.0,
    z_thickness_mm: float = 280.0,
) -> list[Element25D]:
    """
    Muchas entidades APS sin vértices XY: cuadrado equivalente en una grilla determinista
    (reduce choques masivos en el origen). Solo para cruzar con otras fuentes o priorizar
    revisión por disciplina/capa.
    """
    import hashlib

    scored: list[tuple[float, str, str, str, float]] = []
    views = autodesk_raw.get("views") or []
    if not views:
        return []

    for view in views:
        objs = view.get("objects") or []
        for o in objs:
            props = o.get("properties")
            if not isinstance(props, dict):
                continue
            general = props.get("General") or {}
            layer = str(general.get("Layer") or "")
            et = str(general.get("Name ") or "").strip()
            geo = props.get("Geometry") or {}
            area = _parse_float_field(geo.get("Area"))
            if area is None or area < min_area_m2:
                continue
            if et == "Polyline" and not _is_closed_polyline(props):
                continue
            if et not in ("Polyline", "Hatch", "Circle"):
                continue
            ext = str(o.get("externalId") or "")
            elev = _parse_float_field(geo.get("Elevation")) or 0.0
            scored.append((area, ext, layer, et, elev))

    scored.sort(key=lambda x: -x[0])
    out: list[Element25D] = []
    for rank, (area, ext, layer, et, elev_m) in enumerate(scored[:max_entities]):
        disc = discipline_from_autodesk_layer(layer)
        h = int(hashlib.sha256(f"{ext}|{layer}".encode("utf-8")).hexdigest()[:12], 16)
        cx = (h % grid_n) * grid_step_mm
        cy = ((h // grid_n) % grid_n) * grid_step_mm
        zr = to_mm(elev_m, "m") if abs(elev_m) > 1e-9 else float(rank % 12) * 150.0
        fp = _footprint_square_mm_at(area, cx, cy, scale=0.1 + (rank % 5) * 0.02)
        out.append(
            Element25D(
                id=f"aps_bulk_{ext or rank}",
                source_ref=f"autodesk_raw:{et}:{layer}:{ext}",
                discipline=disc,
                category=f"bulk:{et}:{layer}",
                footprint_coords_mm=fp,
                z_data=ZInterval(
                    level_id=level_id,
                    z_ref_raw_mm=zr,
                    thickness_mm=z_thickness_mm,
                    reference_point="bottom",
                ),
                metadata={
                    "area_m2": area,
                    "footprint_model": "aps_grid_square",
                    "rank": rank,
                    "geometry_source": "autodesk_bulk",
                    "geometry_quality": "proxy",
                },
            )
        )
    return out
