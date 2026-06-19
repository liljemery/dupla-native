#!/usr/bin/env python
"""Control-point authoring + validation for Dupla common-frame alignment.

This is the human-in-the-loop front end for Layer C in
``coordination.core.frame_alignment``. The user identifies the SAME physical point
in each discipline's DWG and in the ARQ reference DWG; this tool turns those pairs
into a validated similarity transform and persists it into the project alignment
manifest (the format the frame resolver already reads/reuses).

Workflow
--------
1. ENTRY     Per discipline, pairs ``{label, disc_xy|disc_handle, ref_xy|ref_handle}``.
             Handles are resolved to a center automatically via ezdxf (less error-prone
             than typing coordinates), scaled by the discipline's factor_to_meters.
2. VALIDATE  >=3 points; collinearity guard; per-point residuals after an SVD similarity
             fit; outlier flagging; scale-≈-1 sanity (everything is meters now).
3. PERSIST   On a good fit (RMS < gate AND scale ≈ 1) write control points + resolved
             transform into the manifest. Status: solved / pending. Never refabricated.
4. VERIFY    A held-out shared point (NOT used in the fit) must land within tolerance
             after transform — the honest accuracy metric.

All transforms map a discipline's meters INTO the ARQ reference meters:
    ref_xy_m = matrix @ disc_xy_m + translation     (matrix = scale * R * flip)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

try:
    import ezdxf
    from ezdxf import bbox as _ezdxf_bbox
except Exception:  # pragma: no cover
    ezdxf = None  # type: ignore[assignment]
    _ezdxf_bbox = None  # type: ignore[assignment]

from coordination.core.frame_alignment import fit_similarity, transform_to_serializable


# --------------------------------------------------------------------------------------
# Thresholds
# --------------------------------------------------------------------------------------

MIN_CONTROL_POINTS = 3
RMS_GATE_M = 0.5                 # persist only if fit RMS is below this
SCALE_TOL = 0.02                 # |scale - 1| must be within this to persist (meters in/out)
COLLINEAR_REJECT_RATIO = 0.02    # singular-value ratio below this => degenerate (reject)
COLLINEAR_WARN_RATIO = 0.08      # below this => warn (rotation poorly constrained)
RESIDUAL_OUTLIER_ABS_M = 0.5     # a point whose residual exceeds this is flagged
RESIDUAL_OUTLIER_RATIO = 4.0     # ...or exceeds this multiple of the median residual
HOLDOUT_TOL_M = 0.5              # hold-out point must land within this after transform


# --------------------------------------------------------------------------------------
# Handle resolution (entry by handle instead of typing coordinates)
# --------------------------------------------------------------------------------------

def resolve_handle_center(dxf_path: str | Path, handle: str, factor_to_meters: float = 1.0) -> list[float]:
    """Return the bbox center of a DXF entity (by handle) in METERS.

    Raises ``ValueError`` if ezdxf is unavailable or the handle/geometry is not found.
    """
    if ezdxf is None or _ezdxf_bbox is None:
        raise ValueError("ezdxf not available; enter disc_xy/ref_xy coordinates directly")
    doc = ezdxf.readfile(str(dxf_path))
    handle_norm = str(handle).strip().upper().lstrip("#")
    entity = doc.entitydb.get(handle_norm)
    if entity is None:
        for cand in doc.modelspace():
            if str(cand.dxf.handle).upper() == handle_norm:
                entity = cand
                break
    if entity is None:
        raise ValueError(f"handle {handle!r} not found in {Path(dxf_path).name}")
    box = _ezdxf_bbox.extents([entity])
    if not box.has_data:
        raise ValueError(f"handle {handle!r} has no resolvable geometry bounds")
    return [float(box.center.x) * factor_to_meters, float(box.center.y) * factor_to_meters]


def resolve_rows(
    rows: list[dict[str, Any]],
    *,
    disc_dxf: str | None,
    ref_dxf: str | None,
    disc_factor: float,
    ref_factor: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fill ``disc_xy``/``ref_xy`` from handles where coordinates are absent."""
    resolved: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, row in enumerate(rows):
        out = dict(row)
        label = out.get("label", f"point_{i}")
        # Accept already-persisted rows (which store the discipline point as ``model_xy``)
        # so the tool is idempotent / can re-validate a saved manifest.
        if not out.get("disc_xy") and out.get("model_xy"):
            out["disc_xy"] = out["model_xy"]
        if not out.get("disc_xy") and out.get("disc_handle"):
            try:
                out["disc_xy"] = resolve_handle_center(disc_dxf, out["disc_handle"], disc_factor)
                out["disc_xy_source"] = f"handle:{out['disc_handle']}"
            except Exception as exc:
                errors.append(f"[{label}] disc handle: {exc}")
        if not out.get("ref_xy") and out.get("ref_handle"):
            try:
                out["ref_xy"] = resolve_handle_center(ref_dxf, out["ref_handle"], ref_factor)
                out["ref_xy_source"] = f"handle:{out['ref_handle']}"
            except Exception as exc:
                errors.append(f"[{label}] ref handle: {exc}")
        resolved.append(out)
    return resolved, errors


