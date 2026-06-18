"""Overlay intra-ARQ clashes onto literal APS 2D-sheet screenshots.

Uses:
  model metres  --(similarity from matched handles)-->  APS paper units
  paper units   --(capture diag screenBBox)-->           screenshot pixels

Outputs clean overview + per-cluster detail annex JPEGs sized for full-bleed PDF.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from coordination.reporting.plan_annex import (
    autocrop_content,
    crop_sheet_from_diag,
    crop_to_aspect,
    detail_crop,
    draw_clash_markers,
    fit_annex_size,
    linework_score,
    normalize_plan_colors,
    prepare_annex,
    snap_to_linework,
)

OUT = Path("var/coord_outputs/serena18_run/arq_intra_clash")
GEOM = Path("var/coord_outputs/serena18_run/sanitized_geometry/ARQ.sanitized.geometry.json")
SHEET_PNG = OUT / "aps_plan.png"
FRAG = OUT / "aps_fragments_2d.json"
CLASH = OUT / "clash_results.json"
DIAG = OUT / "aps_plan.png.diag.json"

MAX_PER_DETAIL = 8
CLUSTER_RADIUS_PX = 380


def umeyama(src, dst):
    n = len(src); mu_s = src.mean(0); mu_d = dst.mean(0)
    ss = src - mu_s; dd = dst - mu_d
    C = dd.T @ ss / n
    U, D, Vt = np.linalg.svd(C); S = np.eye(2)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[1, 1] = -1
    R = U @ S @ Vt; var = (ss ** 2).sum() / n
    c = np.trace(np.diag(D) @ S) / var; t = mu_d - c * R @ mu_s
    return c, R, t


def fit_model_to_paper():
    g = json.load(open(GEOM))
    gb = {e["handle"].upper(): e for e in g["elements"]}
    objs = json.load(open(FRAG))["views"][0]["objects"]
    sb = json.load(open(FRAG))["views"][0]["sheet_bounds"]
    sw, sh = sb[2] - sb[0], sb[3] - sb[1]
    pairs = []
    for o in objs:
        e = gb.get(o["handle"].upper())
        if not e or not e.get("model_center"):
            continue
        pb, mb, mc = o["world_bounds"], e["model_bounds"], e["model_center"]
        if not (-60 < mc[0] < 120 and 30 < mc[1] < 120):
            continue
        if (pb[2] - pb[0]) > sw * 0.25 or (pb[3] - pb[1]) > sh * 0.25:
            continue
        if (mb[2] - mb[0]) > 10 or (mb[3] - mb[1]) > 10:
            continue
        pairs.append((mc, o["center"]))
    M = np.array([p[0] for p in pairs]); P = np.array([p[1] for p in pairs])
    rng = np.random.default_rng(0); best = None
    for _ in range(4000):
        idx = rng.choice(len(M), 3, replace=False)
        try:
            c, R, t = umeyama(M[idx], P[idx])
        except Exception:
            continue
        if not np.isfinite(c) or c <= 0:
            continue
        res = np.linalg.norm((c * (R @ M.T).T) + t - P, axis=1)
        inl = res < 0.12
        if best is None or inl.sum() > best[0]:
            best = (inl.sum(), inl)
    inl = best[1]
    c, R, t = umeyama(M[inl], P[inl])
    res = np.linalg.norm((c * (R @ M[inl].T).T) + t - P[inl], axis=1)
    print(f"[fit] pairs={len(M)} inliers={inl.sum()} scale={c:.5f} "
          f"rot={np.degrees(np.arctan2(R[1,0],R[0,0])):.2f} resid_mean={res.mean():.4f}")
    return c, R, t


def paper_to_screen_fn(diag):
    mb = diag["modelBBox"]; sb = diag["screenBBox"]
    x0, x1 = mb["min"]["x"], mb["max"]["x"]
    y0, y1 = mb["min"]["y"], mb["max"]["y"]

    def f(px, py):
        u = (px - x0) / (x1 - x0) if x1 != x0 else 0.5
        v = (py - y0) / (y1 - y0) if y1 != y0 else 0.5
        sx = sb["minX"] + u * (sb["maxX"] - sb["minX"])
        sy = sb["maxY"] - v * (sb["maxY"] - sb["minY"])
        return sx, sy

    return f


def _centroid_m(inc: dict) -> tuple[float, float]:
    b = inc["bounds_m"]
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _layer_versus(inc: dict) -> str:
    rep = inc.get("representative") or inc
    a = rep.get("layer_a") or "?"
    b = rep.get("layer_b") or "?"
    # Short labels for on-plan readability
    def short(layer: str) -> str:
        return layer.replace("I-", "").replace("MILLWORK-FULL-HEIGHT", "MW-FH")[:12]
    return f"{short(a)} vs {short(b)}"


def _overlap_centroid_m(inc: dict) -> tuple[float, float]:
    rep = inc.get("representative") or inc
    b = rep.get("overlap_bounds_m") or inc.get("bounds_m")
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _handle_paper_xy(obj: dict) -> tuple[float, float] | None:
    wb = obj.get("world_bounds") or obj.get("aggregate_world_bounds")
    if wb and len(wb) >= 4:
        return (wb[0] + wb[2]) / 2, (wb[1] + wb[3]) / 2
    center = obj.get("center")
    if center:
        return center[0], center[1]
    return None


def _incident_sheet_px(
    inc: dict,
    sheet: Image.Image,
    frag_by_handle: dict,
    p2s,
    total_off,
    model_to_sheet_fn,
) -> tuple[float, float]:
    """Best-effort sheet pixel for a clash (overlap fit + fragment, snapped to linework)."""
    rep = inc.get("representative") or inc
    candidates: list[tuple[float, float]] = []

    oc = _overlap_centroid_m(inc)
    candidates.append(model_to_sheet_fn(*oc))

    frag_pts: list[tuple[float, float]] = []
    for h in (rep.get("handle_a"), rep.get("handle_b")):
        if not h:
            continue
        obj = frag_by_handle.get(str(h).upper())
        if not obj:
            continue
        pc = _handle_paper_xy(obj)
        if not pc:
            continue
        sx, sy = p2s(pc[0], pc[1])
        frag_pts.append((sx - total_off[0], sy - total_off[1]))
    if frag_pts:
        candidates.append((
            sum(p[0] for p in frag_pts) / len(frag_pts),
            sum(p[1] for p in frag_pts) / len(frag_pts),
        ))

    best = min(candidates, key=lambda p: linework_score(sheet, p[0], p[1]))
    return snap_to_linework(sheet, best[0], best[1], radius=max(80, sheet.width // 18))


def group_incidents_by_px(
    incidents: list[dict],
    positions: dict[str, tuple[float, float]],
    *,
    max_per: int,
    radius_px: float,
) -> list[list[dict]]:
    if not incidents:
        return []
    remaining = list(incidents)
    groups: list[list[dict]] = []
    while remaining:
        seed = remaining.pop(0)
        group = [seed]
        changed = True
        while changed and len(group) < max_per:
            changed = False
            gcx = sum(positions[i["incident_id"]][0] for i in group) / len(group)
            gcy = sum(positions[i["incident_id"]][1] for i in group) / len(group)
            best_j, best_d = None, radius_px
            for j, inc in enumerate(remaining):
                cx, cy = positions[inc["incident_id"]]
                d = math.hypot(cx - gcx, cy - gcy)
                if d <= best_d:
                    best_j, best_d = j, d
            if best_j is not None:
                group.append(remaining.pop(best_j))
                changed = True
        groups.append(group)
    return groups


def _group_layer_pairs(group: list[dict]) -> list[str]:
    pairs: set[str] = set()
    for inc in group:
        rep = inc.get("representative") or inc
        a, b = rep.get("layer_a"), rep.get("layer_b")
        if a and b:
            pairs.add(f"{a} vs {b}")
    return sorted(pairs)


def main():
    c, R, t = fit_model_to_paper()
    diag = json.load(open(DIAG))
    p2s = paper_to_screen_fn(diag)

    raw = Image.open(SHEET_PNG).convert("RGB")
    sheet, offset = crop_sheet_from_diag(raw, diag)
    sheet = normalize_plan_colors(sheet)
    sheet, acrop_off = autocrop_content(sheet)
    total_off = (offset[0] + acrop_off[0], offset[1] + acrop_off[1])

    cl = json.load(open(CLASH))
    incidents = cl["incidents"]
    frag_by_handle = {
        o["handle"].upper(): o
        for o in json.load(open(FRAG))["views"][0]["objects"]
    }

    def model_to_sheet_px(mx, my):
        p = c * (R @ np.array([mx, my])) + t
        sx, sy = p2s(p[0], p[1])
        return sx - total_off[0], sy - total_off[1]

    positions = {
        inc["incident_id"]: _incident_sheet_px(
            inc, sheet, frag_by_handle, p2s, total_off, model_to_sheet_px,
        )
        for inc in incidents
    }

    # Overview: crop to the building area (incident span), not stray APS fragments.
    cen_px = list(positions.values())
    cxs = [p[0] for p in cen_px]; cys = [p[1] for p in cen_px]
    span = max(max(cxs) - min(cxs), max(cys) - min(cys), 1)
    margin = span * 0.18
    ox0 = max(0, int(min(cxs) - margin)); oy0 = max(0, int(min(cys) - margin))
    ox1 = min(sheet.width, int(max(cxs) + margin)); oy1 = min(sheet.height, int(max(cys) + margin))
    overview_src = sheet.crop((ox0, oy0, ox1, oy1))

    overview_path = OUT / "aps_plan_overview.jpg"
    prepare_annex(overview_src, overview_path)

    groups = group_incidents_by_px(
        incidents, positions, max_per=MAX_PER_DETAIL, radius_px=CLUSTER_RADIUS_PX,
    )
    detail_pages: list[dict] = []
    label_off = 0

    for gi, group in enumerate(groups):
        points: list[tuple[float, float, str, str]] = []
        px_pts: list[tuple[float, float]] = []
        ids: list[str] = []
        for j, inc in enumerate(group):
            cx, cy = positions[inc["incident_id"]]
            lbl = f"C-{label_off + j + 1:03d}"
            versus = _layer_versus(inc)
            points.append((cx, cy, lbl, versus))
            px_pts.append((cx, cy))
            ids.append(inc["incident_id"])

        zoom, (zox, zoy) = detail_crop(sheet, px_pts, pad_frac=0.45, min_frac=0.18)
        adj = [(cx - zox, cy - zoy, lbl, versus) for cx, cy, lbl, versus in points]
        marked = draw_clash_markers(zoom, adj, radius=max(4, zoom.width // 350))
        marked = crop_to_aspect(marked, 772 / 576)
        marked = fit_annex_size(marked)
        path = OUT / f"aps_detail_{gi + 1:02d}.jpg"
        marked.save(path, "JPEG", quality=92, dpi=(200, 200))

        detail_pages.append({
            "path": str(path),
            "group": gi + 1,
            "n": len(group),
            "label_from": label_off + 1,
            "label_to": label_off + len(group),
            "incident_ids": ids,
            "layer_pairs": _group_layer_pairs(group),
        })
        label_off += len(group)

    index = {
        "overview": str(overview_path),
        "detail_pages": detail_pages,
        "n_incidents": len(incidents),
        "n_detail_pages": len(detail_pages),
    }
    (OUT / "aps_overlay_index.json").write_text(json.dumps(index, indent=2))
    print(f"[overlay] overview -> {overview_path}  ({overview_src.size[0]}x{overview_src.size[1]} crop)")
    print(f"[overlay] {len(detail_pages)} detail page(s)")


if __name__ == "__main__":
    main()
