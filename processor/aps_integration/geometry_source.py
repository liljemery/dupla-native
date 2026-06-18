"""
Geometry-accurate extraction via Design Automation (AutoCAD core engine).

Model Derivative only returns object *properties*; a plain LINE or a segment in
the legend has no "Length" property, so it cannot be measured. The DuplaExtractor
Design Automation plugin runs inside AutoCAD in the cloud and reads true geometry
(Polyline.Length / Area, Line.Length, vertices) and excludes the legend / title
block. This module converts that plugin's JSON into the same ``cad_facts`` shape
``processors.json_processor`` produces, so the rest of the pipeline measures real
segments without any other change.

Enable (off by default — the working pipeline keeps using Model Derivative):
    DUPLA_USE_DA_GEOMETRY=1        # run DA and feed its geometry into cad_facts
    DUPLA_DA_REPLACE_GEOMETRY=1    # (default 1 when DA on) replace MD geometry_hints
                                   #   with DA-measured geometry to avoid double count

Requires: APS Design Automation entitlement, the DuplaExtractor AppBundle +
Activity deployed once (``python -m aps_integration.da_manager``), and the plugin
rebuilt from the updated Commands.cs.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("dupla.geometry_source")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _num(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n == n else None  # drop NaN


def _da_to_facts(da: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    """Convert DuplaExtractor JSON to (geometry_hints, blocks, texts).

    Tolerates both the new arrays (Lines/Arcs/Circles/Texts) and the original
    plugin output (Blocks/Polylines only).
    """
    hints: list[dict] = []
    blocks: list[dict] = []
    texts: list[dict] = []

    for pl in da.get("Polylines", []) or []:
        hints.append({
            "layer": str(pl.get("Layer", "")), "entity_type": "polyline",
            "name": "", "handle": str(pl.get("Handle", "")),
            "length": _num(pl.get("Length")),
            "area": _num(pl.get("Area")) if pl.get("Closed") else None,
            "radius": None, "bbox": {},
            # Preserve vertices so the GeometryMerger can collapse double-lines.
            "vertices": pl.get("Vertices") or [],
            "closed": bool(pl.get("Closed")),
        })
    for ln in da.get("Lines", []) or []:
        hints.append({
            "layer": str(ln.get("Layer", "")), "entity_type": "line",
            "name": "", "handle": str(ln.get("Handle", "")),
            "length": _num(ln.get("Length")), "area": None, "radius": None, "bbox": {},
            # Preserve endpoints for double-line collapse.
            "start": ln.get("Start"), "end": ln.get("End"),
        })
    for arc in da.get("Arcs", []) or []:
        hints.append({
            "layer": str(arc.get("Layer", "")), "entity_type": "arc",
            "name": "", "handle": str(arc.get("Handle", "")),
            "length": _num(arc.get("Length")), "area": None,
            "radius": _num(arc.get("Radius")), "bbox": {},
        })
    for circ in da.get("Circles", []) or []:
        hints.append({
            "layer": str(circ.get("Layer", "")), "entity_type": "circle",
            "name": "", "handle": str(circ.get("Handle", "")),
            "length": None, "area": None, "radius": _num(circ.get("Radius")), "bbox": {},
        })
    for blk in da.get("Blocks", []) or []:
        blocks.append({
            "layer": str(blk.get("Layer", "")), "entity_type": "block reference",
            "handle": str(blk.get("Handle", "")), "block_name": str(blk.get("Name", "")),
            "bbox": {},
        })
    for txt in da.get("Texts", []) or []:
        texts.append({
            "layer": str(txt.get("Layer", "")), "entity_type": "text",
            "handle": str(txt.get("Handle", "")), "content": str(txt.get("Content", "")),
            "bbox": {},
        })

    return hints, blocks, texts


def enrich_cad_facts_with_da(cad_facts: dict[str, Any], dwg_paths: list[str]) -> bool:
    """Run DA over the given DWGs and fold measured geometry into ``cad_facts``.

    Returns True when DA geometry was applied. Any failure is swallowed by the
    caller so the Model Derivative result is kept. Lengths are scale-normalised
    with the same heuristic json_processor uses (DWGs are often in millimetres).
    """
    from aps_integration.da_manager import run_da_extraction
    from processors.json_processor import _infer_global_scale

    all_hints: list[dict] = []
    all_blocks: list[dict] = []
    all_texts: list[dict] = []
    for path in dwg_paths:
        try:
            da = run_da_extraction(path)
        except Exception:
            logger.warning("DA extraction failed for %s — skipping", path, exc_info=True)
            continue
        hints, blocks, texts = _da_to_facts(da)
        all_hints += hints
        all_blocks += blocks
        all_texts += texts

    if not all_hints and not all_blocks:
        logger.info("DA enrichment produced no geometry; keeping Model Derivative facts")
        return False

    scale = _infer_global_scale([], all_hints)
    if scale != 1.0:
        logger.info("DA geometry scale factor inferred: %.0f (units -> metres)", scale)
        for h in all_hints:
            if h.get("length") is not None:
                h["length"] /= scale
            if h.get("area") is not None:
                h["area"] /= scale * scale
            if h.get("radius") is not None:
                h["radius"] /= scale

    # GeometryMerger (P2.7): collapse double-line walls before the geometry is
    # measured downstream. Coordinates from DA make this exact. Off via
    # DUPLA_GEOMETRY_MERGE=0.
    if _env_bool("DUPLA_GEOMETRY_MERGE", True):
        try:
            from core.geometry_merger import merge_geometry_hints

            all_hints, merge_stats = merge_geometry_hints(all_hints)
            if merge_stats.get("applied"):
                logger.info(
                    "GeometryMerger: %d lines -> %d groups, collapsed %d segments, "
                    "removed %.2f m of double-count",
                    merge_stats.get("input_lines", 0),
                    merge_stats.get("groups", 0),
                    merge_stats.get("collapsed_segments", 0),
                    merge_stats.get("removed_length_m", 0.0),
                )
                cad_facts["geometry_merge_stats"] = merge_stats
        except Exception:
            logger.warning("GeometryMerger failed; keeping raw DA geometry", exc_info=True)

    cf = cad_facts.setdefault("cad_facts", {})
    if _env_bool("DUPLA_DA_REPLACE_GEOMETRY", True):
        cf["geometry_hints"] = all_hints
    else:
        cf.setdefault("geometry_hints", []).extend(all_hints)
    if all_blocks:
        cf.setdefault("blocks", []).extend(all_blocks)
    if all_texts:
        cf.setdefault("texts", []).extend(all_texts)
    cad_facts["da_geometry_used"] = True
    logger.info(
        "DA geometry applied: %d segments, %d blocks, %d texts from %d DWG(s)",
        len(all_hints), len(all_blocks), len(all_texts), len(dwg_paths),
    )
    return True
