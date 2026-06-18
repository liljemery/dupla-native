"""Real APS PDF derivative plan images with clash overlays."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

logger = logging.getLogger(__name__)
coord_logger = logging.getLogger("COORD")

APS_MD_BASE = "https://developer.api.autodesk.com/modelderivative/v2/designdata"
PDF_FORMAT = {
    "type": "pdf",
    "advanced": {
        "exportFileStructure": "single",
        "exportColor": True,
        "exportPaperSpace": False,
    },
}


async def get_plan_image_for_file(
    filename: str,
    incidents_for_file: list[dict[str, Any]],
    job_output_dir: str,
    aps_token: str,
    elements_for_file: list[dict[str, Any]] | None = None,
) -> str | None:
    """Build one rendered real-plan JPEG for a DWG, or return None on failure."""
    pages = await get_plan_images_for_file(
        filename=filename,
        incidents_for_file=incidents_for_file,
        job_output_dir=job_output_dir,
        aps_token=aps_token,
        elements_for_file=elements_for_file,
    )
    return pages[0] if pages else None


async def get_plan_images_for_file(
    filename: str,
    incidents_for_file: list[dict[str, Any]],
    job_output_dir: str,
    aps_token: str,
    elements_for_file: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Build overview + grouped detail JPEG pages for one DWG."""
    try:
        return await asyncio.wait_for(
            _get_plan_images_for_file(
                filename=filename,
                incidents_for_file=incidents_for_file,
                job_output_dir=job_output_dir,
                aps_token=aps_token,
                elements_for_file=elements_for_file,
            ),
            timeout=120,
        )
    except Exception as exc:
        logger.warning("Plan image skipped for %s: %s", filename, exc)
        return []


async def _get_plan_images_for_file(
    *,
    filename: str,
    incidents_for_file: list[dict[str, Any]],
    job_output_dir: str,
    aps_token: str,
    elements_for_file: list[dict[str, Any]] | None,
) -> list[str]:
    from app.services.clash_reports.aps_viewer_renderer import (
        engine_available,
        render_plan_pages,
    )

    output_dir   = Path(job_output_dir)
    cache_dir    = output_dir / "cache"
    rendered_dir = output_dir / "plan_rendered"
    stem         = _safe_stem(filename)

    record = get_urn_from_cache(str(cache_dir), filename)
    if not record:
        logger.warning("No APS URN found in cache for %s", filename)
        return []
    model_urn, _record_dir, _object_key = record

    # Build the clash list expected by the viewer engine
    clashes = _build_clash_list(incidents_for_file)

    # ── Vía A: headless APS Viewer (SVF2 → real annotated plan) ──────────────
    if engine_available():
        loop = asyncio.get_event_loop()
        pages = await loop.run_in_executor(
            None,
            lambda: render_plan_pages(
                urn=model_urn,
                aps_token=aps_token,
                clashes=clashes,
                output_dir=str(rendered_dir),
                stem=stem,
            ),
        )
        if pages:
            logger.info("viewer-engine rendered %d page(s) for %s", len(pages), filename)
            return pages
        logger.warning("viewer-engine returned no pages for %s — falling back to PDF path", filename)

    # ── Vía B fallback: APS PDF derivative (may be unsupported for DWG) ──────
    derivative_urn = _read_cached_pdf_urn(_record_dir)
    if not derivative_urn:
        derivative_urn = await _find_pdf_derivative_in_manifest(aps_token, model_urn)
    if not derivative_urn:
        try:
            await translate_to_pdf(aps_token, model_urn, _object_key or filename)
            derivative_urn = await wait_for_pdf_derivative(aps_token, model_urn, timeout_seconds=90)
        except Exception as exc:
            logger.warning("PDF derivative translate failed for %s: %s", filename, exc)
    if not derivative_urn:
        logger.warning("No plan images available for %s", filename)
        return []

    _write_cached_pdf_urn(_record_dir, derivative_urn)
    pdf_path      = output_dir / "plan_pdfs"  / f"{stem}.pdf"
    raster_path   = output_dir / "plan_jpegs" / f"{stem}.jpg"
    rendered_path = rendered_dir / f"{stem}_plan.jpg"

    await download_pdf_derivative(aps_token, model_urn, derivative_urn, str(pdf_path))
    _, (w_px, h_px) = rasterize_pdf_to_jpeg(str(pdf_path), str(raster_path), dpi=300)
    transform = compute_transform_pdf_to_clash_coords(
        str(pdf_path), w_px, h_px, elements_for_file or [],
    )
    draw_clash_overlays(str(raster_path), incidents_for_file, transform, str(rendered_path))
    return [str(rendered_path)]