# --------------------------------------------------------------------------------------
# Geometry checks
# --------------------------------------------------------------------------------------

def collinearity(points: np.ndarray) -> dict[str, Any]:
    """Singular-value ratio of centered points. ~0 => collinear (degenerate for rotation)."""
    if len(points) < 2:
        return {"ratio": 0.0, "status": "reject", "spread_m": [0.0, 0.0], "reason": "too_few_points"}
    centered = points - points.mean(axis=0)
    _u, s, _vt = np.linalg.svd(centered, full_matrices=False)
    ratio = float(s[1] / s[0]) if s[0] > 1e-9 else 0.0
    spread = [float(points[:, 0].ptp()), float(points[:, 1].ptp())]
    if ratio < COLLINEAR_REJECT_RATIO:
        status = "reject"
    elif ratio < COLLINEAR_WARN_RATIO:
        status = "warn"
    else:
        status = "ok"
    return {"ratio": ratio, "status": status, "spread_m": spread}


def fit_control_points(disc_xy: np.ndarray, ref_xy: np.ndarray) -> dict[str, Any]:
    """SVD similarity disc->ref (try both handedness), with per-point residuals in meters."""
    candidates = [f for f in (fit_similarity(disc_xy, ref_xy, False), fit_similarity(disc_xy, ref_xy, True)) if f]
    if not candidates:
        raise ValueError("could not fit a similarity transform from the control points")
    best = min(candidates, key=lambda f: float(np.sqrt(np.mean(f["residuals"] ** 2))))
    residuals = [float(v) for v in best["residuals"]]
    transform = transform_to_serializable(best)
    transform.update({
        "rms_m": float(np.sqrt(np.mean(np.square(residuals)))),
        "max_m": float(np.max(residuals)),
        "n_control_points": int(len(disc_xy)),
    })
    return {"transform": transform, "residuals_m": residuals}


# --------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------

