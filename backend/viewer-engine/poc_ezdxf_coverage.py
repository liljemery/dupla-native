#!/usr/bin/env python3
"""Coverage POC: full-scale ezdxf vs APS Layer 1 (no refactor)."""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import bbox
from ezdxf.entities import DXFEntity, Insert

# Match APS Layer-1 quality thresholds (from_aps_viewer_dump.py)
SHEET_AXIS_COVERAGE_GOOD_MAX = 0.60
SHEET_AREA_COVERAGE_GOOD_MAX = 0.25
SHEET_AXIS_COVERAGE_UNLOCALIZABLE_MIN = 0.95
SHEET_AREA_COVERAGE_UNLOCALIZABLE_MIN = 0.85

ANNOTATION_LAYER_TOKENS = (
    "DEFPOINTS", "VIEWPORT", "TITLE", "BORDER", "FRAME", "GRID", "TEXT", "ANNO",
    "DIM", "LABEL", "LEGEND", "SIMBO", "NOTA", "TEXTO", "ESCALA", "NORTH", "NUMERO",
    "TITULOS", "MARCO", "CARTUCHO", "SELLO", "REV", "LEADER",
)
PHYSICAL_LAYER_TOKENS = (
    "WALL", "MURO", "DOOR", "PUERTA", "COL", "COLUMN", "VIGA", "BEAM", "PIPE",
    "DUCT", "ELEC", "LIGHT", "TOMA", "TABLERO", "SAN", "FONTAN", "COLUMNAS",
    "A-WALL", "A-DOOR", "S-WALL", "E-", "HS-", "CLIM", "HVAC", "CABLE", "LUM",
    "PANEL", "CONTACT", "SWITCH", "RECEPT",
)
NON_PHYSICAL_DXFTYPES = {
    "TEXT", "MTEXT", "DIMENSION", "LEADER", "MLEADER", "VIEWPORT",
    "ATTDEF", "ATTRIB", "SHAPE", "IMAGE", "WIPEOUT", "RAY", "XLINE",
}

CACHE_DIR = Path(
    "/Users/samuelfernandez/dupla-native/var/coord_outputs/09a33a3e-9230-4aa2-a445-30df0bc2aee5/cache"
)
DEFAULT_ARQ_DXF = Path("/tmp/oda_nasas_test/out/PLANOS ARQ.-LAS NASAS 09-20260320.dxf")
DEFAULT_ELEC_DXF = Path("/tmp/oda_nasas_elec/out/20.03.2026 LAS NASAS 09-PLANOS ELECTRICOS .dxf")

# viewer.json filenames are base64 URNs — discover by decoding urn field or hash suffix.
def _decode_aps_urn(urn: str) -> str:
    import base64

    text = str(urn or "").strip()
    if not text:
        return ""
    if text.startswith("urn:"):
        return text
    pad = "=" * (-len(text) % 4)
    try:
        return base64.b64decode(text + pad).decode("utf-8", errors="ignore")
    except Exception:
        return text


