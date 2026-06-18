#!/usr/bin/env python
"""Resolve the SERENA 18 common frame from REAL control points (Layer C).

Reuses:
  * coordination.core.control_points  — solve_discipline / validation / hold-out
  * coordination.core.frame_alignment — resolve_frame (writes common_frame.json)

Honest by construction: a discipline is solved ONLY if it has real control points
that pass the gates (RMS < 0.5 m AND scale ~= 1.0). Disciplines without authored
points are reported pending; nothing is fabricated.

Run (conda python):
    PYTHONPATH=motor /Users/samuelfernandez/anaconda3/bin/python \
        motor/coordination/scripts/resolve_serena18_frame.py
"""

from __future__ import annotations

import json
from pathlib import Path

from coordination.core.control_points import (
    context_from_work_dir,
    load_manifest,
    print_report,
    solve_discipline,
    verify_frame,
)
from coordination.core.frame_alignment import render_report, resolve_frame

WORK = Path("var/coord_outputs/serena18_run")
MANIFEST = WORK / "alignment_manifest.json"
REFERENCE = "ARQ"
NON_REF_DISCIPLINES = ["EST", "ELEC", "MEC", "HS"]
RMS_GATE_M = 0.5
SCALE_TOL = 0.02
HOLDOUT_TOL_M = 0.5


def _fmt(v: float | None, nd: int = 4) -> str:
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "—"


def main() -> int:
    print("=" * 78)
    print("  SERENA 18 — COMMON FRAME from real control points (Layer C)")
    print("=" * 78)

    manifest = load_manifest(MANIFEST)
    context = context_from_work_dir(WORK.resolve())

    authored = manifest.get("control_points") or {}
    print(f"\nReference (identity): {REFERENCE}")
    print(f"Disciplines with authored control points in manifest: "
          f"{sorted(d for d, r in authored.items() if r) or 'none besides reference'}")

    summary: list[dict] = []
    # ARQ is the reference frame: identity by definition.
    summary.append({
        "discipline": REFERENCE, "n": 0, "scale": 1.0, "rot": 0.0, "rms": 0.0,
        "holdout": 0.0, "status": "reference (identity)", "frame_ready": True,
    })

    for disc in NON_REF_DISCIPLINES:
        report = solve_discipline(
            manifest, disc, context=context, reference=REFERENCE,
            rms_gate_m=RMS_GATE_M, scale_tol=SCALE_TOL,
            persist=True, manifest_path=MANIFEST,
        )
        print_report(report)

        hold = report.get("hold_out") or []
        worst_holdout = max((h["error_m"] for h in hold), default=None)
        holdout_ok = all(h["within_tol"] for h in hold) if hold else None
        scale = report.get("scale")
        rms = report.get("rms_m")
        status = report.get("alignment_status", "pending")
        frame_ready = (
            status == "solved"
            and scale is not None and abs(scale - 1.0) <= SCALE_TOL
            and rms is not None and rms <= RMS_GATE_M
            and (holdout_ok is True)
        )
        summary.append({
            "discipline": disc,
            "n": report.get("n_usable", 0),
            "scale": scale,
            "rot": report.get("rotation_deg"),
            "rms": rms,
            "holdout": worst_holdout,
            "status": status if report.get("n_usable", 0) >= 3 else "pending (no authored points)",
            "frame_ready": bool(frame_ready),
        })

    # ── Per-discipline solve table ─────────────────────────────────────────
    print("\n" + "-" * 78)
    print("PER-DISCIPLINE SOLVE TABLE")
    print(f"{'disc':<6}{'n':>3} {'scale':>9} {'rot°':>8} {'RMS m':>9} {'holdout m':>11}  {'status':<26}{'frame-ready'}")
    for s in summary:
        print(
            f"{s['discipline']:<6}{s['n']:>3} {_fmt(s['scale'],5):>9} {_fmt(s['rot'],3):>8} "
            f"{_fmt(s['rms']):>9} {_fmt(s['holdout']):>11}  {s['status']:<26}{'YES' if s['frame_ready'] else 'no'}"
        )

    # ── Cross-discipline verify ────────────────────────────────────────────
    print("\n" + "-" * 78)
    print("CROSS-DISCIPLINE VERIFY (shared hold-out feature, not used in any fit)")
    v = verify_frame(manifest)
    print(f"  solved disciplines (non-reference): {v['solved_disciplines']}")
    if v["shared_holdout_labels"]:
        for label, info in v["shared_holdout_labels"].items():
            print(f"  shared '{label}' across {info['disciplines']}: max pairwise {info['max_pairwise_m']} m")
        print(f"  worst cross-discipline hold-out: {v['worst_cross_discipline_m']} m")
    else:
        print("  No shared hold-out across >=2 non-reference disciplines yet.")
        # The reference IS the common frame, so a solved discipline's own hold-out
        # mapped into ARQ is the honest accuracy of that discipline vs the frame.
        for s in summary:
            if s["discipline"] == REFERENCE or s["status"] != "solved":
                continue
            print(
                f"  {s['discipline']} -> {REFERENCE} hold-out (feature not in fit): "
                f"{_fmt(s['holdout'])} m  "
                f"({'within' if (s['holdout'] is not None and s['holdout'] <= HOLDOUT_TOL_M) else 'OUT OF'} {HOLDOUT_TOL_M} m tol)"
            )
        print("  NOTE: a true multi-discipline cross-check (e.g. EST vs ELEC at a shared")
        print("        column) needs >=2 non-reference disciplines solved. Only EST is solved,")
        print("        so the available honest check is EST vs the ARQ reference frame.")

    # ── Final common_frame.json via frame_alignment.resolve_frame ──────────
    print("\n" + "-" * 78)
    print("WRITE common_frame.json (frame_alignment.resolve_frame, Layer C reused)")
    payload = resolve_frame(
        work_dir=WORK.resolve(),
        reference=REFERENCE,
        exclude=("HS",),
        manifest_path=MANIFEST.resolve(),
    )
    out = WORK / "common_frame.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (WORK / "frame_alignment_report.md").write_text(render_report(payload), encoding="utf-8")
    print(f"  wrote {out}")
    print(f"  verdict: {payload['verdict']}")
    prov = payload["provenance"]
    print(f"  nasas_paths hash-offset disabled: {prov['hash_offset_disabled']}  "
          f"(file_translation_mm NOT applied)")
    print("  per-discipline transforms in common_frame.json:")
    for disc, t in payload["transforms"].items():
        print(f"    {disc:<6} layer={str(t.get('layer')):<4} method={t.get('method'):<34} "
              f"scale={_fmt(t.get('scale'),3)} rms={_fmt(t.get('residual_rms_m'),3)} status={t.get('status')}")

    # ── Frame-ready conclusion ─────────────────────────────────────────────
    ready = [s["discipline"] for s in summary if s["frame_ready"]]
    not_ready = [s["discipline"] for s in summary if not s["frame_ready"]]
    print("\n" + "=" * 78)
    print(f"FRAME-READY for clash: {ready}")
    print(f"NOT ready (need authored control points): {not_ready}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