def _build_clash_list(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert incident dicts to the flat format expected by viewer-engine."""
    result = []
    for inc in incidents:
        rep    = inc.get("representative_conflict") or inc
        bounds = rep.get("plan_intersection_bounds_mm") or rep.get("bounds_mm")
        centroid = rep.get("plan_intersection_centroid_mm") or rep.get("centroid_mm") or inc.get("centroid_mm")
        if not bounds or len(bounds) != 4:
            continue
        clash_id = inc.get("incident_id") or rep.get("element_id_a") or f"clash_{len(result)}"
        coord_logger.info(
            "COORD_VIEWER_INPUT clash_id=%s bounds_mm=%s centroid_mm=%s",
            clash_id,
            bounds,
            centroid,
        )
        result.append({
            "bounds_mm":   bounds,
            "centroid_mm": centroid,
            "clash_type":  str(rep.get("clash_type") or "HARD"),
        })
    return result


async def translate_to_pdf(token: str, urn: str, object_key: str) -> dict[str, Any]:
    body = {"input": {"urn": urn}, "output": {"formats": [PDF_FORMAT]}}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{APS_MD_BASE}/job",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "x-ads-force": "true",
            },
            json=body,
        )
        r.raise_for_status()
        data = r.json()
    data.setdefault("object_key", object_key)
    return data


async def wait_for_pdf_derivative(
    token: str,
    urn: str,
    timeout_seconds: int = 300,
    poll_interval: int = 10,
) -> str | None:
    start = time.monotonic()
    while time.monotonic() - start <= timeout_seconds:
        manifest = await _get_manifest(token, urn)
        derivative_urn = _find_pdf_child_urn(manifest)
        if derivative_urn:
            return derivative_urn
        status = _pdf_derivative_status(manifest)
        logger.info(
            "APS PDF derivative poll urn=%s status=%s elapsed=%ss",
            urn[:24],
            status or "missing",
            int(time.monotonic() - start),
        )
        if status in {"failed", "timeout"}:
            return None
        await asyncio.sleep(max(1, poll_interval))
    return None


async def download_pdf_derivative(
    token: str,
    model_urn: str,
    derivative_urn: str,
    output_path: str,
) -> str:
    url = f"{APS_MD_BASE}/{model_urn}/derivative/{quote(derivative_urn, safe='')}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
        return str(path)


def rasterize_pdf_to_jpeg(
    pdf_path: str,
    output_path: str,
    dpi: int = 300,
    page_index: int = 0,
) -> tuple[str, tuple[int, int]]:
    from pdf2image import convert_from_path

    effective_dpi = _effective_dpi(pdf_path, dpi, page_index)
    images = convert_from_path(
        pdf_path,
        dpi=effective_dpi,
        first_page=page_index + 1,
        last_page=page_index + 1,
        fmt="jpeg",
        jpegopt={"quality": 95, "progressive": True},
    )
    if not images:
        raise ValueError(f"No pages extracted from {pdf_path}")
    img = images[0]
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=95, dpi=(effective_dpi, effective_dpi))
    return output_path, img.size


def compute_transform_pdf_to_clash_coords(
    pdf_path: str,
    raster_width_px: int,
    raster_height_px: int,
    sample_elements: list[dict[str, Any]],
) -> dict[str, Any]:
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    pdf_w_pt = float(page.mediabox.width)
    pdf_h_pt = float(page.mediabox.height)
    pt_to_mm = 25.4 / 72
    pdf_w_mm = pdf_w_pt * pt_to_mm
    pdf_h_mm = pdf_h_pt * pt_to_mm
    scale_x = raster_width_px / pdf_w_mm if pdf_w_mm else 1.0
    scale_y = raster_height_px / pdf_h_mm if pdf_h_mm else 1.0
    log = [
        f"PDF {pdf_w_pt:.2f}x{pdf_h_pt:.2f}pt",
        f"Raster {raster_width_px}x{raster_height_px}px",
        f"Scale {scale_x:.6f},{scale_y:.6f}px/mm",
    ]
    return {
        "pdf_w_pt": pdf_w_pt,
        "pdf_h_pt": pdf_h_pt,
        "pdf_w_mm": pdf_w_mm,
        "pdf_h_mm": pdf_h_mm,
        "scale_x": scale_x,
        "scale_y": scale_y,
        "verified": bool(sample_elements),
        "verification_log": log,
    }


def draw_clash_overlays(
    raster_path: str,
    incidents: list[dict[str, Any]],
    transform: dict[str, Any],
    output_path: str,
) -> str:
    img = Image.open(raster_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    scale_x = float(transform["scale_x"])
    scale_y = float(transform["scale_y"])
    img_h = img.size[1]

    def mm_to_px(x_mm, y_mm):
        return int(float(x_mm) * scale_x), int(img_h - float(y_mm) * scale_y)

    font_size_px = max(12, int(10 / 72 * 300))
    try:
        font_bold = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size_px)
    except Exception:
        font_bold = ImageFont.load_default()

    colors = {
        "critical": (220, 50, 50, 140),
        "high": (220, 140, 50, 130),
        "default": (50, 100, 220, 110),
    }
    min_px = 40
    clash_index = 0
    for inc in incidents:
        rep = inc.get("representative_conflict") or inc
        bounds = rep.get("plan_intersection_bounds_mm") or rep.get("bounds_mm")
        centroid = rep.get("plan_intersection_centroid_mm") or rep.get("centroid_mm")
        if not bounds or len(bounds) != 4:
            continue
        clash_index += 1
        clash_id = f"C-{clash_index:03d}"
        color = colors.get(str(inc.get("priority") or "default"), colors["default"])
        border = (color[0], color[1], color[2], 255)
        x0, y0 = mm_to_px(bounds[0], bounds[1])
        x1, y1 = mm_to_px(bounds[2], bounds[3])
        if y0 > y1:
            y0, y1 = y1, y0
        if x0 > x1:
            x0, x1 = x1, x0
        if x1 - x0 < min_px:
            cx = (x0 + x1) // 2
            x0, x1 = cx - min_px // 2, cx + min_px // 2
        if y1 - y0 < min_px:
            cy = (y0 + y1) // 2
            y0, y1 = cy - min_px // 2, cy + min_px // 2
        draw.rectangle([x0, y0, x1, y1], fill=color)
        draw.rectangle([x0, y0, x1, y1], outline=border, width=4)
        bbox = font_bold.getbbox(clash_id)
        label_w, label_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        label_top = max(0, y0 - label_h - 8)
        draw.rectangle([x0, label_top, x0 + label_w + 8, label_top + label_h + 8], fill=border)
        draw.text((x0 + 4, label_top + 3), clash_id, fill=(255, 255, 255, 255), font=font_bold)
        if centroid and len(centroid) == 2:
            cx, cy = mm_to_px(centroid[0], centroid[1])
            r = 20
            draw.line([(cx - r, cy), (cx + r, cy)], fill=border, width=3)
            draw.line([(cx, cy - r), (cx, cy + r)], fill=border, width=3)

    result = Image.alpha_composite(img, overlay).convert("RGB")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, "JPEG", quality=92, dpi=(300, 300))
    return output_path


def group_incidents_for_detail_pages(
    incidents: list[dict[str, Any]],
    *,
    max_per_page: int = 10,
    radius_mm: float = 3000.0,
) -> list[list[dict[str, Any]]]:
    """Group clashes by centroid proximity for readable detail pages."""
    candidates = [inc for inc in incidents if _incident_bounds(inc)]
    if not candidates:
        return []

    remaining = sorted(candidates, key=lambda inc: (_incident_centroid(inc)[0], _incident_centroid(inc)[1]))
    groups: list[list[dict[str, Any]]] = []
    while remaining:
        group = [remaining.pop(0)]
        changed = True
        while changed and len(group) < max_per_page:
            changed = False
            gcx = sum(_incident_centroid(inc)[0] for inc in group) / len(group)
            gcy = sum(_incident_centroid(inc)[1] for inc in group) / len(group)
            nearest_idx = None
            nearest_dist = radius_mm
            for idx, inc in enumerate(remaining):
                cx, cy = _incident_centroid(inc)
                dist = ((cx - gcx) ** 2 + (cy - gcy) ** 2) ** 0.5
                if dist <= nearest_dist:
                    nearest_idx = idx
                    nearest_dist = dist
            if nearest_idx is not None:
                group.append(remaining.pop(nearest_idx))
                changed = True
        groups.append(group)
    return groups


def draw_clash_detail_page(
    raster_path: str,
    incidents: list[dict[str, Any]],
    transform: dict[str, Any],
    output_path: str,
    *,
    title: str,
) -> str:
    """Draw overlays on the full raster, then crop around one clash group."""
    temp_path = str(Path(output_path).with_suffix(".full.jpg"))
    draw_clash_overlays(raster_path, incidents, transform, temp_path)
    img = Image.open(temp_path).convert("RGB")
    crop = _detail_crop_box(img.size, incidents, transform)
    detail = img.crop(crop)
    _draw_page_title(detail, title)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    detail.save(output_path, "JPEG", quality=92, dpi=(300, 300))
    try:
        Path(temp_path).unlink()
    except OSError:
        pass
    return output_path


def get_urn_from_cache(cache_dir: str, filename: str) -> tuple[str, Path, str | None] | None:
    basename = Path(filename).name
    root = Path(cache_dir)
    candidates = []
    if root.exists():
        candidates.extend(root.rglob("*.json"))
    for extra in (root.parent / "raw.json", root.parent / "outputs" / "raw.json"):
        if extra.is_file():
            candidates.append(extra)
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        record = _find_urn_record(data, basename)
        if record:
            urn, object_key = record
            return urn, path.parent, object_key
    return None


def _save_overview(raster_path: str, output_path: str, filename: str) -> None:
    img = Image.open(raster_path).convert("RGB")
    _draw_page_title(img, f"{filename} - Overview")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=92, dpi=(300, 300))


def _draw_page_title(img: Image.Image, title: str) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", max(24, int(img.width * 0.012)))
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), title, font=font)
    h = bbox[3] - bbox[1] + 24
    draw.rectangle([0, 0, img.width, h], fill=(26, 26, 26, 220))
    draw.text((16, 12), title, fill=(255, 255, 255, 255), font=font)


def _detail_crop_box(
    image_size: tuple[int, int],
    incidents: list[dict[str, Any]],
    transform: dict[str, Any],
) -> tuple[int, int, int, int]:
    img_w, img_h = image_size
    scale_x = float(transform["scale_x"])
    scale_y = float(transform["scale_y"])

    def mm_to_px(x_mm, y_mm):
        return int(float(x_mm) * scale_x), int(img_h - float(y_mm) * scale_y)

    xs: list[int] = []
    ys: list[int] = []
    for inc in incidents:
        bounds = _incident_bounds(inc)
        if not bounds:
            continue
        x0, y0 = mm_to_px(bounds[0], bounds[1])
        x1, y1 = mm_to_px(bounds[2], bounds[3])
        xs.extend([x0, x1])
        ys.extend([y0, y1])
    if not xs:
        return (0, 0, img_w, img_h)

    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    group_w = max(x1 - x0, 1)
    group_h = max(y1 - y0, 1)
    pad = int(max(group_w, group_h, min(img_w, img_h) * 0.12))
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(img_w, x1 + pad)
    y1 = min(img_h, y1 + pad)

    min_w = min(img_w, 1800)
    min_h = min(img_h, 1300)
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    if x1 - x0 < min_w:
        x0, x1 = cx - min_w // 2, cx + min_w // 2
    if y1 - y0 < min_h:
        y0, y1 = cy - min_h // 2, cy + min_h // 2
    if x0 < 0:
        x1 -= x0
        x0 = 0
    if y0 < 0:
        y1 -= y0
        y0 = 0
    if x1 > img_w:
        x0 -= x1 - img_w
        x1 = img_w
    if y1 > img_h:
        y0 -= y1 - img_h
        y1 = img_h
    return max(0, x0), max(0, y0), min(img_w, x1), min(img_h, y1)


def _incident_bounds(inc: dict[str, Any]) -> list[Any] | None:
    rep = inc.get("representative_conflict") or inc
    bounds = rep.get("plan_intersection_bounds_mm") or rep.get("bounds_mm")
    return list(bounds) if isinstance(bounds, (list, tuple)) and len(bounds) == 4 else None


def _incident_centroid(inc: dict[str, Any]) -> tuple[float, float]:
    rep = inc.get("representative_conflict") or inc
    centroid = rep.get("plan_intersection_centroid_mm") or rep.get("centroid_mm")
    if isinstance(centroid, (list, tuple)) and len(centroid) == 2:
        return float(centroid[0]), float(centroid[1])
    bounds = _incident_bounds(inc) or [0, 0, 0, 0]
    return (float(bounds[0]) + float(bounds[2])) / 2, (float(bounds[1]) + float(bounds[3])) / 2


async def _find_pdf_derivative_in_manifest(token: str, urn: str) -> str | None:
    return _find_pdf_child_urn(await _get_manifest(token, urn))


async def _get_manifest(token: str, urn: str) -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(f"{APS_MD_BASE}/{urn}/manifest", headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else None


def _find_pdf_child_urn(manifest: dict[str, Any] | None) -> str | None:
    for derivative in (manifest or {}).get("derivatives") or []:
        if str(derivative.get("outputType") or "").lower() != "pdf":
            continue
        if str(derivative.get("status") or "").lower() != "success":
            continue
        for node in _walk_manifest(derivative):
            urn = node.get("urn")
            markers = [str(node.get(k) or "").lower() for k in ("role", "type", "mime", "name", "urn")]
            if urn and any("pdf" in marker for marker in markers):
                return str(urn)
    return None


def _pdf_derivative_status(manifest: dict[str, Any] | None) -> str | None:
    for derivative in (manifest or {}).get("derivatives") or []:
        if str(derivative.get("outputType") or "").lower() == "pdf":
            return str(derivative.get("status") or "").lower()
    return None


def _walk_manifest(node):
    if isinstance(node, dict):
        yield node
        for child in node.get("children") or []:
            yield from _walk_manifest(child)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_manifest(item)


def _read_cached_pdf_urn(record_dir: Path) -> str | None:
    path = record_dir / "pdf_derivative.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    urn = data.get("pdf_derivative_urn")
    status = data.get("pdf_derivative_status")
    return str(urn) if urn and status == "success" else None


def _write_cached_pdf_urn(record_dir: Path, derivative_urn: str) -> None:
    payload = {
        "pdf_derivative_urn": derivative_urn,
        "pdf_derivative_status": "success",
        "pdf_generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (record_dir / "pdf_derivative.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _cache_name_matches(name: str, basename: str) -> bool:
    """Match cache object_name to incident filename (cache adds _<hash> before .dwg)."""
    if not name or not basename:
        return False
    cache_base = Path(name).name
    want = Path(basename).name
    if cache_base == want:
        return True
    want_stem = Path(want).stem
    cache_stem = Path(cache_base).stem
    if cache_stem == want_stem:
        return True
    # e.g. 2208-Serena18-ID-Base_9911d70e0302 vs 2208-Serena18-ID-Base.dwg
    return cache_stem.startswith(want_stem + "_") or want_stem.startswith(cache_stem + "_")


def _find_urn_record(data: Any, basename: str) -> tuple[str, str | None] | None:
    if isinstance(data, dict):
        name = str(data.get("dwg") or data.get("filename") or data.get("object_name") or "")
        nested = data.get("data")
        if name and _cache_name_matches(name, basename):
            payload = nested if isinstance(nested, dict) else data
            urn = payload.get("urn") if isinstance(payload, dict) else None
            object_key = payload.get("object_name") if isinstance(payload, dict) else name
            if isinstance(urn, str) and urn:
                return urn, str(object_key or name)
        if nested is not None:
            found = _find_urn_record(nested, basename)
            if found:
                return found
        for value in data.values():
            found = _find_urn_record(value, basename)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_urn_record(item, basename)
            if found:
                return found
    return None


def _safe_stem(filename: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in Path(filename).stem) or "plan"


def _effective_dpi(pdf_path: str, requested_dpi: int, page_index: int) -> int:
    reader = PdfReader(pdf_path)
    page = reader.pages[page_index]
    width_inches = float(page.mediabox.width) / 72
    if width_inches <= 0:
        return requested_dpi
    return max(150, min(requested_dpi, int(10000 / width_inches)))