def _discover_viewer_json(*needles: str) -> Path | None:
    needles_upper = [n.upper() for n in needles]
    for path in sorted(CACHE_DIR.glob("*.viewer.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        decoded = _decode_aps_urn(str(data.get("urn") or ""))
        haystack = f"{path.name} {decoded}".upper()
        if any(n in haystack for n in needles_upper):
            return path
    return None


ARQ_VIEWER_JSON = _discover_viewer_json("PLANOS ARQ", "275a5bb94073")
ELEC_VIEWER_JSON = _discover_viewer_json("ELECTRICOS", "292294b06f77")

# Physical-element tightness in model meters (NASAS $INSUNITS=6).
PHYSICAL_GOOD_MAX_AXIS_M = 25.0
PHYSICAL_GOOD_MAX_AREA_M2 = 600.0
PHYSICAL_UNLOCALIZABLE_AXIS_RATIO = 0.95
PHYSICAL_UNLOCALIZABLE_AREA_RATIO = 0.85


def normalize_handle(value: str) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("0X"):
        text = text[2:]
    return text.lstrip("0") or "0"


def is_annotation_layer(layer: str) -> bool:
    upper = layer.upper()
    return any(token in upper for token in ANNOTATION_LAYER_TOKENS)


def is_physical_entity(layer: str, dxftype: str) -> bool:
    if is_annotation_layer(layer):
        return False
    if dxftype in NON_PHYSICAL_DXFTYPES:
        return False
    upper = layer.upper()
    if any(token in upper for token in PHYSICAL_LAYER_TOKENS):
        return True
    if dxftype in {"INSERT", "LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "HATCH", "ELLIPSE", "SOLID", "3DFACE", "SPLINE"}:
        return bool(layer.strip()) and layer != "0"
    return False


def classify_quality_sheet(
    bounds: tuple[float, float, float, float],
    ref: tuple[float, float, float, float],
) -> str:
    ref_w = max(ref[2] - ref[0], 1e-9)
    ref_h = max(ref[3] - ref[1], 1e-9)
    ref_area = ref_w * ref_h
    w = max(bounds[2] - bounds[0], 0.0)
    h = max(bounds[3] - bounds[1], 0.0)
    x_ratio = w / ref_w
    y_ratio = h / ref_h
    area_ratio = (w * h) / ref_area
    if (
        x_ratio >= SHEET_AXIS_COVERAGE_UNLOCALIZABLE_MIN
        or y_ratio >= SHEET_AXIS_COVERAGE_UNLOCALIZABLE_MIN
        or area_ratio >= SHEET_AREA_COVERAGE_UNLOCALIZABLE_MIN
    ):
        return "unlocalizable"
    if (
        x_ratio < SHEET_AXIS_COVERAGE_GOOD_MAX
        and y_ratio < SHEET_AXIS_COVERAGE_GOOD_MAX
        and area_ratio < SHEET_AREA_COVERAGE_GOOD_MAX
    ):
        return "good"
    return "coarse"


def classify_quality_model_meters(
    bounds: tuple[float, float, float, float],
    model_ref: tuple[float, float, float, float],
) -> str:
    """Classify DXF model-space bboxes using building-scale thresholds."""
    ref_w = max(model_ref[2] - model_ref[0], 1e-9)
    ref_h = max(model_ref[3] - model_ref[1], 1e-9)
    ref_area = ref_w * ref_h
    w = max(bounds[2] - bounds[0], 0.0)
    h = max(bounds[3] - bounds[1], 0.0)
    area = w * h
    x_ratio = w / ref_w
    y_ratio = h / ref_h
    area_ratio = area / ref_area
    if (
        x_ratio >= PHYSICAL_UNLOCALIZABLE_AXIS_RATIO
        or y_ratio >= PHYSICAL_UNLOCALIZABLE_AXIS_RATIO
        or area_ratio >= PHYSICAL_UNLOCALIZABLE_AREA_RATIO
    ):
        return "unlocalizable"
    if w <= PHYSICAL_GOOD_MAX_AXIS_M and h <= PHYSICAL_GOOD_MAX_AXIS_M and area <= PHYSICAL_GOOD_MAX_AREA_M2:
        return "good"
    return "coarse"


def bounds_from_extents(ext) -> tuple[float, float, float, float] | None:
    if not ext.has_data:
        return None
    min_x, min_y = float(ext.extmin.x), float(ext.extmin.y)
    max_x, max_y = float(ext.extmax.x), float(ext.extmax.y)
    if not all(map(math.isfinite, (min_x, min_y, max_x, max_y))):
        return None
    if max_x <= min_x and max_y <= min_y:
        return None
    if max_x <= min_x:
        max_x = min_x + 1e-6
    if max_y <= min_y:
        max_y = min_y + 1e-6
    return (min_x, min_y, max_x, max_y)


def entity_bbox(entity: DXFEntity, cache: bbox.Cache) -> tuple[tuple[float, float, float, float] | None, str]:
    try:
        ext = bbox.extents([entity], cache=cache)
        bounds = bounds_from_extents(ext)
        if bounds:
            return bounds, "direct"
    except Exception:
        pass
    if entity.dxftype() == "INSERT":
        try:
            insert = Insert(entity)
            points: list[tuple[float, float]] = []
            for virtual in insert.virtual_entities():
                try:
                    sub = bbox.extents([virtual], cache=cache)
                except Exception:
                    continue
                b = bounds_from_extents(sub)
                if b:
                    points.extend([(b[0], b[1]), (b[2], b[3])])
            if points:
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                return (min(xs), min(ys), max(xs), max(ys)), "insert_virtual"
        except Exception:
            return None, "insert_failed"
    return None, "failed"


def drawing_reference_bounds(doc: ezdxf.document.Drawing) -> tuple[tuple[float, float, float, float], str]:
    try:
        extmin = doc.header.get("$EXTMIN")
        extmax = doc.header.get("$EXTMAX")
        if extmin and extmax:
            bounds = (
                float(extmin[0]), float(extmin[1]),
                float(extmax[0]), float(extmax[1]),
            )
            if bounds[2] > bounds[0] and bounds[3] > bounds[1]:
                if abs(bounds[0]) < 1e19 and abs(bounds[2]) < 1e19:
                    return bounds, "header_extents"
    except Exception:
        pass
    cache = bbox.Cache()
    ext = bbox.extents(doc.modelspace(), cache=cache)
    b = bounds_from_extents(ext)
    if b:
        return b, "computed_modelspace_union"
    return (0.0, 0.0, 1.0, 1.0), "fallback_unit_square"


@dataclass
class TypeStats:
    total: int = 0
    bbox_ok: int = 0
    bbox_failed: int = 0
    physical_total: int = 0
    physical_bbox_ok: int = 0
    physical_good: int = 0
    physical_coarse: int = 0
    physical_unlocalizable: int = 0


@dataclass
class InsertStats:
    total: int = 0
    resolved: int = 0
    failed: int = 0
    physical_total: int = 0
    physical_resolved: int = 0
    sample: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DisciplineReport:
    label: str
    dxf_path: str
    dxf_present: bool
    insunits: int | None = None
    ref_bounds: list[float] | None = None
    ref_bounds_source: str | None = None
    all_entities: int = 0
    all_bbox_ok: int = 0
    physical_entities: int = 0
    physical_bbox_ok: int = 0
    physical_good: int = 0
    physical_coarse: int = 0
    physical_unlocalizable: int = 0
    physical_good_model: int = 0
    physical_coarse_model: int = 0
    physical_unlocalizable_model: int = 0
    by_type: dict[str, dict[str, int]] = field(default_factory=dict)
    insert_stats: dict[str, Any] = field(default_factory=dict)
    aps: dict[str, Any] = field(default_factory=dict)
    handle_mapping: dict[str, Any] = field(default_factory=dict)


def analyze_ezdxf(path: Path, label: str) -> DisciplineReport:
    report = DisciplineReport(label=label, dxf_path=str(path), dxf_present=path.is_file())
    if not path.is_file():
        return report

    doc = ezdxf.readfile(path)
    report.insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    ref_bounds, ref_source = drawing_reference_bounds(doc)
    report.ref_bounds = [round(v, 4) for v in ref_bounds]
    report.ref_bounds_source = ref_source

    cache = bbox.Cache()
    by_type: dict[str, TypeStats] = defaultdict(TypeStats)
    insert_stats = InsertStats()
    insert_samples: list[dict[str, Any]] = []

    for entity in doc.modelspace():
        dxftype = entity.dxftype()
        layer = str(entity.dxf.layer)
        physical = is_physical_entity(layer, dxftype)
        stats = by_type[dxftype]
        stats.total += 1
        report.all_entities += 1
        if physical:
            stats.physical_total += 1
            report.physical_entities += 1

        bounds, method = entity_bbox(entity, cache)
        if bounds is None:
            stats.bbox_failed += 1
            if dxftype == "INSERT":
                insert_stats.total += 1
                insert_stats.failed += 1
                if physical:
                    insert_stats.physical_total += 1
            continue

        stats.bbox_ok += 1
        report.all_bbox_ok += 1
        quality_model = classify_quality_model_meters(bounds, ref_bounds)
        quality = quality_model

        if physical:
            stats.physical_bbox_ok += 1
            report.physical_bbox_ok += 1
            if quality == "good":
                stats.physical_good += 1
                report.physical_good += 1
                report.physical_good_model += 1
            elif quality == "coarse":
                stats.physical_coarse += 1
                report.physical_coarse += 1
                report.physical_coarse_model += 1
            else:
                stats.physical_unlocalizable += 1
                report.physical_unlocalizable += 1
                report.physical_unlocalizable_model += 1

        if dxftype == "INSERT":
            insert_stats.total += 1
            insert_stats.resolved += 1
            if physical:
                insert_stats.physical_total += 1
                insert_stats.physical_resolved += 1
            if len(insert_samples) < 12:
                w = bounds[2] - bounds[0]
                h = bounds[3] - bounds[1]
                insert_samples.append(
                    {
                        "handle": normalize_handle(entity.dxf.handle),
                        "layer": layer,
                        "block": str(entity.dxf.name),
                        "method": method,
                        "bbox_xy": [round(bounds[0], 4), round(bounds[1], 4), round(bounds[2], 4), round(bounds[3], 4)],
                        "size": [round(w, 4), round(h, 4)],
                        "quality": quality,
                        "insertion": [round(float(entity.dxf.insert[0]), 4), round(float(entity.dxf.insert[1]), 4)],
                    }
                )

    report.by_type = {
        dxftype: {
            "total": s.total,
            "bbox_ok": s.bbox_ok,
            "bbox_failed": s.bbox_failed,
            "physical_total": s.physical_total,
            "physical_bbox_ok": s.physical_bbox_ok,
            "physical_good": s.physical_good,
            "physical_coarse": s.physical_coarse,
            "physical_unlocalizable": s.physical_unlocalizable,
        }
        for dxftype, s in sorted(by_type.items(), key=lambda item: -item[1].total)
    }
    loose_physical = report.physical_bbox_ok - insert_stats.physical_resolved
    report.insert_stats = {
        "insert_total": insert_stats.total,
        "insert_resolved": insert_stats.resolved,
        "insert_failed": insert_stats.failed,
        "insert_resolved_pct": round(100.0 * insert_stats.resolved / insert_stats.total, 1) if insert_stats.total else 0.0,
        "physical_in_inserts": insert_stats.physical_resolved,
        "physical_loose_entities": max(0, loose_physical),
        "physical_in_inserts_pct": round(
            100.0 * insert_stats.physical_resolved / report.physical_bbox_ok, 1
        ) if report.physical_bbox_ok else 0.0,
        "samples": insert_samples,
    }
    return report


def _aps_object_bounds(obj: dict[str, Any]) -> tuple[tuple[float, float, float, float] | None, list[tuple[float, float, float, float]]]:
    agg = None
    for key in ("world_bounds", "aggregate_world_bounds"):
        raw = obj.get(key)
        if isinstance(raw, list) and len(raw) >= 4:
            agg = tuple(float(v) for v in raw[:4])
            break
    fragments: list[tuple[float, float, float, float]] = []
    for frag in obj.get("fragments") or []:
        if isinstance(frag, dict) and isinstance(frag.get("world_bounds"), list) and len(frag["world_bounds"]) >= 4:
            fragments.append(tuple(float(v) for v in frag["world_bounds"][:4]))
    return agg, fragments


def _collect_aps_objects(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    views = data.get("views") or []
    all_objects: list[dict[str, Any]] = []
    view_summaries: list[dict[str, Any]] = []
    for view in views:
        objects = view.get("objects") or []
        all_objects.extend(objects)
        view_summaries.append(
            {
                "name": view.get("name"),
                "object_count": len(objects),
                "sheet_bounds": view.get("sheet_bounds"),
            }
        )
    return all_objects, view_summaries


def analyze_aps_viewer_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"present": False, "path": str(path) if path else None}

    data = json.loads(path.read_text())
    objects, view_summaries = _collect_aps_objects(data)
    default_sheet = None
    for view in data.get("views") or []:
        if isinstance(view.get("sheet_bounds"), list) and len(view["sheet_bounds"]) >= 4:
            default_sheet = tuple(float(v) for v in view["sheet_bounds"][:4])
            break

    stats = Counter()
    physical_stats = Counter()
    handle_to_dbid: dict[str, int] = {}

    for obj in objects:
        layer = str(obj.get("layer") or "")
        dxftype = "APS_OBJECT"
        physical = is_physical_entity(layer, dxftype)
        aggregate, fragments = _aps_object_bounds(obj)
        if aggregate is None:
            stats["failed"] += 1
            continue
        stats["bbox_ok"] += 1
        sheet = default_sheet or aggregate
        quality = classify_quality_sheet(aggregate, sheet)
        if quality != "good" and fragments:
            frag_qualities = [(f, classify_quality_sheet(f, sheet)) for f in fragments]
            good_frags = [f for f, q in frag_qualities if q == "good"]
            if good_frags:
                quality = "good"
            else:
                coarse_frags = [f for f, q in frag_qualities if q == "coarse"]
                if coarse_frags:
                    quality = "coarse"
        stats[quality] += 1
        if physical:
            physical_stats["total"] += 1
            physical_stats["bbox_ok"] += 1
            physical_stats[quality] += 1
        handle = normalize_handle(str(obj.get("handle") or ""))
        if handle and obj.get("dbId") is not None:
            handle_to_dbid[handle] = int(obj["dbId"])

    def pct(num: int, den: int) -> float:
        return round(100.0 * num / den, 1) if den else 0.0

    phys_good = physical_stats["good"]
    phys_coarse = physical_stats["coarse"]
    phys_total = physical_stats["bbox_ok"]

    return {
        "present": True,
        "path": str(path),
        "view_count": len(view_summaries),
        "object_count": len(objects),
        "view_summaries": view_summaries[:5],
        "sheet_bounds": list(default_sheet) if default_sheet else None,
        "all_bbox_ok": stats["bbox_ok"],
        "physical_total": physical_stats["total"],
        "physical_bbox_ok": phys_total,
        "physical_good": phys_good,
        "physical_coarse": phys_coarse,
        "physical_unlocalizable": physical_stats["unlocalizable"],
        "physical_good_pct": pct(phys_good, phys_total),
        "physical_good_plus_coarse_pct": pct(phys_good + phys_coarse, phys_total),
        "physical_bbox_ok_pct": pct(phys_total, physical_stats["total"]),
        "handle_map_size": len(handle_to_dbid),
        "handle_to_dbid": handle_to_dbid,
    }


def sample_dxf_handles(path: Path, n: int = 20) -> list[str]:
    doc = ezdxf.readfile(path)
    cache = bbox.Cache()
    physical_handles: list[str] = []
    other_handles: list[str] = []
    for entity in doc.modelspace():
        handle = normalize_handle(entity.dxf.handle)
        layer = str(entity.dxf.layer)
        if not handle:
            continue
        bounds, _ = entity_bbox(entity, cache)
        if bounds is None:
            continue
        if is_physical_entity(layer, entity.dxftype()):
            physical_handles.append(handle)
        else:
            other_handles.append(handle)
    rng = random.Random(42)
    picks: list[str] = []
    if len(physical_handles) >= n:
        picks = rng.sample(physical_handles, n)
    else:
        picks = list(physical_handles)
        remaining = n - len(picks)
        if remaining > 0 and other_handles:
            picks.extend(rng.sample(other_handles, min(remaining, len(other_handles))))
    return picks


def full_dxf_handle_mapping_rate(dxf_path: Path, handle_map: dict[str, int]) -> dict[str, Any]:
    if not dxf_path.is_file():
        return {}
    doc = ezdxf.readfile(dxf_path)
    expanded = {normalize_handle(h): dbid for h, dbid in handle_map.items()}
    total = 0
    mapped = 0
    physical_total = 0
    physical_mapped = 0
    for entity in doc.modelspace():
        handle = normalize_handle(entity.dxf.handle)
        if not handle:
            continue
        total += 1
        is_mapped = handle in expanded
        if is_mapped:
            mapped += 1
        if is_physical_entity(str(entity.dxf.layer), entity.dxftype()):
            physical_total += 1
            if is_mapped:
                physical_mapped += 1
    return {
        "dxf_handles_total": total,
        "dxf_handles_mapped": mapped,
        "dxf_handles_mapped_pct": pct(mapped, total),
        "dxf_physical_handles_total": physical_total,
        "dxf_physical_handles_mapped": physical_mapped,
        "dxf_physical_handles_mapped_pct": pct(physical_mapped, physical_total),
    }


def analyze_handle_mapping(dxf_path: Path, aps_data: dict[str, Any], sample_size: int = 20) -> dict[str, Any]:
    if not dxf_path.is_file() or not aps_data.get("present"):
        return {"present": False}
    handle_map: dict[str, int] = aps_data.get("handle_to_dbid") or {}
    # also index zero-padded variants
    expanded: dict[str, int] = {}
    for handle, dbid in handle_map.items():
        expanded[normalize_handle(handle)] = dbid
        expanded[handle.upper()] = dbid

    samples = sample_dxf_handles(dxf_path, sample_size)
    rows = []
    mapped = 0
    for handle in samples:
        norm = normalize_handle(handle)
        dbid = expanded.get(norm) or expanded.get(handle.upper())
        if dbid is not None:
            mapped += 1
        rows.append({"handle": handle, "normalized": norm, "dbId": dbid, "mapped": dbid is not None})

    target_handles = ["96080E7", "96080E8", "960BBDD", "1C3E45A", "3CD1040"]
    target_rows = []
    for handle in target_handles:
        norm = normalize_handle(handle)
        dbid = expanded.get(norm) or expanded.get(handle.upper())
        target_rows.append({"handle": handle, "dbId": dbid, "mapped": dbid is not None})

    full_rate = full_dxf_handle_mapping_rate(dxf_path, handle_map)
    return {
        "present": True,
        "aps_map_entries": len(handle_map),
        "sample_size": len(samples),
        "sample_mapped": mapped,
        "sample_mapped_pct": round(100.0 * mapped / len(samples), 1) if samples else 0.0,
        "sample_rows": rows,
        "target_handles": target_rows,
        "target_mapped_pct": round(
            100.0 * sum(1 for row in target_rows if row["mapped"]) / len(target_rows), 1
        ),
        **full_rate,
    }


def pct(num: int, den: int) -> float:
    return round(100.0 * num / den, 1) if den else 0.0


def compare_ezdxf_vs_aps(ezdxf_report: DisciplineReport, aps: dict[str, Any]) -> dict[str, Any]:
    if not ezdxf_report.dxf_present or not aps.get("present"):
        return {"comparable": False}
    e_good = pct(ezdxf_report.physical_good, ezdxf_report.physical_bbox_ok)
    e_gc = pct(ezdxf_report.physical_good + ezdxf_report.physical_coarse, ezdxf_report.physical_bbox_ok)
    return {
        "comparable": True,
        "ezdxf_physical_good_pct": e_good,
        "ezdxf_physical_good_plus_coarse_pct": e_gc,
        "ezdxf_physical_bbox_ok_pct": pct(ezdxf_report.physical_bbox_ok, ezdxf_report.physical_entities),
        "aps_physical_good_pct": aps.get("physical_good_pct"),
        "aps_physical_good_plus_coarse_pct": aps.get("physical_good_plus_coarse_pct"),
        "delta_good_pts": round(e_good - float(aps.get("physical_good_pct") or 0), 1),
        "delta_good_coarse_pts": round(e_gc - float(aps.get("physical_good_plus_coarse_pct") or 0), 1),
        "better_than_aps": e_good > float(aps.get("physical_good_pct") or 0),
    }


def render_verdict(reports: list[DisciplineReport], comparisons: list[dict[str, Any]], mappings: list[dict[str, Any]]) -> str:
    issues: list[str] = []
    greens: list[str] = []

    for rep, cmp_, map_ in zip(reports, comparisons, mappings):
        if not rep.dxf_present:
            issues.append(f"{rep.label}: DXF missing")
            continue
        if cmp_.get("comparable"):
            eg = cmp_["ezdxf_physical_good_pct"]
            ag = cmp_["aps_physical_good_pct"]
            egc = cmp_["ezdxf_physical_good_plus_coarse_pct"]
            agc = cmp_["aps_physical_good_plus_coarse_pct"]
            greens.append(
                f"{rep.label} coverage: ezdxf good {eg}% / good+coarse {egc}% vs APS {ag}% / {agc}%"
            )
            if eg <= ag and egc <= agc:
                issues.append(f"{rep.label}: ezdxf not better than APS on physical geometry")
        ins = rep.insert_stats
        if ins.get("insert_total", 0) > 0:
            resolved_pct = ins.get("insert_resolved_pct", 0)
            if resolved_pct < 90:
                issues.append(f"{rep.label}: INSERT resolution only {resolved_pct}%")
            else:
                greens.append(f"{rep.label} INSERTs: {resolved_pct}% resolve ({ins.get('physical_in_inserts_pct', 0)}% of physical bbox in blocks)")
        if map_.get("present"):
            mp = map_.get("sample_mapped_pct", 0)
            if mp < 50:
                issues.append(f"{rep.label}: handle→dbId mapping only {mp}% on sample")
            else:
                greens.append(f"{rep.label} handle mapping: {mp}% sample, targets {map_.get('target_mapped_pct')}%")

    if issues:
        return "ISSUES: " + "; ".join(issues) + " | Notes: " + "; ".join(greens)
    return (
        "REFACTOR GREENLIT: "
        + "; ".join(greens)
        + " — proceed to full Layer 1 rewrite (pending product sign-off)."
    )


def print_report(rep: DisciplineReport) -> None:
    print(f"\n{'=' * 72}\n{rep.label}\n{'=' * 72}")
    print(f"DXF: {rep.dxf_path}  present={rep.dxf_present}")
    if not rep.dxf_present:
        print("BLOCKED for this discipline.")
        return
    print(f"$INSUNITS={rep.insunits}  ref_bounds={rep.ref_bounds} ({rep.ref_bounds_source})")
    print(
        f"ALL entities: {rep.all_entities} | bbox_ok {rep.all_bbox_ok} ({pct(rep.all_bbox_ok, rep.all_entities)}%)"
    )
    print(
        f"PHYSICAL entities: {rep.physical_entities} | bbox_ok {rep.physical_bbox_ok} ({pct(rep.physical_bbox_ok, rep.physical_entities)}%)"
    )
    print(
        f"PHYSICAL quality (model-scale ≤{PHYSICAL_GOOD_MAX_AXIS_M}m axis): "
        f"good {rep.physical_good} ({pct(rep.physical_good, rep.physical_bbox_ok)}%) | "
        f"coarse {rep.physical_coarse} ({pct(rep.physical_coarse, rep.physical_bbox_ok)}%) | "
        f"unlocalizable {rep.physical_unlocalizable} ({pct(rep.physical_unlocalizable, rep.physical_bbox_ok)}%)"
    )
    print(f"PHYSICAL good+coarse: {pct(rep.physical_good + rep.physical_coarse, rep.physical_bbox_ok)}%")
    print(f"PHYSICAL bbox_ok (usable geometry): {pct(rep.physical_bbox_ok, rep.physical_entities)}%")
    print("\nBy dxftype (top 15):")
    for dxftype, stats in list(rep.by_type.items())[:15]:
        print(
            f"  {dxftype:12} total={stats['total']:6} bbox_ok={stats['bbox_ok']:6} fail={stats['bbox_failed']:5} | "
            f"phys={stats['physical_total']:5} phys_good={stats['physical_good']:5}"
        )
    print("\nINSERT resolution:")
    print(json.dumps(rep.insert_stats, indent=2))
    if rep.aps.get("present"):
        print("\nAPS Layer-1 baseline (viewer.json):")
        print(json.dumps({k: rep.aps[k] for k in rep.aps if k != "handle_to_dbid"}, indent=2))
    if rep.handle_mapping.get("present"):
        print("\nHandle mapping sample:")
        print(json.dumps({k: rep.handle_mapping[k] for k in rep.handle_mapping if k != "sample_rows"}, indent=2))
        print("Sample rows:", json.dumps(rep.handle_mapping.get("sample_rows", [])[:5], indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="ezdxf full-scale coverage POC")
    parser.add_argument("--arq-dxf", type=Path, default=DEFAULT_ARQ_DXF)
    parser.add_argument("--elec-dxf", type=Path, default=DEFAULT_ELEC_DXF)
    parser.add_argument("--arq-viewer-json", type=Path, default=ARQ_VIEWER_JSON)
    parser.add_argument("--elec-viewer-json", type=Path, default=ELEC_VIEWER_JSON)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    configs = [
        ("ARQ", args.arq_dxf, args.arq_viewer_json),
        ("ELEC", args.elec_dxf, args.elec_viewer_json),
    ]

    reports: list[DisciplineReport] = []
    comparisons: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []

    for label, dxf_path, viewer_json in configs:
        rep = analyze_ezdxf(dxf_path, label)
        aps = analyze_aps_viewer_json(viewer_json)
        rep.aps = {k: v for k, v in aps.items() if k != "handle_to_dbid"}
        rep.handle_mapping = analyze_handle_mapping(dxf_path, aps)
        cmp_ = compare_ezdxf_vs_aps(rep, aps)
        reports.append(rep)
        comparisons.append(cmp_)
        mappings.append(rep.handle_mapping)
        print_report(rep)
        if cmp_.get("comparable"):
            print("\nComparison ezdxf vs APS:", json.dumps(cmp_, indent=2))

    verdict = render_verdict(reports, comparisons, mappings)
    print(f"\n{'=' * 72}\nVERDICT\n{'=' * 72}\n{verdict}\n")

    if args.json_out:
        payload = {
            "reports": [rep.__dict__ for rep in reports],
            "comparisons": comparisons,
            "mappings": mappings,
            "verdict": verdict,
        }
        args.json_out.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
