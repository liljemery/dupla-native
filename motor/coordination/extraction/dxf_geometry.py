"""Low-level DXF model-space geometry extraction.

This module is the production form of the fast ezdxf coverage POC: it emits one
record per DXF model-space entity with stable handles, tight XY bounds, and
enough provenance to later align model coordinates into APS sheet coordinates.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from coordination.extraction.ezdxf_font_setup import ensure_ezdxf_fallback_fonts

ensure_ezdxf_fallback_fonts()

import ezdxf
from ezdxf import bbox
from ezdxf.entities import DXFEntity, Insert
from ezdxf.math import Matrix44, Vec3

from coordination.core.models_25d import Discipline

logger = logging.getLogger("dupla.coordination.dxf_geometry")

DXF_EZDXF_GEOMETRY_SOURCE = "dxf_ezdxf"
MODEL_METERS_COORDINATE_UNIT = "model_meters"

PHYSICAL_GOOD_MAX_AXIS_M = 25.0
PHYSICAL_GOOD_MAX_AREA_M2 = 600.0
PHYSICAL_UNLOCALIZABLE_AXIS_RATIO = 0.95
PHYSICAL_UNLOCALIZABLE_AREA_RATIO = 0.85

ANNOTATION_LAYER_TOKENS = (
    "DEFPOINTS",
    "VIEWPORT",
    "TITLE",
    "BORDER",
    "FRAME",
    "GRID",
    "TEXT",
    "ANNO",
    "DIM",
    "LABEL",
    "LEGEND",
    "SIMBO",
    "NOTA",
    "TEXTO",
    "ESCALA",
    "NORTH",
    "NUMERO",
    "TITULOS",
    "MARCO",
    "CARTUCHO",
    "SELLO",
    "REV",
    "LEADER",
)

PHYSICAL_LAYER_TOKENS = (
    "WALL",
    "MURO",
    "DOOR",
    "PUERTA",
    "COL",
    "COLUMN",
    "VIGA",
    "BEAM",
    "PIPE",
    "DUCT",
    "ELEC",
    "LIGHT",
    "TOMA",
    "TABLERO",
    "SAN",
    "FONTAN",
    "COLUMNAS",
    "A-WALL",
    "A-DOOR",
    "S-WALL",
    "E-",
    "HS-",
    "CLIM",
    "HVAC",
    "CABLE",
    "LUM",
    "PANEL",
    "CONTACT",
    "SWITCH",
    "RECEPT",
)

NON_PHYSICAL_DXFTYPES = {
    "TEXT",
    "MTEXT",
    "DIMENSION",
    "LEADER",
    "MLEADER",
    "VIEWPORT",
    "ATTDEF",
    "ATTRIB",
    "SHAPE",
    "IMAGE",
    "WIPEOUT",
    "RAY",
    "XLINE",
}


BoundsXY = tuple[float, float, float, float]


@dataclass(frozen=True)
class DxfGeometryRecord:
    handle: str
    layer: str
    discipline: str
    dxftype: str
    source_ref: str
    model_bounds: BoundsXY
    model_center: tuple[float, float]
    geometry_source: str = DXF_EZDXF_GEOMETRY_SOURCE
    geometry_quality: str = "good"
    coordinate_unit: str = MODEL_METERS_COORDINATE_UNIT
    block_resolution_method: str | None = None
    is_physical: bool = True
    block_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "layer": self.layer,
            "discipline": self.discipline,
            "dxftype": self.dxftype,
            "source_ref": self.source_ref,
            "model_bounds": [float(v) for v in self.model_bounds],
            "model_center": [float(v) for v in self.model_center],
            "geometry_source": self.geometry_source,
            "geometry_quality": self.geometry_quality,
            "coordinate_unit": self.coordinate_unit,
            "block_resolution_method": self.block_resolution_method,
            "is_physical": self.is_physical,
            "block_name": self.block_name,
        }


@dataclass
class DxfGeometryStats:
    all_entities: int = 0
    all_bbox_ok: int = 0
    physical_entities: int = 0
    physical_bbox_ok: int = 0
    physical_good: int = 0
    physical_coarse: int = 0
    physical_unlocalizable: int = 0
    bbox_failed: int = 0
    by_dxftype: dict[str, dict[str, int]] = field(default_factory=dict)
    insert_stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_entities": self.all_entities,
            "all_bbox_ok": self.all_bbox_ok,
            "physical_entities": self.physical_entities,
            "physical_bbox_ok": self.physical_bbox_ok,
            "physical_good": self.physical_good,
            "physical_coarse": self.physical_coarse,
            "physical_unlocalizable": self.physical_unlocalizable,
            "bbox_failed": self.bbox_failed,
            "by_dxftype": self.by_dxftype,
            "insert_stats": self.insert_stats,
        }


@dataclass
class DxfGeometryExtraction:
    path: str
    discipline: str
    dxf_present: bool
    insunits: int | None = None
    coordinate_unit: str = MODEL_METERS_COORDINATE_UNIT
    ref_bounds: BoundsXY | None = None
    ref_bounds_source: str | None = None
    records: list[DxfGeometryRecord] = field(default_factory=list)
    stats: DxfGeometryStats = field(default_factory=DxfGeometryStats)
    timings: dict[str, float] = field(default_factory=dict)
    geometry_source: str = DXF_EZDXF_GEOMETRY_SOURCE
    recovered_partial: bool = False
    recovered_salvaged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "discipline": self.discipline,
            "dxf_present": self.dxf_present,
            "insunits": self.insunits,
            "coordinate_unit": self.coordinate_unit,
            "ref_bounds": [float(v) for v in self.ref_bounds] if self.ref_bounds else None,
            "ref_bounds_source": self.ref_bounds_source,
            "records": [record.to_dict() for record in self.records],
            "stats": self.stats.to_dict(),
            "timings": self.timings,
            "geometry_source": self.geometry_source,
            "recovered_partial": self.recovered_partial,
            "recovered_salvaged": self.recovered_salvaged,
        }


@dataclass
class _TypeStats:
    total: int = 0
    bbox_ok: int = 0
    bbox_failed: int = 0
    physical_total: int = 0
    physical_bbox_ok: int = 0
    physical_good: int = 0
    physical_coarse: int = 0
    physical_unlocalizable: int = 0


@dataclass
class _InsertStats:
    total: int = 0
    resolved: int = 0
    failed: int = 0
    block_bbox_resolved: int = 0
    virtual_resolved: int = 0
    virtual_fallback_attempts: int = 0
    virtual_fallback_capped: int = 0
    physical_total: int = 0
    physical_resolved: int = 0


def normalize_handle(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("0X"):
        text = text[2:]
    return text.lstrip("0") or "0"


def is_annotation_layer(layer: str) -> bool:
    upper = str(layer or "").upper()
    return any(token in upper for token in ANNOTATION_LAYER_TOKENS)


def is_physical_entity(layer: str, dxftype: str) -> bool:
    dxftype = str(dxftype or "").upper()
    layer = str(layer or "")
    if is_annotation_layer(layer):
        return False
    if dxftype in NON_PHYSICAL_DXFTYPES:
        return False
    upper = layer.upper()
    if any(token in upper for token in PHYSICAL_LAYER_TOKENS):
        return True
    return dxftype in {
        "INSERT",
        "LINE",
        "LWPOLYLINE",
        "POLYLINE",
        "CIRCLE",
        "ARC",
        "HATCH",
        "ELLIPSE",
        "SOLID",
        "3DFACE",
        "SPLINE",
    } and bool(layer.strip()) and layer != "0"


def _center(bounds: BoundsXY) -> tuple[float, float]:
    return ((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0)


def _valid_bounds(bounds: BoundsXY) -> BoundsXY | None:
    min_x, min_y, max_x, max_y = bounds
    if not all(math.isfinite(v) for v in bounds):
        return None
    if max_x < min_x:
        min_x, max_x = max_x, min_x
    if max_y < min_y:
        min_y, max_y = max_y, min_y
    if max_x <= min_x:
        max_x = min_x + 1e-9
    if max_y <= min_y:
        max_y = min_y + 1e-9
    return (min_x, min_y, max_x, max_y)


def _bounds_from_extents(ext: Any) -> BoundsXY | None:
    if not getattr(ext, "has_data", False):
        return None
    return _valid_bounds(
        (
            float(ext.extmin.x),
            float(ext.extmin.y),
            float(ext.extmax.x),
            float(ext.extmax.y),
        )
    )


def _union_bounds(bounds: Iterable[BoundsXY]) -> BoundsXY | None:
    rows = list(bounds)
    if not rows:
        return None
    return (
        min(row[0] for row in rows),
        min(row[1] for row in rows),
        max(row[2] for row in rows),
        max(row[3] for row in rows),
    )


def _transform_bounds(bounds: BoundsXY, matrix: Matrix44) -> BoundsXY:
    min_x, min_y, max_x, max_y = bounds
    points = [
        matrix.transform(Vec3(min_x, min_y, 0.0)),
        matrix.transform(Vec3(max_x, min_y, 0.0)),
        matrix.transform(Vec3(max_x, max_y, 0.0)),
        matrix.transform(Vec3(min_x, max_y, 0.0)),
    ]
    return (
        min(point.x for point in points),
        min(point.y for point in points),
        max(point.x for point in points),
        max(point.y for point in points),
    )


def _cheap_entity_bounds(entity: DXFEntity) -> BoundsXY | None:
    dxftype = entity.dxftype()
    try:
        if dxftype == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            return _valid_bounds((float(start.x), float(start.y), float(end.x), float(end.y)))
        if dxftype == "LWPOLYLINE":
            points = list(entity.get_points("xy"))
            if not points:
                return None
            xs = [float(point[0]) for point in points]
            ys = [float(point[1]) for point in points]
            return _valid_bounds((min(xs), min(ys), max(xs), max(ys)))
        if dxftype == "POLYLINE":
            points = [vertex.dxf.location for vertex in entity.vertices]
            if not points:
                return None
            xs = [float(point.x) for point in points]
            ys = [float(point.y) for point in points]
            return _valid_bounds((min(xs), min(ys), max(xs), max(ys)))
        if dxftype == "CIRCLE":
            center = entity.dxf.center
            radius = abs(float(entity.dxf.radius))
            return _valid_bounds((float(center.x) - radius, float(center.y) - radius, float(center.x) + radius, float(center.y) + radius))
        if dxftype == "ARC":
            center = entity.dxf.center
            radius = abs(float(entity.dxf.radius))
            return _valid_bounds((float(center.x) - radius, float(center.y) - radius, float(center.x) + radius, float(center.y) + radius))
        if dxftype in {"3DFACE", "SOLID"}:
            points = [entity.dxf.vtx0, entity.dxf.vtx1, entity.dxf.vtx2, entity.dxf.vtx3]
            xs = [float(point.x) for point in points]
            ys = [float(point.y) for point in points]
            return _valid_bounds((min(xs), min(ys), max(xs), max(ys)))
        if dxftype in {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}:
            point = entity.dxf.get("insert", None)
            if point is None:
                return None
            return _valid_bounds((float(point.x), float(point.y), float(point.x), float(point.y)))
        if dxftype == "DIMENSION":
            point = entity.dxf.get("defpoint", None)
            if point is None:
                return None
            return _valid_bounds((float(point.x), float(point.y), float(point.x), float(point.y)))
        if dxftype == "ELLIPSE":
            center = entity.dxf.center
            major = entity.dxf.major_axis
            ratio = abs(float(entity.dxf.ratio))
            major_len = math.hypot(float(major.x), float(major.y))
            radius = major_len * max(1.0, ratio)
            return _valid_bounds((float(center.x) - radius, float(center.y) - radius, float(center.x) + radius, float(center.y) + radius))
    except Exception:
        return None
    return None


def _insert_matrix(insert: Insert) -> Matrix44:
    if hasattr(insert, "matrix44"):
        return insert.matrix44()
    sx = float(insert.dxf.get("xscale", 1.0) or 1.0)
    sy = float(insert.dxf.get("yscale", 1.0) or 1.0)
    sz = float(insert.dxf.get("zscale", 1.0) or 1.0)
    rotation = math.radians(float(insert.dxf.get("rotation", 0.0) or 0.0))
    ins = insert.dxf.insert
    return Matrix44.chain(
        Matrix44.scale(sx, sy, sz),
        Matrix44.z_rotate(rotation),
        Matrix44.translate(float(ins.x), float(ins.y), float(ins.z)),
    )


class FastDxfBBoxResolver:
    def __init__(self, doc: ezdxf.document.Drawing, *, virtual_fallback_cap: int = 50) -> None:
        self.doc = doc
        self.cache = bbox.Cache()
        self.virtual_fallback_cap = virtual_fallback_cap
        self.block_cache: dict[str, BoundsXY | None] = {}
        self.block_cache_hits = 0
        self.block_cache_misses = 0
        self.virtual_attempts = 0
        self.virtual_resolved = 0
        self.virtual_capped = 0
        self._block_stack: set[str] = set()

    def block_local_bounds(self, block_name: str) -> BoundsXY | None:
        if block_name in self.block_cache:
            self.block_cache_hits += 1
            return self.block_cache[block_name]
        if block_name in self._block_stack:
            return None
        self.block_cache_misses += 1
        try:
            self._block_stack.add(block_name)
            block = self.doc.blocks.get(block_name)
            rows = []
            for entity in block:
                bounds, _method = self.entity_bounds(entity)
                if bounds is not None:
                    rows.append(bounds)
            bounds = _union_bounds(rows)
        except Exception:
            bounds = None
        finally:
            self._block_stack.discard(block_name)
        self.block_cache[block_name] = bounds
        return bounds

    def virtual_insert_bounds(self, insert: Insert) -> BoundsXY | None:
        if self.virtual_attempts >= self.virtual_fallback_cap:
            self.virtual_capped += 1
            return None
        self.virtual_attempts += 1
        rows: list[BoundsXY] = []
        try:
            for virtual in insert.virtual_entities():
                try:
                    bounds = _bounds_from_extents(bbox.extents([virtual], cache=self.cache))
                except Exception:
                    bounds = None
                if bounds is not None:
                    rows.append(bounds)
        except Exception:
            return None
        bounds = _union_bounds(rows)
        if bounds is not None:
            self.virtual_resolved += 1
        return bounds

    def entity_bounds(self, entity: DXFEntity) -> tuple[BoundsXY | None, str]:
        if entity.dxftype() == "INSERT":
            insert = entity
            block_name = str(insert.dxf.name)
            local = self.block_local_bounds(block_name)
            if local is not None:
                try:
                    return _transform_bounds(local, _insert_matrix(insert)), "insert_block_bbox"
                except Exception:
                    logger.debug("Failed to transform INSERT bounds for block %s", block_name, exc_info=True)
            fallback = self.virtual_insert_bounds(insert)
            if fallback is not None:
                return fallback, "insert_virtual_fallback"
            return None, "insert_failed"

        cheap = _cheap_entity_bounds(entity)
        if cheap is not None:
            return cheap, "direct_fast"
        try:
            return _bounds_from_extents(bbox.extents([entity], cache=self.cache)), "direct"
        except Exception:
            return None, "failed"


def drawing_reference_bounds(doc: ezdxf.document.Drawing) -> tuple[BoundsXY | None, str]:
    try:
        extmin = doc.header.get("$EXTMIN")
        extmax = doc.header.get("$EXTMAX")
        if extmin is not None and extmax is not None:
            bounds = _valid_bounds((float(extmin[0]), float(extmin[1]), float(extmax[0]), float(extmax[1])))
            if bounds is not None and max(abs(v) for v in bounds) < 1e12:
                return bounds, "header_extents"
    except Exception:
        pass
    return None, "entity_bbox_union"


def classify_model_geometry_quality(bounds: BoundsXY, reference_bounds: BoundsXY) -> str:
    ref_w = max(reference_bounds[2] - reference_bounds[0], 1e-9)
    ref_h = max(reference_bounds[3] - reference_bounds[1], 1e-9)
    ref_area = ref_w * ref_h
    w = max(bounds[2] - bounds[0], 0.0)
    h = max(bounds[3] - bounds[1], 0.0)
    area = w * h
    if (
        w / ref_w >= PHYSICAL_UNLOCALIZABLE_AXIS_RATIO
        or h / ref_h >= PHYSICAL_UNLOCALIZABLE_AXIS_RATIO
        or area / ref_area >= PHYSICAL_UNLOCALIZABLE_AREA_RATIO
    ):
        return "unlocalizable"
    if w <= PHYSICAL_GOOD_MAX_AXIS_M and h <= PHYSICAL_GOOD_MAX_AXIS_M and area <= PHYSICAL_GOOD_MAX_AREA_M2:
        return "good"
    return "coarse"


_PARSE_ERROR_LINE_RE = re.compile(r"at line (\d+)", re.I)


def _parse_error_line(exc: BaseException) -> int | None:
    match = _PARSE_ERROR_LINE_RE.search(str(exc))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _salvage_dxf_at_line(path: Path, error_line: int) -> Path | None:
    """Truncate DXF before a corrupt line and append EOF. ponytail: drops tail entities."""
    if error_line <= 2:
        return None
    salvaged = path.with_name(f"{path.stem}.salvaged{path.suffix}")
    try:
        with path.open("r", encoding="utf-8", errors="replace") as src, salvaged.open(
            "w",
            encoding="utf-8",
        ) as dst:
            for lineno, line in enumerate(src, start=1):
                if lineno >= error_line:
                    break
                dst.write(line)
            dst.write("0\nEOF\n")
    except OSError:
        return None
    return salvaged if salvaged.is_file() else None


def _read_dxf(path: Path, *, allow_salvage: bool = True) -> tuple[ezdxf.document.Drawing, bool, bool]:
    """Return (document, recovered_partial, salvaged)."""
    try:
        return ezdxf.readfile(str(path)), False, False
    except Exception as primary_exc:
        from ezdxf import recover

        try:
            doc, auditor = recover.readfile(str(path))
            if auditor.has_errors:
                logger.warning("DXF %s recovered with auditor errors", path.name)
            return doc, auditor.has_errors, False
        except Exception:
            pass

        try:
            doc, auditor = recover.readfile(str(path), errors="ignore")
            entity_count = len(list(doc.modelspace()))
            if entity_count > 0:
                logger.info(
                    "DXF %s partial recover: %d entities (primary: %s)",
                    path.name,
                    entity_count,
                    primary_exc,
                )
                return doc, True, False
        except Exception:
            pass

        if allow_salvage:
            error_line = _parse_error_line(primary_exc)
            if error_line is not None:
                salvaged = _salvage_dxf_at_line(path, error_line)
                if salvaged is not None:
                    try:
                        doc, auditor = recover.readfile(str(salvaged), errors="ignore")
                        entity_count = len(list(doc.modelspace()))
                        if entity_count > 0:
                            logger.info(
                                "DXF %s salvaged at line %d: %d entities",
                                path.name,
                                error_line,
                                entity_count,
                            )
                            return doc, True, True
                    except Exception:
                        pass
                    finally:
                        if salvaged.is_file():
                            try:
                                salvaged.unlink()
                            except OSError:
                                pass

        raise primary_exc


def probe_dxf_readable(path: Path) -> bool:
    """True when ezdxf can open the DXF and modelspace has entities."""
    path = Path(path)
    if not path.is_file():
        return False
    try:
        from ezdxf import recover

        # ponytail: errors=ignore skips auditor stdout spam; probe only, not full extraction
        doc, _auditor = recover.readfile(str(path), errors="ignore")
        return len(list(doc.modelspace())) > 0
    except Exception:
        return False


def _discipline_value(discipline: Discipline | str) -> str:
    if isinstance(discipline, Discipline):
        return discipline.value
    return str(discipline)


def extract_dxf_geometry(
    path: Path,
    discipline: Discipline | str,
    *,
    include_non_physical: bool = True,
    virtual_fallback_cap: int = 50,
) -> DxfGeometryExtraction:
    """Extract stable per-entity model-space bounds from a DXF file."""
    path = Path(path)
    result = DxfGeometryExtraction(
        path=str(path),
        discipline=_discipline_value(discipline),
        dxf_present=path.is_file(),
    )
    if not path.is_file():
        return result

    t0 = time.perf_counter()
    doc, recovered_partial, recovered_salvaged = _read_dxf(path)
    result.recovered_partial = recovered_partial
    result.recovered_salvaged = recovered_salvaged
    t1 = time.perf_counter()

    try:
        result.insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    except Exception:
        result.insunits = None
    resolver = FastDxfBBoxResolver(doc, virtual_fallback_cap=virtual_fallback_cap)
    header_ref, ref_source = drawing_reference_bounds(doc)
    entities = list(doc.modelspace())
    t2 = time.perf_counter()

    all_bounds: list[BoundsXY] = []
    pending: list[tuple[DXFEntity, BoundsXY, str, bool]] = []
    by_type: dict[str, _TypeStats] = defaultdict(_TypeStats)
    insert_stats = _InsertStats()

    for entity in entities:
        dxftype = entity.dxftype()
        layer = str(getattr(entity.dxf, "layer", "") or "")
        physical = is_physical_entity(layer, dxftype)
        type_stats = by_type[dxftype]
        type_stats.total += 1
        result.stats.all_entities += 1
        if physical:
            type_stats.physical_total += 1
            result.stats.physical_entities += 1

        bounds, method = resolver.entity_bounds(entity)
        if bounds is None:
            type_stats.bbox_failed += 1
            result.stats.bbox_failed += 1
            if dxftype == "INSERT":
                insert_stats.total += 1
                insert_stats.failed += 1
                if physical:
                    insert_stats.physical_total += 1
            continue

        type_stats.bbox_ok += 1
        result.stats.all_bbox_ok += 1
        all_bounds.append(bounds)
        if physical:
            type_stats.physical_bbox_ok += 1
            result.stats.physical_bbox_ok += 1

        if dxftype == "INSERT":
            insert_stats.total += 1
            insert_stats.resolved += 1
            insert_stats.block_bbox_resolved += int(method == "insert_block_bbox")
            insert_stats.virtual_resolved += int(method == "insert_virtual_fallback")
            if physical:
                insert_stats.physical_total += 1
                insert_stats.physical_resolved += 1

        if include_non_physical or physical:
            pending.append((entity, bounds, method, physical))

    result.ref_bounds = header_ref or _union_bounds(all_bounds) or (0.0, 0.0, 1.0, 1.0)
    result.ref_bounds_source = ref_source if header_ref is not None else "entity_bbox_union"

    quality_by_handle: dict[str, str] = {}
    for entity, bounds, _method, physical in pending:
        quality = classify_model_geometry_quality(bounds, result.ref_bounds)
        handle = normalize_handle(entity.dxf.handle)
        quality_by_handle[handle] = quality
        if physical:
            type_stats = by_type[entity.dxftype()]
            if quality == "good":
                result.stats.physical_good += 1
                type_stats.physical_good += 1
            elif quality == "coarse":
                result.stats.physical_coarse += 1
                type_stats.physical_coarse += 1
            else:
                result.stats.physical_unlocalizable += 1
                type_stats.physical_unlocalizable += 1

    records: list[DxfGeometryRecord] = []
    for entity, bounds, method, physical in pending:
        handle = normalize_handle(entity.dxf.handle)
        layer = str(getattr(entity.dxf, "layer", "") or "")
        dxftype = entity.dxftype()
        block_name = str(entity.dxf.name) if dxftype == "INSERT" else None
        records.append(
            DxfGeometryRecord(
                handle=handle,
                layer=layer,
                discipline=result.discipline,
                dxftype=dxftype,
                source_ref=f"{path.as_posix()}|{handle}|{layer}|{dxftype}",
                model_bounds=bounds,
                model_center=_center(bounds),
                geometry_quality=quality_by_handle.get(handle, "coarse"),
                block_resolution_method=method,
                is_physical=physical,
                block_name=block_name,
            )
        )

    t3 = time.perf_counter()
    result.records = records
    result.stats.by_dxftype = {
        dxftype: {
            "total": stats.total,
            "bbox_ok": stats.bbox_ok,
            "bbox_failed": stats.bbox_failed,
            "physical_total": stats.physical_total,
            "physical_bbox_ok": stats.physical_bbox_ok,
            "physical_good": stats.physical_good,
            "physical_coarse": stats.physical_coarse,
            "physical_unlocalizable": stats.physical_unlocalizable,
        }
        for dxftype, stats in sorted(by_type.items(), key=lambda item: (-item[1].total, item[0]))
    }
    method_counts = Counter(record.block_resolution_method for record in records)
    result.stats.insert_stats = {
        "insert_total": insert_stats.total,
        "insert_resolved": insert_stats.resolved,
        "insert_failed": insert_stats.failed,
        "block_bbox_resolved": insert_stats.block_bbox_resolved,
        "virtual_fallback_resolved": insert_stats.virtual_resolved,
        "virtual_fallback_attempts": resolver.virtual_attempts,
        "virtual_fallback_capped": resolver.virtual_capped,
        "block_defs_cached": len(resolver.block_cache),
        "block_cache_hits": resolver.block_cache_hits,
        "block_cache_misses": resolver.block_cache_misses,
        "physical_in_inserts": insert_stats.physical_resolved,
        "resolution_methods": {str(k): v for k, v in sorted(method_counts.items()) if k is not None},
    }
    result.timings = {
        "read_dxf_s": round(t1 - t0, 3),
        "prepare_s": round(t2 - t1, 3),
        "entity_pass_s": round(t3 - t2, 3),
        "total_s": round(t3 - t0, 3),
    }
    return result