def validate_points(
    rows: list[dict[str, Any]],
    *,
    rms_gate_m: float = RMS_GATE_M,
    scale_tol: float = SCALE_TOL,
) -> dict[str, Any]:
    """Run all gates and return a structured report (does not persist)."""
    report: dict[str, Any] = {"n_points": len(rows), "issues": [], "warnings": [], "persist_ok": False}

    usable = [r for r in rows if r.get("disc_xy") and r.get("ref_xy")]
    report["n_usable"] = len(usable)
    if len(usable) < MIN_CONTROL_POINTS:
        report["issues"].append(
            f"need >= {MIN_CONTROL_POINTS} resolved points, have {len(usable)} "
            "(missing coordinates/handles?)"
        )
        return report

    disc_xy = np.array([r["disc_xy"] for r in usable], dtype=float)
    ref_xy = np.array([r["ref_xy"] for r in usable], dtype=float)

    col_disc = collinearity(disc_xy)
    col_ref = collinearity(ref_xy)
    report["collinearity"] = {"discipline": col_disc, "reference": col_ref}
    for name, col in (("discipline", col_disc), ("reference", col_ref)):
        if col["status"] == "reject":
            report["issues"].append(
                f"{name} points are nearly collinear (ratio={col['ratio']:.3f}); "
                "rotation is undetermined — add a well-separated 3rd/4th point"
            )
        elif col["status"] == "warn":
            report["warnings"].append(f"{name} points weakly spread (ratio={col['ratio']:.3f})")

    fit = fit_control_points(disc_xy, ref_xy)
    transform, residuals = fit["transform"], fit["residuals_m"]
    report["transform"] = transform
    report["scale"] = transform["scale"]
    report["rotation_deg"] = transform["rotation_deg"]
    report["rms_m"] = transform["rms_m"]
    report["max_m"] = transform["max_m"]

    median_res = float(np.median(residuals)) if residuals else 0.0
    point_rows = []
    for r, res in zip(usable, residuals):
        is_outlier = res > RESIDUAL_OUTLIER_ABS_M or (median_res > 1e-6 and res > RESIDUAL_OUTLIER_RATIO * median_res)
        point_rows.append({
            "label": r.get("label"),
            "disc_xy": r["disc_xy"],
            "ref_xy": r["ref_xy"],
            "residual_m": round(res, 4),
            "flag": "OUTLIER" if is_outlier else "ok",
            "disc_xy_source": r.get("disc_xy_source", "typed"),
            "ref_xy_source": r.get("ref_xy_source", "typed"),
        })
    report["points"] = point_rows
    outliers = [p["label"] for p in point_rows if p["flag"] == "OUTLIER"]
    if outliers:
        report["warnings"].append(
            f"high-residual point(s): {outliers} (median residual {median_res:.3f} m) — "
            "likely mis-identified/mistyped; drop or fix and refit"
        )

    scale_dev = abs(transform["scale"] - 1.0)
    if scale_dev > scale_tol:
        report["issues"].append(
            f"scale {transform['scale']:.4f} deviates {scale_dev*100:.1f}% from 1.0 — "
            "wrong correspondence or residual unit error"
        )

    if transform["rms_m"] > rms_gate_m:
        report["issues"].append(f"fit RMS {transform['rms_m']:.3f} m exceeds gate {rms_gate_m} m")

    report["persist_ok"] = (
        not report["issues"]
        and scale_dev <= scale_tol
        and transform["rms_m"] <= rms_gate_m
        and col_disc["status"] != "reject"
        and col_ref["status"] != "reject"
    )
    return report


# --------------------------------------------------------------------------------------
# Hold-out verification
# --------------------------------------------------------------------------------------

def apply_serialized(point: list[float], transform: dict[str, Any]) -> list[float]:
    m = np.asarray(transform["matrix"], dtype=float)
    t = np.asarray(transform["translation"], dtype=float)
    out = m @ np.asarray(point, dtype=float) + t
    return [float(out[0]), float(out[1])]


