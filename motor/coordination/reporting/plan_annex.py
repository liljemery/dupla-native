"""Prepare literal APS plan annex images for GA-FO-08 PDF pages."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

# Letter-landscape annex frame aspect (points): ~772 x 576
ANNEX_ASPECT = 772.0 / 576.0
ANNEX_WIDTH_PX = 2400
MARKER = (210, 30, 120)  # magenta revision markup


def autocrop_content(img: Image.Image, *, threshold: int = 252, margin: int = 24) -> tuple[Image.Image, tuple[int, int]]:
    """Trim empty white margins. Returns (crop, (ox, oy))."""
    gray = img.convert("L")
    mask = gray.point(lambda x: 0 if x > threshold else 255, "1")
    bbox = mask.getbbox()
    if not bbox:
        return img, (0, 0)
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - margin); y0 = max(0, y0 - margin)
    x1 = min(img.width, x1 + margin); y1 = min(img.height, y1 + margin)
    return img.crop((x0, y0, x1, y1)), (x0, y0)


def normalize_plan_colors(img: Image.Image) -> Image.Image:
    """Mute garish APS layer colours → readable plan (dark lines on white)."""
    gray = ImageOps.grayscale(img.convert("RGB"))
    rgb = Image.merge("RGB", (gray, gray, gray))
    rgb = ImageEnhance.Contrast(rgb).enhance(1.15)
    rgb = ImageEnhance.Brightness(rgb).enhance(1.03)
    return rgb


def crop_sheet_from_diag(img: Image.Image, diag: dict, *, margin: int = 32) -> tuple[Image.Image, tuple[int, int]]:
    """Crop to the APS sheet region reported by capture diag. Returns (crop, (ox, oy))."""
    sb = diag.get("screenBBox") or {}
    x0 = max(0, int(math.floor(sb.get("minX", 0))) - margin)
    y0 = max(0, int(math.floor(sb.get("minY", 0))) - margin)
    x1 = min(img.width, int(math.ceil(sb.get("maxX", img.width))) + margin)
    y1 = min(img.height, int(math.ceil(sb.get("maxY", img.height))) + margin)
    if x1 <= x0 or y1 <= y0:
        return img, (0, 0)
    return img.crop((x0, y0, x1, y1)), (x0, y0)


def crop_to_aspect(img: Image.Image, aspect: float) -> Image.Image:
    """Center-crop to target width/height aspect ratio."""
    w, h = img.size
    current = w / h
    if current > aspect:
        new_w = int(h * aspect)
        x0 = (w - new_w) // 2
        return img.crop((x0, 0, x0 + new_w, h))
    new_h = int(w / aspect)
    y0 = (h - new_h) // 2
    return img.crop((0, y0, w, y0 + new_h))


def fit_annex_size(img: Image.Image, *, width: int = ANNEX_WIDTH_PX) -> Image.Image:
    h = int(width / ANNEX_ASPECT)
    return img.resize((width, h), Image.Resampling.LANCZOS)


def prepare_annex(img: Image.Image, out_path: str | Path) -> Image.Image:
    """Normalize colours, enforce aspect, resize for full-bleed PDF annex."""
    img = normalize_plan_colors(img)
    img = crop_to_aspect(img, ANNEX_ASPECT)
    img = fit_annex_size(img)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=92, dpi=(200, 200))
    return img


def _font(size: int):
    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_clash_markers(
    img: Image.Image,
    points: list[tuple[float, float, str, str]],
    *,
    radius: int | None = None,
) -> Image.Image:
    """Magenta dot + C-NNN label + layer-versus sublabel."""
    out = img.copy()
    draw = ImageDraw.Draw(out, "RGBA")
    r = radius or max(5, img.width // 400)
    font = _font(max(13, img.width // 180))
    subfont = _font(max(10, img.width // 220))
    col = MARKER + (255,)
    for cx, cy, label, versus in points:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=2)
        draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=col)
        tx, ty = cx + r + 3, cy - r - 2
        draw.text((tx, ty), label, fill=col, font=font)
        if versus:
            draw.text((tx, ty + font.size + 1), versus, fill=col, font=subfont)
    return out


def linework_score(img: Image.Image, cx: float, cy: float, *, radius: int = 14) -> int:
    """Lower is darker / closer to drawn linework (0 = on line)."""
    gray = img.convert("L")
    w, h = gray.size
    cx_i, cy_i = int(cx), int(cy)
    vals: list[int] = []
    for dy in range(-radius, radius + 1, 3):
        for dx in range(-radius, radius + 1, 3):
            x, y = cx_i + dx, cy_i + dy
            if 0 <= x < w and 0 <= y < h:
                vals.append(gray.getpixel((x, y)))
    return min(vals) if vals else 255


def snap_to_linework(
    img: Image.Image,
    cx: float,
    cy: float,
    *,
    radius: int = 100,
) -> tuple[float, float]:
    """Nudge marker onto nearest dark pixel (plan linework)."""
    gray = img.convert("L")
    w, h = gray.size
    best = (cx, cy)
    best_v = linework_score(img, cx, cy, radius=8)
    steps = max(8, radius // 8)
    for r in range(4, radius + 1, steps):
        for k in range(24):
            ang = 2 * math.pi * k / 24
            x = int(cx + r * math.cos(ang))
            y = int(cy + r * math.sin(ang))
            if 0 <= x < w and 0 <= y < h:
                v = gray.getpixel((x, y))
                if v < best_v:
                    best_v = v
                    best = (float(x), float(y))
    return best


def detail_crop(
    img: Image.Image,
    points: list[tuple[float, float]],
    *,
    pad_frac: float = 0.35,
    min_frac: float = 0.22,
) -> tuple[Image.Image, tuple[int, int]]:
    """Crop a detail view around clash centroids. Returns (crop, (ox, oy))."""
    if not points:
        return img, (0, 0)
    xs = [p[0] for p in points]; ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    span = max(x1 - x0, y1 - y0, 1)
    pad = span * pad_frac
    x0 -= pad; x1 += pad; y0 -= pad; y1 += pad
    min_w = img.width * min_frac
    min_h = img.height * min_frac
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if x1 - x0 < min_w:
        x0, x1 = cx - min_w / 2, cx + min_w / 2
    if y1 - y0 < min_h:
        y0, y1 = cy - min_h / 2, cy + min_h / 2
    ox = max(0, int(x0)); oy = max(0, int(y0))
    x1 = min(img.width, int(x1)); y1 = min(img.height, int(y1))
    return img.crop((ox, oy, x1, y1)), (ox, oy)
