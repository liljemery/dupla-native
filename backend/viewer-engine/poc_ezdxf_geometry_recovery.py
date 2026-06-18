#!/usr/bin/env python3
"""POC: recover real model-space bboxes via ezdxf (vs APS F2D full-sheet collapse).

Usage:
  python poc_ezdxf_geometry_recovery.py path/to/drawing.dxf
  python poc_ezdxf_geometry_recovery.py path/to/drawing.dxf --handles 96080E7 96080E8
  python poc_ezdxf_geometry_recovery.py --write-sample /tmp/nasas_arq_poc_sample.dxf
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import ezdxf
from ezdxf import bbox, units
from ezdxf.entities import DXFEntity, Insert

# APS F2D fragment bounds observed on LAS NASAS ARQ (sheet paper frame, identical collapse).
APS_COLLAPSED_BOUNDS: dict[str, dict[str, Any]] = {
    "96080E7": {
        "layer": "Columnas",
        "aps_bounds": [0.7358, 0.7725, 35.3312, 22.6946],
        "note": "Identical full-sheet fragment across column handles",
    },
    "96080E8": {
        "layer": "Columnas",
        "aps_bounds": [0.7358, 0.7725, 35.3312, 22.6946],
        "note": "Identical full-sheet fragment across column handles",
    },
    "960BBDD": {
        "layer": "Columnas",
        "aps_bounds": [0.7358, 0.7725, 35.3312, 22.6946],
        "note": "Identical full-sheet fragment across column handles",
    },
    "1C3E45A": {
        "layer": "A-WALL",
        "aps_bounds": [-0.0000005, -0.27, 36.27, 24.0],
        "note": "Full-sheet drawing extents",
    },
    "3CD1040": {
        "layer": "A-DOOR",
        "aps_bounds": [-0.0000005, -0.27, 36.27, 24.0],
        "note": "Full-sheet drawing extents",
    },
}

TARGET_HANDLES = list(APS_COLLAPSED_BOUNDS.keys())
INSUNITS_LABELS = {
    0: "unitless",
    1: "inches",
    2: "feet",
    3: "miles",
    4: "millimeters",
    5: "centimeters",
    6: "meters",
    7: "kilometers",
}


@dataclass
class EntityReport:
    handle: str
    layer: str
    dxftype: str
    bbox_min: tuple[float, float, float]
    bbox_max: tuple[float, float, float]
    center: tuple[float, float, float]
    width: float
    height: float
    block_name: str | None = None


@dataclass
class DrawingMeta:
    path: str
    insunits: int
    insunits_label: str
    insbase: tuple[float, float, float]
    extmin: tuple[float, float, float] | None
    extmax: tuple[float, float, float] | None
    entity_count: int


def _vec3(point: Any) -> tuple[float, float, float]:
    return (float(point[0]), float(point[1]), float(getattr(point, "z", point[2] if len(point) > 2 else 0.0)))


def _entity_bbox(entity: DXFEntity, cache: bbox.Cache) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    try:
        ext = bbox.extents([entity], cache=cache)
    except Exception:
        ext = None
    if ext.has_data:
        return _vec3(ext.extmin), _vec3(ext.extmax)

    if entity.dxftype() == "INSERT":
        insert = Insert(entity)
        points: list[tuple[float, float, float]] = []
        for virtual in insert.virtual_entities():
            try:
                sub = bbox.extents([virtual], cache=cache)
            except Exception:
                continue
            if sub.has_data:
                points.append(_vec3(sub.extmin))
                points.append(_vec3(sub.extmax))
        if points:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            zs = [p[2] for p in points]
            return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
    return None


def _center(min_pt: tuple[float, float, float], max_pt: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        (min_pt[0] + max_pt[0]) / 2.0,
        (min_pt[1] + max_pt[1]) / 2.0,
        (min_pt[2] + max_pt[2]) / 2.0,
    )


def read_drawing_meta(path: Path, doc: ezdxf.document.Drawing) -> DrawingMeta:
    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    insbase = _vec3(doc.header.get("$INSBASE", (0.0, 0.0, 0.0)))
    extmin = _vec3(doc.header["$EXTMIN"]) if doc.header.get("$EXTMIN") else None
    extmax = _vec3(doc.header["$EXTMAX"]) if doc.header.get("$EXTMAX") else None
    return DrawingMeta(
        path=str(path),
        insunits=insunits,
        insunits_label=INSUNITS_LABELS.get(insunits, f"code_{insunits}"),
        insbase=insbase,
        extmin=extmin,
        extmax=extmax,
        entity_count=len(list(doc.modelspace())),
    )


def extract_modelspace_entities(path: Path, *, handle_filter: Iterable[str] | None = None) -> tuple[DrawingMeta, list[EntityReport], dict[str, EntityReport]]:
    doc = ezdxf.readfile(path)
    meta = read_drawing_meta(path, doc)
    cache = bbox.Cache()
    wanted = {h.upper() for h in handle_filter} if handle_filter else None
    reports: list[EntityReport] = []
    by_handle: dict[str, EntityReport] = {}

    for entity in doc.modelspace():
        handle = str(entity.dxf.handle).upper()
        if wanted is not None and handle not in wanted:
            continue
        bounds = _entity_bbox(entity, cache)
        if bounds is None:
            continue
        min_pt, max_pt = bounds
        block_name = str(entity.dxf.name) if entity.dxftype() == "INSERT" else None
        report = EntityReport(
            handle=handle,
            layer=str(entity.dxf.layer),
            dxftype=entity.dxftype(),
            bbox_min=min_pt,
            bbox_max=max_pt,
            center=_center(min_pt, max_pt),
            width=max_pt[0] - min_pt[0],
            height=max_pt[1] - min_pt[1],
            block_name=block_name,
        )
        reports.append(report)
        by_handle[handle] = report
    return meta, reports, by_handle


def write_poc_sample_dxf(path: Path) -> None:
    """Synthetic DXF: distinct column footprints + wall + door at APS target handles."""
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4  # millimeters
    doc.header["$INSBASE"] = (0.0, 0.0, 0.0)
    msp = doc.modelspace()

    # Three distinct column proxies (0.4m x 0.4m squares) — NOT full sheet.
    column_specs = [
        ("96080E7", (12500.0, 8400.0)),
        ("96080E8", (18750.0, 8400.0)),
        ("960BBDD", (25000.0, 8400.0)),
    ]
    half = 200.0
    for handle, (cx, cy) in column_specs:
        msp.add_lwpolyline(
            [
                (cx - half, cy - half),
                (cx + half, cy - half),
                (cx + half, cy + half),
                (cx - half, cy + half),
            ],
            close=True,
            dxfattribs={"layer": "Columnas", "handle": handle},
        )

    # Wall segment — tight line, not sheet extents.
    msp.add_line(
        (12000.0, 8000.0),
        (26000.0, 8000.0),
        dxfattribs={"layer": "A-WALL", "handle": "1C3E45A"},
    )

    # Door block insert — localized footprint.
    door_blk = doc.blocks.new("DOOR_900")
    door_blk.add_lwpolyline([(0.0, 0.0), (900.0, 0.0), (900.0, 2100.0), (0.0, 2100.0)], close=True)
    msp.add_blockref(
        "DOOR_900",
        (15200.0, 8100.0),
        dxfattribs={"layer": "A-DOOR", "handle": "3CD1040"},
    )

    doc.header["$EXTMIN"] = (12000.0, 8000.0, 0.0)
    doc.header["$EXTMAX"] = (26000.0, 10200.0, 0.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)


def _fmt_bounds(min_pt: tuple[float, ...], max_pt: tuple[float, ...]) -> list[float]:
    return [round(min_pt[0], 4), round(min_pt[1], 4), round(max_pt[0], 4), round(max_pt[1], 4)]


def _matches_aps_sheet_collapse(ezdxf_bounds: list[float], aps_bounds: list[float], rel_tol: float = 0.02) -> bool:
    """True when ezdxf bbox numerically matches APS collapsed sheet fragment."""
    if len(ezdxf_bounds) != 4 or len(aps_bounds) != 4:
        return False
    span_aps = max(abs(aps_bounds[2] - aps_bounds[0]), abs(aps_bounds[3] - aps_bounds[1]), 1e-9)
    span_ezdxf = max(abs(ezdxf_bounds[2] - ezdxf_bounds[0]), abs(ezdxf_bounds[3] - ezdxf_bounds[1]), 1e-9)
    corner_close = all(abs(ezdxf_bounds[i] - aps_bounds[i]) <= rel_tol * span_aps for i in range(4))
    span_close = abs(span_ezdxf - span_aps) <= rel_tol * span_aps
    return corner_close or span_close


def compare_aps_vs_ezdxf(by_handle: dict[str, EntityReport]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for handle in TARGET_HANDLES:
        aps = APS_COLLAPSED_BOUNDS[handle]
        ezdxf_row = by_handle.get(handle.upper())
        ezdxf_bounds = _fmt_bounds(ezdxf_row.bbox_min, ezdxf_row.bbox_max) if ezdxf_row else None
        rows.append(
            {
                "handle": handle,
                "layer_expected": aps["layer"],
                "aps_bounds_xy": aps["aps_bounds"],
                "aps_note": aps["note"],
                "ezdxf_found": ezdxf_row is not None,
                "ezdxf_layer": ezdxf_row.layer if ezdxf_row else None,
                "ezdxf_dxftype": ezdxf_row.dxftype if ezdxf_row else None,
                "ezdxf_bounds_xy": ezdxf_bounds,
                "ezdxf_center_xy": [round(ezdxf_row.center[0], 4), round(ezdxf_row.center[1], 4)] if ezdxf_row else None,
                "ezdxf_width": round(ezdxf_row.width, 4) if ezdxf_row else None,
                "ezdxf_height": round(ezdxf_row.height, 4) if ezdxf_row else None,
                "distinct_from_aps_sheet": (
                    ezdxf_row is not None
                    and ezdxf_bounds is not None
                    and not _matches_aps_sheet_collapse(ezdxf_bounds, aps["aps_bounds"])
                ),
            }
        )
    return rows


def column_distinctness(by_handle: dict[str, EntityReport]) -> dict[str, Any]:
    cols = [by_handle[h] for h in ("96080E7", "96080E8", "960BBDD") if h in by_handle]
    centers = [(_fmt_bounds(c.bbox_min, c.bbox_max), c.center[:2]) for c in cols]
    unique_centers = len({(round(c[0], 1), round(c[1], 1)) for c in [item[1] for item in centers]})
    unique_bboxes = len({tuple(_fmt_bounds(c.bbox_min, c.bbox_max)) for c in cols})
    return {
        "columns_found": len(cols),
        "unique_centers": unique_centers,
        "unique_bboxes": unique_bboxes,
        "columns_are_distinct": len(cols) >= 3 and unique_centers == 3 and unique_bboxes == 3,
        "centers": {c.handle: [round(c.center[0], 2), round(c.center[1], 2)] for c in cols},
    }


def render_verdict(*, dxf_path: Path | None, is_sample: bool, comparison: list[dict[str, Any]], distinct: dict[str, Any], meta: DrawingMeta | None) -> str:
    if dxf_path is None:
        return (
            "BLOCKED: no usable DXF available in-container. Extraction script is ready; user must "
            "run ODA DWG→DXF on PLANOS ARQ.-LAS NASAS 09-20260320 and pass the path to this script."
        )

    found_targets = sum(1 for row in comparison if row["ezdxf_found"])
    if found_targets == 0:
        return (
            f"BLOCKED: DXF present ({dxf_path.name}) but target handles not found. "
            "Confirm ODA export preserved handles or run against the LAS NASAS ARQ DXF."
        )

    if is_sample:
        if distinct.get("columns_are_distinct"):
            return (
                "MECHANISM VALIDATED on synthetic POC sample (not real LAS NASAS ARQ DXF): ezdxf returns "
                f"distinct tight bounds per handle while APS collapsed them to full-sheet fragments. "
                f"Real units={meta.insunits_label if meta else 'unknown'}, insbase={meta.insbase if meta else '?'}. "
                "User must run this script on ODA-converted NASAS ARQ DXF for final verdict."
            )
        return "ezdxf extraction ran on sample but column distinctness check failed."

    recovered = all(row.get("distinct_from_aps_sheet") for row in comparison if row["ezdxf_found"])
    if recovered and distinct.get("columns_are_distinct"):
        units = meta.insunits_label if meta else "unknown"
        base = meta.insbase if meta else (0, 0, 0)
        return (
            "ezdxf RECOVERS the geometry: handles APS lost now have distinct tight real bounds "
            f"(see comparison table). Hybrid path (ezdxf geometry + APS render) is validated. "
            f"Also report: real units={units}, base point={base} — relevant for Layer 2 alignment."
        )
    return (
        "ezdxf ALSO fails on these: one or more target handles still map to sheet-scale bounds "
        "or columns are not distinct. Hybrid path does not solve it; reconsider."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="POC ezdxf geometry recovery vs APS collapse")
    parser.add_argument("dxf", nargs="?", type=Path, help="Path to DXF (model space)")
    parser.add_argument("--handles", nargs="*", default=TARGET_HANDLES, help="Handles to compare")
    parser.add_argument(
        "--write-sample",
        type=Path,
        help="Write synthetic POC DXF with target handles at distinct locations",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only")
    args = parser.parse_args()

    sample_path = args.write_sample
    if sample_path:
        write_poc_sample_dxf(sample_path)

    dxf_path = args.dxf or sample_path
    if dxf_path is None:
        print("No DXF path provided and --write-sample not used.", file=sys.stderr)
        return 2

    is_sample = bool(sample_path and (args.dxf is None or args.dxf.resolve() == sample_path.resolve()))
    meta, _all_reports, by_handle = extract_modelspace_entities(dxf_path, handle_filter=args.handles)
    comparison = compare_aps_vs_ezdxf(by_handle)
    distinct = column_distinctness(by_handle)
    verdict = render_verdict(
        dxf_path=dxf_path,
        is_sample=is_sample,
        comparison=comparison,
        distinct=distinct,
        meta=meta,
    )

    payload = {
        "dxf_path": str(dxf_path.resolve()),
        "is_synthetic_sample": is_sample,
        "drawing_meta": asdict(meta),
        "aps_vs_ezdxf": comparison,
        "column_distinctness": distinct,
        "verdict": verdict,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("=" * 72)
        print("POC: ezdxf geometry recovery vs APS F2D collapse")
        print("=" * 72)
        print(f"DXF file     : {dxf_path.resolve()}")
        print(f"Synthetic    : {is_sample}")
        print(f"$INSUNITS    : {meta.insunits} ({meta.insunits_label})")
        print(f"$INSBASE     : {meta.insbase}")
        print(f"$EXTMIN/MAX  : {meta.extmin} / {meta.extmax}")
        print(f"Model entities scanned (filtered): {len(by_handle)}")
        print()
        print("APS vs ezdxf (target handles)")
        print("-" * 72)
        for row in comparison:
            print(f"Handle {row['handle']} ({row['layer_expected']})")
            print(f"  APS bounds (xy):  {row['aps_bounds_xy']}  [{row['aps_note']}]")
            if row["ezdxf_found"]:
                print(
                    f"  ezdxf bounds (xy): {row['ezdxf_bounds_xy']}  "
                    f"center={row['ezdxf_center_xy']}  "
                    f"w={row['ezdxf_width']} h={row['ezdxf_height']}  "
                    f"type={row['ezdxf_dxftype']} layer={row['ezdxf_layer']}"
                )
                print(f"  distinct from APS sheet collapse: {row['distinct_from_aps_sheet']}")
            else:
                print("  ezdxf: HANDLE NOT FOUND in modelspace")
            print()
        print("Column distinctness (96080E7, 96080E8, 960BBDD)")
        print(json.dumps(distinct, indent=2))
        print()
        print("VERDICT:", verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
