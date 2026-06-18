"""Overlay intra-ARQ clash boxes onto the real APS 2D-sheet screenshot.

Frames:
  clash/model meters  --(similarity c,R,t fitted from matched handle centers)-->  APS paper units
  APS paper units      --(linear map from capture diag modelBBox<->screenBBox)-->  screenshot pixels

The similarity is fit + RANSAC here from fragment-dump handle centers vs our
sanitized geometry handle centers (handles match 1:1).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = Path("var/coord_outputs/serena18_run/arq_intra_clash")
GEOM = Path("var/coord_outputs/serena18_run/sanitized_geometry/ARQ.sanitized.geometry.json")
SHEET_PNG = OUT / "aps_plan.png"
FRAG = OUT / "aps_fragments_2d.json"
CLASH = OUT / "clash_results.json"
DIAG = OUT / "aps_plan.png.diag.json"

SEV = {"critical": (220, 38, 38), "major": (230, 110, 0), "minor": (30, 110, 220)}


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


def paper_to_pixel_fn(diag):
    mb = diag["modelBBox"]; sbx = diag["screenBBox"]
    x0, x1 = mb["min"]["x"], mb["max"]["x"]
    y0, y1 = mb["min"]["y"], mb["max"]["y"]
    sx0, sx1 = sbx["minX"], sbx["maxX"]
    sy0, sy1 = sbx["minY"], sbx["maxY"]

    def f(px, py):
        # paper x grows -> screen x grows; paper y grows -> screen y shrinks (flip)
        u = (px - x0) / (x1 - x0)
        v = (py - y0) / (y1 - y0)
        return sx0 + u * (sx1 - sx0), sy1 - v * (sy1 - sy0)

    return f


def main():
    c, R, t = fit_model_to_paper()
    diag = json.load(open(DIAG))
    p2px = paper_to_pixel_fn(diag)

    def model_to_pixel(mx, my):
        p = c * (R @ np.array([mx, my])) + t
        return p2px(p[0], p[1])

    img = Image.open(SHEET_PNG).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 26)
    except Exception:
        font = ImageFont.load_default()

    cl = json.load(open(CLASH))
    for inc in cl["incidents"]:
        b = inc["bounds_m"]
        col = SEV.get(inc["severity"], (220, 38, 38))
        corners = [model_to_pixel(b[0], b[1]), model_to_pixel(b[2], b[1]),
                   model_to_pixel(b[2], b[3]), model_to_pixel(b[0], b[3])]
        draw.polygon(corners, outline=col + (255,), width=4)
        cx = sum(p[0] for p in corners) / 4; cy = sum(p[1] for p in corners) / 4
        n = inc["incident_id"].split("-")[-1]
        draw.text((cx + 6, cy - 30), n, fill=col + (255,), font=font)

    out = OUT / "aps_plan_annotated.png"
    img.save(out)
    print(f"[overlay] saved -> {out}  ({len(cl['incidents'])} incidents)")


if __name__ == "__main__":
    main()