def holdout_errors(transform: dict[str, Any], hold_out_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For each held-out pair, transform disc_xy and measure distance to the known ref_xy."""
    rows = []
    for r in hold_out_rows:
        if not r.get("disc_xy") or not r.get("ref_xy"):
            continue
        pred = apply_serialized(r["disc_xy"], transform)
        err = float(np.linalg.norm(np.array(pred) - np.array(r["ref_xy"], dtype=float)))
        rows.append({
            "label": r.get("label"),
            "predicted_ref_xy": [round(v, 4) for v in pred],
            "known_ref_xy": [round(float(v), 4) for v in r["ref_xy"]],
            "error_m": round(err, 4),
            "within_tol": err <= HOLDOUT_TOL_M,
        })
    return rows


# --------------------------------------------------------------------------------------
# Manifest IO + solve
# --------------------------------------------------------------------------------------

def load_manifest(path: Path) -> dict[str, Any]:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def context_from_work_dir(work_dir: Path) -> dict[str, dict[str, Any]]:
    """Auto-load dxf_path + factor_to_meters per discipline from sanitized geometry."""
    ctx: dict[str, dict[str, Any]] = {}
    sanitized_dir = work_dir / "sanitized_geometry"
    for p in sorted(sanitized_dir.glob("*.sanitized.geometry.json")):
        disc = p.name.split(".")[0]
        try:
            if p.stat().st_size < 5_000_000:
                d = json.loads(p.read_text(encoding="utf-8"))
                ctx[disc] = {
                    "dxf_path": d.get("dxf_path"),
                    "factor_to_meters": float((d.get("unit_sanitation") or {}).get("factor_to_meters", 1.0)),
                }
                continue
        except Exception:
            pass
        # Large file (e.g. HS): pull factor from the sanitation report instead.
        rep = work_dir / "sanitation_report.json"
        factor = 1.0
        dxf_path = None
        if rep.is_file():
            try:
                data = json.loads(rep.read_text(encoding="utf-8"))
                factor = float(((data.get("disciplines") or {}).get(disc) or {})
                               .get("unit_sanitation", {}).get("factor_to_meters", 1.0))
            except Exception:
                pass
        ctx[disc] = {"dxf_path": dxf_path, "factor_to_meters": factor}
    return ctx


def solve_discipline(
    manifest: dict[str, Any],
    discipline: str,
    *,
    context: dict[str, dict[str, Any]] | None = None,
    reference: str = "ARQ",
    rms_gate_m: float = RMS_GATE_M,
    scale_tol: float = SCALE_TOL,
    persist: bool = True,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Resolve handles, validate, fit, optionally persist; return a full report."""
    context = context or {}
    ref_ctx = context.get(reference, {})
    disc_ctx = context.get(discipline, {})
    authoring = (manifest.get("control_points") or {}).get(discipline) or []
    hold_out = (manifest.get("hold_out_points") or {}).get(discipline) or []

    resolved, resolve_errors = resolve_rows(
        authoring,
        disc_dxf=disc_ctx.get("dxf_path"),
        ref_dxf=ref_ctx.get("dxf_path"),
        disc_factor=float(disc_ctx.get("factor_to_meters", 1.0)),
        ref_factor=float(ref_ctx.get("factor_to_meters", 1.0)),
    )
    resolved_holdout, _ = resolve_rows(
        hold_out,
        disc_dxf=disc_ctx.get("dxf_path"),
        ref_dxf=ref_ctx.get("dxf_path"),
        disc_factor=float(disc_ctx.get("factor_to_meters", 1.0)),
        ref_factor=float(ref_ctx.get("factor_to_meters", 1.0)),
    )

    report = validate_points(resolved, rms_gate_m=rms_gate_m, scale_tol=scale_tol)
    report["discipline"] = discipline
    report["reference"] = reference
    if resolve_errors:
        report["issues"] = list(report.get("issues", [])) + resolve_errors
        report["persist_ok"] = False

    if report.get("transform") and resolved_holdout:
        report["hold_out"] = holdout_errors(report["transform"], resolved_holdout)

    status = "pending"
    if report.get("persist_ok") and persist:
        manifest.setdefault("control_points", {})[discipline] = [
            {"label": r.get("label"), "model_xy": r["disc_xy"], "ref_xy": r["ref_xy"]}
            for r in resolved if r.get("disc_xy") and r.get("ref_xy")
        ]
        record = transform_to_serializable(report["transform"])
        record.update({
            "residual_rms_m": report["rms_m"],
            "residual_max_m": report["max_m"],
            "n_control_points": report["n_usable"],
            "status": "ok",
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "source": "control_points.solve_discipline",
        })
        manifest.setdefault("resolved_transforms", {})[discipline] = record
        status = "solved"
    manifest.setdefault("alignment_status", {})[discipline] = status
    if persist and manifest_path:
        save_manifest(manifest_path, manifest)
    report["alignment_status"] = status
    return report


def verify_frame(manifest: dict[str, Any]) -> dict[str, Any]:
    """Cross-discipline check on shared held-out labels once >=2 disciplines are solved."""
    solved = [d for d, s in (manifest.get("alignment_status") or {}).items() if s == "solved"]
    transforms = manifest.get("resolved_transforms") or {}
    hold_out = manifest.get("hold_out_points") or {}
    by_label: dict[str, list[dict[str, Any]]] = {}
    for disc in solved:
        tr = transforms.get(disc)
        for r in hold_out.get(disc, []):
            if not r.get("disc_xy") or not r.get("label") or not tr:
                continue
            mapped = apply_serialized(r["disc_xy"], tr)
            by_label.setdefault(r["label"], []).append({"discipline": disc, "mapped_ref_xy": mapped})
    shared = {}
    worst = 0.0
    for label, rows in by_label.items():
        if len(rows) < 2:
            continue
        pts = np.array([r["mapped_ref_xy"] for r in rows], dtype=float)
        dmax = 0.0
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                dmax = max(dmax, float(np.linalg.norm(pts[i] - pts[j])))
        shared[label] = {"disciplines": [r["discipline"] for r in rows], "max_pairwise_m": round(dmax, 4)}
        worst = max(worst, dmax)
    return {"solved_disciplines": solved, "shared_holdout_labels": shared,
            "worst_cross_discipline_m": round(worst, 4) if shared else None}


# --------------------------------------------------------------------------------------
# Template
# --------------------------------------------------------------------------------------

def build_template(disciplines: list[str], reference: str = "ARQ") -> dict[str, Any]:
    guidance = [
        f"Reference frame = {reference}. ref_xy values are coordinates in the {reference} DWG (meters).",
        "For each non-reference discipline collect >= 3 (ideally 4+) control points:",
        "  - same physical feature visible in BOTH that discipline's DWG and the ARQ DWG",
        "  - prefer grid intersections (e.g. 'grid B-3'), building corners, or a specific column",
        "  - spread them out and AVOID collinear points (don't pick 3 along one gridline)",
        "Enter either disc_xy/ref_xy [x,y] meters, OR a disc_handle/ref_handle to auto-resolve.",
        "Add at least 1 hold_out_points entry per discipline (NOT used in the fit) to verify accuracy.",
        "Units are meters. Estimated scale must come out ~1.0; if not, a point is wrong.",
    ]
    example_cp = [
        {"label": "grid A-1 intersection", "disc_handle": None, "disc_xy": [0.0, 0.0],
         "ref_handle": None, "ref_xy": [0.0, 0.0]},
        {"label": "grid F-1 intersection", "disc_handle": None, "disc_xy": [0.0, 0.0],
         "ref_handle": None, "ref_xy": [0.0, 0.0]},
        {"label": "NE building corner", "disc_handle": None, "disc_xy": [0.0, 0.0],
         "ref_handle": None, "ref_xy": [0.0, 0.0]},
    ]
    example_ho = [
        {"label": "column C12 (hold-out)", "disc_handle": None, "disc_xy": [0.0, 0.0],
         "ref_handle": None, "ref_xy": [0.0, 0.0]},
    ]
    return {
        "project": "FILL_ME",
        "reference": reference,
        "_guidance": guidance,
        "control_points": {d: [dict(p) for p in example_cp] for d in disciplines if d != reference},
        "hold_out_points": {d: [dict(p) for p in example_ho] for d in disciplines if d != reference},
        "alignment_status": {d: "pending" for d in disciplines if d != reference},
    }


# --------------------------------------------------------------------------------------
# Reporting + CLI
# --------------------------------------------------------------------------------------

def print_report(report: dict[str, Any]) -> None:
    disc = report.get("discipline", "?")
    print(f"\n=== Control-point validation: {disc} -> {report.get('reference', 'ARQ')} ===")
    print(f"points: {report.get('n_points')} entered, {report.get('n_usable', 0)} usable")
    col = report.get("collinearity")
    if col:
        print(f"collinearity: disc ratio={col['discipline']['ratio']:.3f} ({col['discipline']['status']}), "
              f"ref ratio={col['reference']['ratio']:.3f} ({col['reference']['status']}); "
              f"disc spread={[round(v,1) for v in col['discipline']['spread_m']]} m")
    if "scale" in report:
        print(f"fit: scale={report['scale']:.5f} rot={report['rotation_deg']:.3f}° "
              f"RMS={report['rms_m']:.4f} m max={report['max_m']:.4f} m")
    for p in report.get("points", []):
        print(f"  [{p['flag']:>7}] {p['label']:<28} residual={p['residual_m']:.4f} m  ({p['disc_xy_source']})")
    for ho in report.get("hold_out", []):
        ok = "OK" if ho["within_tol"] else "OUT-OF-TOL"
        print(f"  hold-out [{ok}] {ho['label']:<24} error={ho['error_m']:.4f} m")
    for w in report.get("warnings", []):
        print(f"  WARN: {w}")
    for i in report.get("issues", []):
        print(f"  ISSUE: {i}")
    print(f"status: {report.get('alignment_status', '?')}  (persist_ok={report.get('persist_ok')})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Author/validate frame-alignment control points")
    parser.add_argument("--manifest", type=Path, required=True, help="Alignment manifest JSON (read/write)")
    parser.add_argument("--work-dir", type=Path, default=None, help="Dir with sanitized_geometry (auto dxf/factors)")
    parser.add_argument("--reference", default="ARQ")
    parser.add_argument("--discipline", default=None, help="Discipline to solve")
    parser.add_argument("--solve", action="store_true", help="Validate + fit + persist on good fit")
    parser.add_argument("--no-persist", action="store_true", help="Validate only, do not write")
    parser.add_argument("--verify", action="store_true", help="Cross-discipline hold-out check")
    parser.add_argument("--template", nargs="*", default=None, metavar="DISC",
                        help="Write a blank template for these disciplines and exit")
    parser.add_argument("--rms-gate-m", type=float, default=RMS_GATE_M)
    parser.add_argument("--scale-tol", type=float, default=SCALE_TOL)
    args = parser.parse_args()

    if args.template is not None:
        discs = args.template or ["ELEC", "EST", "MEC", "HS"]
        template = build_template([args.reference, *discs], reference=args.reference)
        save_manifest(args.manifest, template)
        print(f"[TEMPLATE] wrote {args.manifest} for disciplines {discs}")
        return 0

    manifest = load_manifest(args.manifest)
    context = context_from_work_dir(args.work_dir.resolve()) if args.work_dir else {}

    if args.discipline and (args.solve or args.no_persist):
        report = solve_discipline(
            manifest, args.discipline, context=context, reference=args.reference,
            rms_gate_m=args.rms_gate_m, scale_tol=args.scale_tol,
            persist=not args.no_persist, manifest_path=args.manifest if not args.no_persist else None,
        )
        print_report(report)

    if args.verify:
        v = verify_frame(manifest)
        print("\n=== Frame verification (cross-discipline hold-outs) ===")
        print(f"solved: {v['solved_disciplines']}")
        for label, info in v["shared_holdout_labels"].items():
            print(f"  shared '{label}' across {info['disciplines']}: max pairwise {info['max_pairwise_m']} m")
        if v["worst_cross_discipline_m"] is not None:
            print(f"worst cross-discipline hold-out: {v['worst_cross_discipline_m']} m")
        else:
            print("  (need >=2 solved disciplines sharing a hold-out label)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
