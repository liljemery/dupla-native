#!/usr/bin/env python
"""PHASE 2 — Common-frame alignment for multi-discipline coordination.

Runs on NOW-CLEAN data (Phase 1 / data sanitation already done: every discipline
in meters, sane outlines, strays removed) and resolves, per discipline, a single
transform INTO the reference frame so cross-discipline clash is geometrically valid.

Layered resolution, reported per discipline:

  Layer A — ALREADY-ALIGNED CHECK
      Cleaned outline bbox + centroid coincide with the reference within a small
      tolerance (meters) -> identity transform.

  Layer B — SHARED-ANCHOR REGISTRATION (automatic)
      Extract a shared physical anchor readable by ezdxf:
        1. structural axis grid (layers EJE*/GRID/AXIS + grid-bubble labels),
        2. else the building outline polygon / perimeter.
      Match anchors across disciplines -> control points -> SVD/RANSAC
      rigid+uniform-scale fit. Residual reported in meters.

  Layer C — MANUAL CONTROL POINTS (persisted fallback)
      Read a per-project alignment manifest JSON
        {discipline: [{"model_xy": [x, y], "ref_xy": [x, y]}, ...]}
      fit from those, and PERSIST the resulting transform back into the manifest
      so it is never recomputed. If a discipline cannot be aligned by A or B and
      no manifest entry exists, it is marked ``needs_manual_control_points`` — no
      transform is fabricated.

Hard constraints honored here:
  * HS (combined AS-BUILT, flagged) is EXCLUDED from establishing the common frame
    and reported separately as ``pending_reselection``. It never contaminates the fit.
  * The deterministic hash-stride separation in
    ``coordination.core.nasas_paths.file_translation_mm`` is intentionally NOT used.
    That offset fights true alignment; the common frame REPLACES it. See
    ``HASH_OFFSET_DISABLED`` and ``frame_provenance()``.
  * Reference discipline is ARQ (fallback EST). All transforms map INTO that frame.
  * Data is meters now, so expect scale ~= 1.0. A fit whose scale is far from 1.0 is
    flagged as a red flag (residual unit error or wrong anchor pairing).

Promoted math (reused as-is from proven POCs):
  * ``fit_similarity`` / ``fit_affine`` (SVD) — dxf_aps_alignment_poc.py:181-233
  * ``robust_similarity_fit`` (RANSAC)        — dxf_aps_alignment_poc.py:240-325
  * ``similarity_transform``                  — stage_data_sanitation.py:252-274
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

try:  # ezdxf only needed for Layer B grid extraction; degrade gracefully without it.
    import ezdxf
except Exception:  # pragma: no cover - environment without ezdxf
    ezdxf = None  # type: ignore[assignment]


# --------------------------------------------------------------------------------------
# Constants / provenance
# --------------------------------------------------------------------------------------

#: Disciplines excluded from establishing the common frame (do NOT contaminate the fit).
DEFAULT_EXCLUDE = ("HS",)

#: Preferred reference order. All transforms map INTO this discipline's frame.
REFERENCE_PREFERENCE = ("ARQ", "EST")

GRID_LAYER_TOKENS = ("EJE", "GRID", "AXIS", "AXES", "RETICULA", "RETÍCULA")
OUTLINE_LAYER_TOKENS = ("WALL", "MURO", "A-WALL", "COLUMN", "COLUMNA", "ESTRUCT", "LOSA", "SLAB", "BORDE")

#: The nasas hash-stride per-file offset is REPLACED by the common frame; never applied here.
HASH_OFFSET_DISABLED = True

#: Scale tolerance around 1.0. Meters-in / meters-out should need no scaling.
SCALE_OK_LOW = 0.5
SCALE_OK_HIGH = 2.0

PROVENANCE = {
    "module": "motor/coordination/core/frame_alignment.py",
    "phase": "2_common_frame_alignment",
    "input_unit": "model_meters_sanitized",
    "hash_offset_disabled": HASH_OFFSET_DISABLED,
    "hash_offset_note": (
        "coordination.core.nasas_paths.file_translation_mm() is NOT applied. Its "
        "deterministic per-file hash stride separates drawings and fights true "
        "alignment; the common frame replaces it."
    ),
    "promoted_from": {
        "fit_similarity/fit_affine": "dxf_aps_alignment_poc.py:181-233",
        "robust_similarity_fit": "dxf_aps_alignment_poc.py:240-325",
        "similarity_transform": "stage_data_sanitation.py:252-274",
    },
}


def frame_provenance() -> dict[str, Any]:
    """Return provenance describing inputs, promoted math and the disabled hash offset."""
    return dict(PROVENANCE)


# --------------------------------------------------------------------------------------
# Promoted math — SVD similarity / affine (dxf_aps_alignment_poc.py:181-233)
# --------------------------------------------------------------------------------------

def fit_similarity(model: np.ndarray, sheet: np.ndarray, flip_y: bool) -> dict[str, Any] | None:
    """Closed-form Umeyama similarity (rotation + uniform scale + translation) via SVD.

    Maps ``model`` -> ``sheet``. ``flip_y`` lets a mirrored handedness be recovered.
    Promoted verbatim from dxf_aps_alignment_poc.py:181-216 (residuals are in the
    units of ``sheet``; here both inputs are meters, so residuals are meters).
    """
    if len(model) < 2:
        return None
    p = model.copy()
    if flip_y:
        p[:, 1] *= -1.0
    p_mean = p.mean(axis=0)
    q_mean = sheet.mean(axis=0)
    pc = p - p_mean
    qc = sheet - q_mean
    denom = float((pc * pc).sum())
    if denom <= 1e-12:
        return None
    h = pc.T @ qc
    u, s, vt = np.linalg.svd(h)
    r = vt.T @ u.T
    if np.linalg.det(r) < 0:
        vt[-1, :] *= -1.0
        r = vt.T @ u.T
    scale = float(s.sum() / denom)
    t = q_mean - scale * (r @ p_mean)
    pred = (scale * (r @ p.T)).T + t
    residuals = np.linalg.norm(pred - sheet, axis=1)
    angle = math.degrees(math.atan2(float(r[1, 0]), float(r[0, 0])))
    f = np.array([[1.0, 0.0], [0.0, -1.0 if flip_y else 1.0]])
    matrix = scale * r @ f
    return {
        "kind": "similarity",
        "flip_y": flip_y,
        "scale": scale,
        "rotation_deg": angle,
        "translation": t,
        "matrix": matrix,
        "pred": pred,
        "residuals": residuals,
    }


def fit_affine(model: np.ndarray, sheet: np.ndarray) -> dict[str, Any] | None:
    """Least-squares full affine. Promoted verbatim from dxf_aps_alignment_poc.py:219-233."""
    if len(model) < 3:
        return None
    x = np.column_stack([model, np.ones(len(model))])
    coeff, *_ = np.linalg.lstsq(x, sheet, rcond=None)
    pred = x @ coeff
    residuals = np.linalg.norm(pred - sheet, axis=1)
    a = coeff[:2, :].T
    return {
        "kind": "affine",
        "matrix": a,
        "translation": coeff[2, :],
        "pred": pred,
        "residuals": residuals,
    }


def similarity_transform(src: np.ndarray, dst: np.ndarray) -> dict[str, Any]:
    """SVD similarity returning a serializable transform. Promoted from
    stage_data_sanitation.py:252-274 (residuals in meters when src/dst are meters)."""
    sm = src.mean(axis=0)
    dm = dst.mean(axis=0)
    sc = src - sm
    dc = dst - dm
    h = sc.T @ dc
    u, s, vt = np.linalg.svd(h)
    r = vt.T @ u.T
    if np.linalg.det(r) < 0:
        vt[-1, :] *= -1
        r = vt.T @ u.T
    scale = float(s.sum() / max(float((sc * sc).sum()), 1e-12))
    t = dm - scale * (r @ sm)
    pred = (scale * (r @ src.T)).T + t
    res = np.linalg.norm(pred - dst, axis=1)
    return {
        "scale": scale,
        "rotation_deg": math.degrees(math.atan2(float(r[1, 0]), float(r[0, 0]))),
        "translation": [float(t[0]), float(t[1])],
        "matrix": [[float(scale * r[0, 0]), float(scale * r[0, 1])],
                   [float(scale * r[1, 0]), float(scale * r[1, 1])]],
        "rms_m": float(np.sqrt(np.mean(res ** 2))),
        "max_m": float(np.max(res)),
        "point_count": int(len(src)),
    }


# --------------------------------------------------------------------------------------
# Promoted math — RANSAC robust fit (dxf_aps_alignment_poc.py:240-325)
# --------------------------------------------------------------------------------------

def robust_similarity_fit(
    src: np.ndarray,
    dst: np.ndarray,
    thresholds_m: tuple[float, ...] = (0.25, 0.50, 1.00, 2.00),
) -> dict[str, Any]:
    """RANSAC similarity fit adapted from dxf_aps_alignment_poc.py:240-325.

    Both ``src`` and ``dst`` are in meters here (vs the POC's model->sheet units), so
    the residual threshold is applied directly in meters with no scale division.
    Two-point minimal samples, ``flip_y`` tried both ways, best inlier set re-fit.
    """
    n = len(src)
    if n < 3 or len(dst) != n:
        return {"status": "insufficient", "n_pairs": n}
    model = np.asarray(src, dtype=float)
    sheet = np.asarray(dst, dtype=float)

    rng = random.Random(42)
    best = None
    max_trials = min(500, max(100, n * 4))
    for _ in range(max_trials):
        idx = rng.sample(range(n), 2)
        m2 = model[idx]
        s2 = sheet[idx]
        for flip in (False, True):
            fit = fit_similarity(m2, s2, flip)
            if not fit or fit["scale"] <= 0.001 or fit["scale"] >= 10.0:
                continue
            pred_all = (fit["matrix"] @ model.T).T + fit["translation"]
            residual_m = np.linalg.norm(pred_all - sheet, axis=1)
            for threshold_m in thresholds_m:
                mask = residual_m <= threshold_m
                count = int(mask.sum())
                if count < 3:
                    continue
                if np.ptp(model[mask, 0]) < 1.0 and np.ptp(model[mask, 1]) < 1.0:
                    continue
                rms_m = float(np.sqrt(np.mean(residual_m[mask] ** 2)))
                score = (count, -rms_m)
                if best is None or score > best["score"]:
                    best = {"score": score, "mask": mask, "threshold_m": threshold_m}

    if best is None:
        candidates = [f for f in (fit_similarity(model, sheet, False), fit_similarity(model, sheet, True)) if f]
        if not candidates:
            return {"status": "insufficient", "n_pairs": n}
        inlier_mask = np.ones(n, dtype=bool)
        threshold_m = None
    else:
        inlier_mask = best["mask"]
        threshold_m = best["threshold_m"]

    model_i = model[inlier_mask]
    sheet_i = sheet[inlier_mask]
    final_candidates = [f for f in (fit_similarity(model_i, sheet_i, False), fit_similarity(model_i, sheet_i, True)) if f]
    if not final_candidates:
        return {"status": "degenerate", "n_pairs": n}
    final = min(final_candidates, key=lambda f: float(np.sqrt(np.mean(f["residuals"] ** 2))))
    if final["scale"] <= 0.001 or final["scale"] >= 10.0:
        return {"status": "degenerate", "n_pairs": n, "n_inliers": int(inlier_mask.sum())}
    rms_m = float(np.sqrt(np.mean(final["residuals"] ** 2)))
    max_m = float(np.max(final["residuals"]))
    return {
        "status": "ok",
        "n_pairs": n,
        "n_inliers": int(inlier_mask.sum()),
        "n_outliers": int(n - inlier_mask.sum()),
        "ransac_threshold_m": threshold_m,
        "scale": float(final["scale"]),
        "rotation_deg": float(final["rotation_deg"]),
        "flip_y": bool(final["flip_y"]),
        "translation": [float(final["translation"][0]), float(final["translation"][1])],
        "matrix": [[float(final["matrix"][0, 0]), float(final["matrix"][0, 1])],
                   [float(final["matrix"][1, 0]), float(final["matrix"][1, 1])]],
        "rms_m": rms_m,
        "max_m": max_m,
    }


# --------------------------------------------------------------------------------------
# bbox helpers
# --------------------------------------------------------------------------------------

def bbox_size(b: list[float]) -> tuple[float, float]:
    return max(b[2] - b[0], 0.0), max(b[3] - b[1], 0.0)


def bbox_center(b: list[float]) -> np.ndarray:
    return np.array([(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0], dtype=float)


def bbox_corners(b: list[float]) -> np.ndarray:
    return np.array(
        [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]],
        dtype=float,
    )


def transform_to_serializable(tr: dict[str, Any]) -> dict[str, Any]:
    """Normalize an internal fit dict into the persisted transform schema."""
    matrix = tr.get("matrix")
    if isinstance(matrix, np.ndarray):
        matrix = [[float(matrix[0, 0]), float(matrix[0, 1])],
                  [float(matrix[1, 0]), float(matrix[1, 1])]]
    translation = tr.get("translation", [0.0, 0.0])
    if isinstance(translation, np.ndarray):
        translation = [float(translation[0]), float(translation[1])]
    return {
        "scale": float(tr.get("scale", 1.0)),
        "rotation_deg": float(tr.get("rotation_deg", 0.0)),
        "flip_y": bool(tr.get("flip_y", False)),
        "translation": [float(translation[0]), float(translation[1])],
        "matrix": matrix,
    }


def apply_transform(points: np.ndarray, tr: dict[str, Any]) -> np.ndarray:
    """Apply a serialized transform: common_xy_m = matrix @ p + translation."""
    matrix = tr.get("matrix")
    if matrix is None:
        scale = float(tr.get("scale", 1.0))
        rad = math.radians(float(tr.get("rotation_deg", 0.0)))
        c, s = math.cos(rad), math.sin(rad)
        fy = -1.0 if tr.get("flip_y") else 1.0
        m = scale * np.array([[c, -s], [s, c]]) @ np.array([[1.0, 0.0], [0.0, fy]])
    else:
        m = np.asarray(matrix, dtype=float)
    t = np.asarray(tr.get("translation", [0.0, 0.0]), dtype=float)
    return (m @ np.asarray(points, dtype=float).T).T + t


def scale_flag(scale: float) -> str:
    if SCALE_OK_LOW <= scale <= SCALE_OK_HIGH:
        return "ok"
    return "RED_FLAG_scale_far_from_1"


# --------------------------------------------------------------------------------------
# Discipline features (robust outline + centroid, strays rejected)
# --------------------------------------------------------------------------------------

@dataclass
class DisciplineFeatures:
    discipline: str
    dxf_path: str | None
    physical_count: int
    outline_bounds_m: list[float]
    outline_size_m: list[float]
    centroid_m: list[float]
    excluded: bool = False
    exclude_reason: str | None = None
    notes: list[str] = field(default_factory=list)


def _physical_elements(geom: dict) -> list[dict]:
    return [
        e for e in geom.get("elements", [])
        if e.get("physical")
        and e.get("geometry_quality") in {"good", "coarse"}
        and e.get("model_bounds")
        and e.get("model_center")
    ]


def robust_features(
    discipline: str,
    geom: dict,
    percentile_low: float = 5.0,
    percentile_high: float = 95.0,
) -> DisciplineFeatures:
    """Compute a stray-rejecting outline + centroid in meters.

    The prior sanitation ``cleanup`` block can be degenerate on PDF-traced or
    mis-unit drawings, so the outline is recomputed here from the percentile window
    of physical element centers (the robust building core) rather than trusted blindly.
    """
    elems = _physical_elements(geom)
    notes: list[str] = []
    if not elems:
        ref = geom.get("model_reference_bounds") or [0.0, 0.0, 1.0, 1.0]
        return DisciplineFeatures(
            discipline=discipline,
            dxf_path=geom.get("dxf_path"),
            physical_count=0,
            outline_bounds_m=[float(v) for v in ref],
            outline_size_m=list(bbox_size([float(v) for v in ref])),
            centroid_m=list(bbox_center([float(v) for v in ref])),
            notes=["no physical good/coarse elements"],
        )
    centers = np.array([e["model_center"] for e in elems], dtype=float)
    lo = np.percentile(centers, percentile_low, axis=0)
    hi = np.percentile(centers, percentile_high, axis=0)
    span = np.maximum(hi - lo, 1e-9)
    pad = span * 0.20
    min_xy, max_xy = lo - pad, hi + pad
    in_window = [
        e for e, c in zip(elems, centers)
        if np.all(c >= min_xy) and np.all(c <= max_xy)
    ]
    if not in_window:
        in_window = elems
    bounds = np.array([e["model_bounds"] for e in in_window], dtype=float)
    outline = [
        float(bounds[:, 0].min()), float(bounds[:, 1].min()),
        float(bounds[:, 2].max()), float(bounds[:, 3].max()),
    ]
    win_centers = np.array([e["model_center"] for e in in_window], dtype=float)
    centroid = win_centers.mean(axis=0)
    w, h = bbox_size(outline)
    if max(w, h) < 5.0:
        notes.append(
            f"robust outline only {w:.2f}x{h:.2f} m — too small for a building "
            "footprint (likely residual unit error or PDF-traced source)"
        )
    return DisciplineFeatures(
        discipline=discipline,
        dxf_path=geom.get("dxf_path"),
        physical_count=len(elems),
        outline_bounds_m=outline,
        outline_size_m=[w, h],
        centroid_m=[float(centroid[0]), float(centroid[1])],
        notes=notes,
    )


def load_features(
    work_dir: Path,
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE,
) -> tuple[dict[str, DisciplineFeatures], dict[str, DisciplineFeatures]]:
    """Load sanitized geometry into features. Returns (fit_features, excluded_features)."""
    sanitized_dir = work_dir / "sanitized_geometry"
    fit: dict[str, DisciplineFeatures] = {}
    excluded: dict[str, DisciplineFeatures] = {}
    for path in sorted(sanitized_dir.glob("*.sanitized.geometry.json")):
        disc = path.name.split(".")[0]
        if disc in exclude:
            # Do NOT contaminate the fit. Summarize cheaply without loading the (huge) file.
            excluded[disc] = _excluded_summary(disc, work_dir, path)
            continue
        geom = json.loads(path.read_text(encoding="utf-8"))
        fit[disc] = robust_features(disc, geom)
    return fit, excluded


def _excluded_summary(disc: str, work_dir: Path, sanitized_path: Path) -> DisciplineFeatures:
    """Summarize an excluded discipline (e.g. HS) from the sanitation report, avoiding
    a full load of a multi-hundred-MB sanitized file."""
    bounds = [0.0, 0.0, 1.0, 1.0]
    centroid = [0.0, 0.0]
    notes = ["excluded from common-frame fit (must not contaminate alignment)"]
    report = work_dir / "sanitation_report.json"
    if report.is_file():
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
            row = (data.get("disciplines") or {}).get(disc) or {}
            cleanup = row.get("cleanup") or {}
            if cleanup.get("cleaned_outline_bounds_m"):
                bounds = [float(v) for v in cleanup["cleaned_outline_bounds_m"]]
            if cleanup.get("cleaned_centroid_m"):
                centroid = [float(v) for v in cleanup["cleaned_centroid_m"]]
            flags = ((data.get("hs_finding") or {}).get("flags")) if disc == "HS" else None
            if flags:
                notes.append("flags=" + ",".join(flags))
            phys = row.get("physical_count")
            if phys is not None:
                notes.append(f"physical_count={phys}")
        except Exception:
            pass
    return DisciplineFeatures(
        discipline=disc,
        dxf_path=None,
        physical_count=0,
        outline_bounds_m=bounds,
        outline_size_m=list(bbox_size(bounds)),
        centroid_m=centroid,
        excluded=True,
        exclude_reason="pending_reselection",
        notes=notes,
    )


def choose_reference(features: dict[str, DisciplineFeatures], requested: str | None) -> str:
    if requested and requested in features:
        return requested
    for pref in REFERENCE_PREFERENCE:
        if pref in features:
            return pref
    return sorted(features)[0]


# --------------------------------------------------------------------------------------
# Layer A — already-aligned check
# --------------------------------------------------------------------------------------

def pair_discrepancy(a: DisciplineFeatures, b: DisciplineFeatures) -> dict[str, Any]:
    ca, cb = np.array(a.centroid_m), np.array(b.centroid_m)
    corner_delta = np.linalg.norm(bbox_corners(a.outline_bounds_m) - bbox_corners(b.outline_bounds_m), axis=1)
    return {
        "centroid_delta_m": float(np.linalg.norm(ca - cb)),
        "corner_rms_m": float(np.sqrt(np.mean(corner_delta ** 2))),
        "corner_max_m": float(np.max(corner_delta)),
    }


def layer_a_pairs(features: dict[str, DisciplineFeatures], tol_m: float) -> dict[str, Any]:
    discs = sorted(features)
    pairs: dict[str, Any] = {}
    worst = 0.0
    for i, a in enumerate(discs):
        for b in discs[i + 1:]:
            d = pair_discrepancy(features[a], features[b])
            metric = max(d["centroid_delta_m"], d["corner_rms_m"])
            d["status"] = "ok" if metric <= tol_m else "mismatch"
            pairs[f"{a}__{b}"] = d
            worst = max(worst, metric)
    return {"pairs": pairs, "max_discrepancy_m": worst, "tolerance_m": tol_m}


def layer_a_transform(feat: DisciplineFeatures, ref: DisciplineFeatures, tol_m: float) -> dict[str, Any] | None:
    d = pair_discrepancy(feat, ref)
    if max(d["centroid_delta_m"], d["corner_rms_m"]) <= tol_m:
        return {
            "layer": "A",
            "method": "identity_already_aligned",
            "scale": 1.0,
            "rotation_deg": 0.0,
            "flip_y": False,
            "translation": [0.0, 0.0],
            "matrix": [[1.0, 0.0], [0.0, 1.0]],
            "residual_rms_m": d["corner_rms_m"],
            "residual_max_m": d["corner_max_m"],
            "n_control_points": 4,
            "status": "ok",
        }
    return None


# --------------------------------------------------------------------------------------
# Layer B — shared-anchor registration
# --------------------------------------------------------------------------------------

def _line_angle_deg(p1: np.ndarray, p2: np.ndarray) -> float:
    return math.degrees(math.atan2(float(p2[1] - p1[1]), float(p2[0] - p1[0])))


def _cluster(vals: list[float], tol: float) -> list[float]:
    vals = sorted(vals)
    groups: list[list[float]] = []
    for v in vals:
        if not groups or abs(statistics.mean(groups[-1]) - v) > tol:
            groups.append([v])
        else:
            groups[-1].append(v)
    return [float(statistics.mean(g)) for g in groups]


def extract_grid_anchor(dxf_path: str | None, factor_to_meters: float, cluster_tol_m: float = 0.25) -> dict[str, Any]:
    """Extract a structural-axis-grid anchor (intersections + bubble labels) in meters."""
    out: dict[str, Any] = {"available": False, "labels": {}, "points": np.zeros((0, 2)), "grid_x": [], "grid_y": []}
    if not dxf_path or ezdxf is None or not Path(dxf_path).is_file():
        return out
    try:
        doc = ezdxf.readfile(dxf_path)
    except Exception:
        return out
    lines: list[dict[str, Any]] = []
    labels: dict[str, np.ndarray] = {}
    for entity in doc.modelspace():
        upper = str(entity.dxf.layer).upper()
        if not any(tok in upper for tok in GRID_LAYER_TOKENS):
            continue
        et = entity.dxftype()
        if et == "LINE":
            s, e = entity.dxf.start, entity.dxf.end
            p1 = np.array([float(s.x) * factor_to_meters, float(s.y) * factor_to_meters])
            p2 = np.array([float(e.x) * factor_to_meters, float(e.y) * factor_to_meters])
            if float(np.linalg.norm(p2 - p1)) >= 1.0:
                lines.append({"p1": p1, "p2": p2, "angle": _line_angle_deg(p1, p2)})
        elif et in {"TEXT", "MTEXT"}:
            text = str(getattr(entity, "text", "") or "").strip()
            ins = entity.dxf.get("insert", None)
            if text and ins is not None and text not in labels:
                labels[text] = np.array([float(ins.x) * factor_to_meters, float(ins.y) * factor_to_meters])
    vertical, horizontal = [], []
    for ln in lines:
        a = abs((ln["angle"] + 180.0) % 180.0)
        if abs(a - 90.0) <= 10.0:
            vertical.append(float((ln["p1"][0] + ln["p2"][0]) / 2.0))
        elif min(abs(a), abs(a - 180.0)) <= 10.0:
            horizontal.append(float((ln["p1"][1] + ln["p2"][1]) / 2.0))
    xs = _cluster(vertical, cluster_tol_m)
    ys = _cluster(horizontal, cluster_tol_m)
    points = np.array([[x, y] for x in xs for y in ys], dtype=float) if xs and ys else np.zeros((0, 2))
    out.update({
        "available": (len(points) >= 4) or (len(labels) >= 2),
        "labels": labels,
        "points": points,
        "grid_x": xs,
        "grid_y": ys,
        "line_count": len(lines),
        "label_count": len(labels),
        "intersection_count": int(len(points)),
    })
    return out


def _fit_from_points(src: np.ndarray, dst: np.ndarray) -> dict[str, Any] | None:
    """Pick the best similarity fit: RANSAC when enough points, else best variant."""
    if len(src) >= 4:
        ransac = robust_similarity_fit(src, dst)
        if ransac.get("status") == "ok":
            return ransac
    candidates = [f for f in (fit_similarity(src, dst, False), fit_similarity(src, dst, True)) if f]
    if not candidates:
        return None
    best = min(candidates, key=lambda f: float(np.sqrt(np.mean(f["residuals"] ** 2))))
    return {
        "status": "ok",
        "scale": float(best["scale"]),
        "rotation_deg": float(best["rotation_deg"]),
        "flip_y": bool(best["flip_y"]),
        "translation": [float(best["translation"][0]), float(best["translation"][1])],
        "matrix": [[float(best["matrix"][0, 0]), float(best["matrix"][0, 1])],
                   [float(best["matrix"][1, 0]), float(best["matrix"][1, 1])]],
        "rms_m": float(np.sqrt(np.mean(best["residuals"] ** 2))),
        "max_m": float(np.max(best["residuals"])),
        "n_pairs": int(len(src)),
    }


def layer_b_transform(
    feat: DisciplineFeatures,
    ref: DisciplineFeatures,
    ref_grid: dict[str, Any],
    disc_grid: dict[str, Any],
    tol_m: float,
) -> dict[str, Any]:
    """Try grid-label, then grid-intersection, then outline-polygon registration."""
    attempts: list[dict[str, Any]] = []

    # B.1 — grid bubbles matched by identical label text.
    shared = sorted(set(ref_grid.get("labels", {})) & set(disc_grid.get("labels", {})))
    if len(shared) >= 2:
        src = np.array([disc_grid["labels"][k] for k in shared], dtype=float)
        dst = np.array([ref_grid["labels"][k] for k in shared], dtype=float)
        fit = _fit_from_points(src, dst)
        if fit and fit.get("status") == "ok":
            attempts.append({**fit, "anchor": "grid_labels", "n_control_points": len(shared)})

    # B.2 — grid intersections matched by sorted pattern (diagnostic; weak ordering).
    rp, dp = ref_grid.get("points"), disc_grid.get("points")
    if isinstance(rp, np.ndarray) and isinstance(dp, np.ndarray) and len(rp) >= 4 and len(dp) >= 4:
        n = min(len(rp), len(dp), 20)
        src = dp[np.lexsort((dp[:, 1], dp[:, 0]))][:n]
        dst = rp[np.lexsort((rp[:, 1], rp[:, 0]))][:n]
        fit = _fit_from_points(src, dst)
        if fit and fit.get("status") == "ok":
            attempts.append({**fit, "anchor": "grid_intersections", "n_control_points": int(n)})

    # B.3 — building outline polygon corners with cyclic/reversed correspondence.
    ref_corners = bbox_corners(ref.outline_bounds_m)
    src_corners = bbox_corners(feat.outline_bounds_m)
    variants = []
    for pts in (src_corners, src_corners[::-1]):
        for shift in range(4):
            variants.append(np.roll(pts, shift, axis=0))
    fits = [fit_similarity(v, ref_corners, flip) for v in variants for flip in (False, True)]
    fits = [f for f in fits if f]
    if fits:
        best = min(fits, key=lambda f: float(np.sqrt(np.mean(f["residuals"] ** 2))))
        attempts.append({
            "status": "ok",
            "anchor": "outline_polygon",
            "scale": float(best["scale"]),
            "rotation_deg": float(best["rotation_deg"]),
            "flip_y": bool(best["flip_y"]),
            "translation": [float(best["translation"][0]), float(best["translation"][1])],
            "matrix": [[float(best["matrix"][0, 0]), float(best["matrix"][0, 1])],
                       [float(best["matrix"][1, 0]), float(best["matrix"][1, 1])]],
            "rms_m": float(np.sqrt(np.mean(best["residuals"] ** 2))),
            "max_m": float(np.max(best["residuals"])),
            "n_control_points": 4,
        })

    if not attempts:
        return {"layer": "B", "status": "failed", "method": "no_anchor", "reason": "no shared anchor extractable"}

    # Prefer accepted (residual + scale ok); else return best attempt as high_residual.
    def accepted(a: dict[str, Any]) -> bool:
        return a["rms_m"] <= tol_m and SCALE_OK_LOW <= a["scale"] <= SCALE_OK_HIGH

    good = [a for a in attempts if accepted(a)]
    chosen = min(good, key=lambda a: a["rms_m"]) if good else min(attempts, key=lambda a: a["rms_m"])
    status = "ok" if accepted(chosen) else "high_residual"
    return {
        "layer": "B",
        "method": f"shared_anchor_{chosen['anchor']}",
        "anchor": chosen["anchor"],
        "scale": chosen["scale"],
        "rotation_deg": chosen["rotation_deg"],
        "flip_y": chosen["flip_y"],
        "translation": chosen["translation"],
        "matrix": chosen["matrix"],
        "residual_rms_m": chosen["rms_m"],
        "residual_max_m": chosen["max_m"],
        "n_control_points": chosen["n_control_points"],
        "scale_flag": scale_flag(chosen["scale"]),
        "status": status,
    }


# --------------------------------------------------------------------------------------
# Layer C — manual control points (persisted)
# --------------------------------------------------------------------------------------

def read_manifest(path: Path | None) -> dict[str, Any]:
    if not path or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _control_points_for(manifest: dict[str, Any], disc: str) -> list[dict[str, Any]] | None:
    cp = manifest.get("control_points") or manifest
    rows = cp.get(disc) if isinstance(cp, dict) else None
    if isinstance(rows, list) and rows:
        return rows
    return None


def layer_c_transform(
    manifest: dict[str, Any],
    manifest_path: Path | None,
    disc: str,
    tol_m: float,
) -> dict[str, Any] | None:
    """Resolve a transform from manual control points and persist it in the manifest.

    Persisted transforms (``resolved_transforms[disc]``) are reused verbatim and never
    recomputed. Returns ``None`` when the manifest has nothing for this discipline.
    """
    resolved = (manifest.get("resolved_transforms") or {}).get(disc)
    if resolved:
        out = dict(resolved)
        out["layer"] = "C"
        out["method"] = "manual_control_points_persisted"
        out["status"] = out.get("status", "ok")
        return out

    rows = _control_points_for(manifest, disc)
    if not rows:
        return None
    try:
        src = np.array([r["model_xy"] for r in rows], dtype=float)
        dst = np.array([r["ref_xy"] for r in rows], dtype=float)
    except Exception:
        return None
    if len(src) < 2:
        return None
    fit = _fit_from_points(src, dst)
    if not fit or fit.get("status") != "ok":
        return {"layer": "C", "status": "failed", "method": "manual_control_points",
                "reason": "fit failed on provided control points", "n_control_points": int(len(src))}
    record = {
        "layer": "C",
        "method": "manual_control_points",
        "scale": fit["scale"],
        "rotation_deg": fit["rotation_deg"],
        "flip_y": fit["flip_y"],
        "translation": fit["translation"],
        "matrix": fit["matrix"],
        "residual_rms_m": fit["rms_m"],
        "residual_max_m": fit["max_m"],
        "n_control_points": int(len(src)),
        "scale_flag": scale_flag(fit["scale"]),
        "status": "ok" if fit["rms_m"] <= tol_m else "high_residual",
    }
    _persist_resolved(manifest, manifest_path, disc, record)
    record["method"] = "manual_control_points_persisted"
    return record


def _persist_resolved(manifest: dict[str, Any], manifest_path: Path | None, disc: str, record: dict[str, Any]) -> None:
    if not manifest_path:
        return
    manifest.setdefault("resolved_transforms", {})
    manifest["resolved_transforms"][disc] = {
        "scale": record["scale"],
        "rotation_deg": record["rotation_deg"],
        "flip_y": record["flip_y"],
        "translation": record["translation"],
        "matrix": record["matrix"],
        "residual_rms_m": record["residual_rms_m"],
        "residual_max_m": record["residual_max_m"],
        "n_control_points": record["n_control_points"],
        "status": record["status"],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source": "frame_alignment.layer_c_transform",
    }
    try:
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------

def resolve_frame(
    work_dir: Path,
    reference: str | None = None,
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE,
    identity_tol_m: float = 2.0,
    anchor_tol_m: float = 1.0,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    features, excluded = load_features(work_dir, exclude=exclude)
    if not features:
        raise SystemExit(f"No sanitized geometry found under {work_dir / 'sanitized_geometry'}")
    ref_name = choose_reference(features, reference)
    ref_feat = features[ref_name]
    manifest = read_manifest(manifest_path)

    # Sanitized unit factors (for converting raw DXF grid coords -> meters in Layer B).
    factors = _unit_factors(work_dir)
    ref_grid = extract_grid_anchor(ref_feat.dxf_path, factors.get(ref_name, 1.0))

    pair_grid = layer_a_pairs(features, identity_tol_m)
    transforms: dict[str, Any] = {}

    for disc in sorted(features):
        feat = features[disc]
        if disc == ref_name:
            transforms[disc] = {
                "layer": "A", "method": "identity_reference", "scale": 1.0, "rotation_deg": 0.0,
                "flip_y": False, "translation": [0.0, 0.0], "matrix": [[1.0, 0.0], [0.0, 1.0]],
                "residual_rms_m": 0.0, "residual_max_m": 0.0, "n_control_points": 0,
                "status": "ok", "reference": True,
            }
            continue

        # Layer A
        a = layer_a_transform(feat, ref_feat, identity_tol_m)
        if a:
            transforms[disc] = a
            continue

        # Layer B
        disc_grid = extract_grid_anchor(feat.dxf_path, factors.get(disc, 1.0))
        b = layer_b_transform(feat, ref_feat, ref_grid, disc_grid, anchor_tol_m)
        if b.get("status") == "ok":
            transforms[disc] = b
            continue

        # Layer C
        c = layer_c_transform(manifest, manifest_path, disc, anchor_tol_m)
        if c and c.get("status") == "ok":
            transforms[disc] = c
            continue

        # Nothing succeeded: report best diagnostic without fabricating a usable transform.
        best_b = b if b.get("status") in {"high_residual", "ok"} else None
        transforms[disc] = {
            "layer": None,
            "method": "needs_manual_control_points",
            "status": "needs_manual_control_points",
            "message": (
                f"{disc} did not align by Layer A (outline/centroid off by "
                f"{pair_discrepancy(feat, ref_feat)['centroid_delta_m']:.1f} m) or Layer B "
                f"(best anchor residual "
                f"{(best_b or {}).get('residual_rms_m', float('nan')):.2f} m, scale "
                f"{(best_b or {}).get('scale', float('nan')):.3f}); no manifest control points. "
                "Provide --alignment-manifest control points."
            ),
            "diagnostic_layer_b": best_b,
            "feature_notes": feat.notes,
        }

    verdict, verdict_kind = _build_verdict(transforms, ref_name, excluded, anchor_tol_m)
    return {
        "checkpoint": "common_frame.json",
        "phase": "2_common_frame_alignment",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "unit": "model_meters_sanitized",
        "reference": ref_name,
        "excluded_from_frame": list(excluded),
        "identity_tolerance_m": identity_tol_m,
        "anchor_tolerance_m": anchor_tol_m,
        "verdict": verdict,
        "verdict_kind": verdict_kind,
        "transforms": transforms,
        "pending_reselection": {
            disc: {
                "status": "pending_reselection",
                "outline_size_m": ef.outline_size_m,
                "centroid_m": ef.centroid_m,
                "notes": ef.notes,
            }
            for disc, ef in excluded.items()
        },
        "layer_a_pair_discrepancies": pair_grid,
        "features": {
            disc: {
                "physical_count": f.physical_count,
                "outline_bounds_m": f.outline_bounds_m,
                "outline_size_m": f.outline_size_m,
                "centroid_m": f.centroid_m,
                "notes": f.notes,
            }
            for disc, f in features.items()
        },
        "provenance": frame_provenance(),
        "apply_as": "common_xy_m = matrix @ sanitized_xy_m + translation   (matrix = scale * R * flip)",
    }


def _unit_factors(work_dir: Path) -> dict[str, float]:
    """Per-discipline factor_to_meters already baked into sanitized coords (=1.0), and the
    raw->meters factor used to convert raw DXF grid coordinates in Layer B."""
    factors: dict[str, float] = {}
    sanitized_dir = work_dir / "sanitized_geometry"
    for path in sorted(sanitized_dir.glob("*.sanitized.geometry.json")):
        disc = path.name.split(".")[0]
        try:
            # Stream just the unit_sanitation block cheaply for large files.
            data = json.loads(path.read_text(encoding="utf-8")) if path.stat().st_size < 5_000_000 else None
        except Exception:
            data = None
        if data is None:
            report = work_dir / "sanitation_report.json"
            if report.is_file():
                try:
                    rep = json.loads(report.read_text(encoding="utf-8"))
                    factors[disc] = float(((rep.get("disciplines") or {}).get(disc) or {})
                                          .get("unit_sanitation", {}).get("factor_to_meters", 1.0))
                    continue
                except Exception:
                    pass
            factors[disc] = 1.0
            continue
        factors[disc] = float((data.get("unit_sanitation") or {}).get("factor_to_meters", 1.0))
    return factors


def _build_verdict(
    transforms: dict[str, Any],
    reference: str,
    excluded: dict[str, DisciplineFeatures],
    tol_m: float,
) -> tuple[str, str]:
    auto = {d: t for d, t in transforms.items()
            if t.get("status") == "ok" and t.get("layer") in {"A", "B"} and not t.get("reference")}
    manual_ok = {d: t for d, t in transforms.items()
                 if t.get("status") == "ok" and t.get("layer") == "C"}
    needs = [d for d, t in transforms.items() if t.get("status") == "needs_manual_control_points"]
    non_ref = [d for d in transforms if not transforms[d].get("reference")]
    excl = ", ".join(excluded) or "none"

    if non_ref and not needs and (auto or manual_ok):
        worst = max((t.get("residual_rms_m", 0.0) for t in {**auto, **manual_ok}.values()), default=0.0)
        layers = "/".join(sorted({t["layer"] for t in {**auto, **manual_ok}.values()}))
        return (
            f"FRAME SOLVED (auto): disciplines [{', '.join(sorted({**auto, **manual_ok}))}] align via "
            f"layer {layers}, residual < {worst:.2f} m. Common frame viable for cross-discipline clash. "
            f"HS excluded ({excl}, pending re-selection).",
            "FRAME_SOLVED",
        )
    if auto or manual_ok:
        aligned = ", ".join(sorted({**auto, **manual_ok})) or "none"
        return (
            f"FRAME PARTIAL: [{aligned}] aligned (layers A/B/C); "
            f"[{', '.join(sorted(needs))}] need manual control points. "
            f"HS excluded ({excl}, pending re-selection).",
            "FRAME_PARTIAL",
        )
    return (
        f"FRAME NEEDS MANUAL: automatic anchors insufficient; manifest required for "
        f"[{', '.join(sorted(needs))}]. Only reference {reference} is fixed. "
        f"HS excluded ({excl}, pending re-selection).",
        "FRAME_NEEDS_MANUAL",
    )


# --------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------

def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# SERENA 18 — Phase 2 Common Frame Alignment (clean data)",
        "",
        f"Reference discipline: `{payload['reference']}`",
        f"Excluded from frame: `{', '.join(payload['excluded_from_frame']) or 'none'}` (pending re-selection)",
        f"Hash-offset (`file_translation_mm`) disabled: `{payload['provenance']['hash_offset_disabled']}` — replaced by common frame",
        "",
        f"**Verdict:** {payload['verdict']}",
        "",
        "## Per-discipline resolution",
        "| Discipline | Winning layer | Method | Scale | Rot° | Translation (m) | Residual RMS (m) | n CP | Status |",
        "|---|---|---|---:|---:|---|---:|---:|---|",
    ]
    for disc, t in payload["transforms"].items():
        tr = t.get("translation", [0.0, 0.0])
        trs = f"[{tr[0]:.2f}, {tr[1]:.2f}]" if isinstance(tr, list) else str(tr)
        lines.append(
            f"| {disc} | {t.get('layer') or '-'} | {t.get('method')} | "
            f"{t.get('scale', float('nan')):.3f} | {t.get('rotation_deg', float('nan')):.2f} | {trs} | "
            f"{t.get('residual_rms_m', float('nan')):.3f} | {t.get('n_control_points', 0)} | {t.get('status')} |"
        )
    lines += ["", "## Layer-A pair discrepancies on CLEAN data (checkpoint vs broken run)",
              "| Pair | Centroid Δ (m) | Corner RMS (m) | Status |", "|---|---:|---:|---|"]
    for pair, d in payload["layer_a_pair_discrepancies"]["pairs"].items():
        lines.append(f"| {pair} | {d['centroid_delta_m']:.3f} | {d['corner_rms_m']:.3f} | {d['status']} |")
    lines += ["", "## Discipline features (robust, strays rejected)",
              "| Discipline | Physical | Outline size (m) | Centroid (m) | Notes |", "|---|---:|---|---|---|"]
    for disc, f in payload["features"].items():
        sz = f["outline_size_m"]
        cen = f["centroid_m"]
        lines.append(
            f"| {disc} | {f['physical_count']} | [{sz[0]:.2f}, {sz[1]:.2f}] | "
            f"[{cen[0]:.1f}, {cen[1]:.1f}] | {'; '.join(f['notes']) or '-'} |"
        )
    if payload["pending_reselection"]:
        lines += ["", "## Excluded — pending re-selection"]
        for disc, info in payload["pending_reselection"].items():
            lines.append(f"- `{disc}` size={info['outline_size_m']} notes={'; '.join(info['notes'])}")
    lines += ["", "## Provenance",
              f"- Promoted SVD/affine: `{payload['provenance']['promoted_from']['fit_similarity/fit_affine']}`",
              f"- Promoted RANSAC: `{payload['provenance']['promoted_from']['robust_similarity_fit']}`",
              f"- Promoted similarity_transform: `{payload['provenance']['promoted_from']['similarity_transform']}`",
              f"- {payload['provenance']['hash_offset_note']}"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 common-frame alignment on clean data")
    parser.add_argument("--work-dir", type=Path, required=True,
                        help="Dir containing sanitized_geometry/*.sanitized.geometry.json")
    parser.add_argument("--reference", default=None, help="Reference discipline (default ARQ then EST)")
    parser.add_argument("--exclude", nargs="*", default=list(DEFAULT_EXCLUDE),
                        help="Disciplines excluded from the frame fit (default: HS)")
    parser.add_argument("--identity-tol-m", type=float, default=2.0)
    parser.add_argument("--anchor-tol-m", type=float, default=1.0)
    parser.add_argument("--alignment-manifest", type=Path, default=None,
                        help="Per-project manual control-point manifest JSON (Layer C)")
    parser.add_argument("--out", type=Path, default=None, help="common_frame.json output path")
    args = parser.parse_args()

    work = args.work_dir.resolve()
    t0 = time.perf_counter()
    payload = resolve_frame(
        work_dir=work,
        reference=args.reference,
        exclude=tuple(args.exclude),
        identity_tol_m=args.identity_tol_m,
        anchor_tol_m=args.anchor_tol_m,
        manifest_path=args.alignment_manifest.resolve() if args.alignment_manifest else None,
    )
    payload["runtime_s"] = round(time.perf_counter() - t0, 3)

    out = (args.out or (work / "common_frame.json")).resolve()
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path = work / "frame_alignment_report.md"
    report_path.write_text(render_report(payload), encoding="utf-8")

    print(f"[FRAME] reference={payload['reference']} excluded={payload['excluded_from_frame']}")
    print(f"[FRAME] wrote {out}")
    print(f"[FRAME] wrote {report_path}")
    print(f"[FRAME] verdict: {payload['verdict']}")
    for disc, t in payload["transforms"].items():
        print(f"  {disc}: layer={t.get('layer')} method={t.get('method')} "
              f"scale={t.get('scale', float('nan')):.3f} rms_m={t.get('residual_rms_m', float('nan')):.3f} "
              f"status={t.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
