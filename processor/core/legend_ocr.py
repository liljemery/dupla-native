"""
Legend / title-block OCR for rendered plan pages.

APS Model Derivative extracts the legend as *notation* (text properties) but
never measures it and never tells the budget engine which floor or view a sheet
belongs to. A senior estimator, before quantifying, reads the legend ("cuadro"
/ "leyenda" / "rótulo") to learn: which floor the sheet is (NIVEL 2, N+2.80,
PISO 1) and which view it is (planta, corte, sección, elevación, ISOMETRÍA,
detalle). Those two facts decide how the measurements are interpreted.

This module runs Tesseract OCR over the already-rendered PNG of each page and
parses those two facts. It is deliberately defensive: if pytesseract or the
Tesseract binary are not installed it logs a warning and returns empty results
so the pipeline degrades gracefully instead of crashing.

Install (Windows, no Docker):
    pip install pytesseract pillow
    # plus the Tesseract engine + Spanish data:
    #   https://github.com/UB-Mannheim/tesseract/wiki   (incluye 'spa')
    # If tesseract.exe is not on PATH, set TESSERACT_CMD=C:\\path\\to\\tesseract.exe
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("dupla.legend_ocr")

# Floor: capture the whole phrase so it still matches the pipeline's level-label
# pattern (which keys on words like "nivel"/"piso"/"planta"/"n+").
_FLOOR_RE = re.compile(
    r"((?:nivel|piso|planta|n\.?p\.?t\.?|n)\s*[:\-]?\s*[+\-]?\s*\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_FLOOR_VALUE_RE = re.compile(r"[+\-]?\d+(?:\.\d+)?")

# View: the specialised plan views a civil engineer distinguishes. "isometría"
# is included explicitly because isometric sheets (sanitario/eléctrico) must be
# read very differently from a plan view.
_VIEW_RE = re.compile(
    r"\b(planta|corte|secci[oó]n|elevaci[oó]n|fachada|isometr[ií]a|detalle|montante|columna)\b",
    re.IGNORECASE,
)

_VIEW_CANON = {
    "seccion": "seccion", "sección": "seccion",
    "elevacion": "elevacion", "elevación": "elevacion",
    "isometria": "isometria", "isometría": "isometria",
}


def _tesseract_ready() -> bool:
    try:
        import pytesseract  # noqa: F401
    except Exception:
        logger.warning(
            "pytesseract not installed — legend OCR disabled. "
            "pip install pytesseract pillow + install the Tesseract engine."
        )
        return False
    cmd = (os.getenv("TESSERACT_CMD") or "").strip()
    if cmd:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = cmd
    return True


def read_legend(page_png: Path) -> dict[str, Any]:
    """OCR one rendered page and parse legend floor + view.

    This does NOT measure geometry; it assigns the *semantics* (floor, view) of
    the sheet so downstream takeoffs land on the right level and are interpreted
    against the right view.
    """
    import pytesseract
    from PIL import Image

    lang = (os.getenv("DUPLA_OCR_LANG") or "spa").strip() or "spa"
    try:
        text = pytesseract.image_to_string(Image.open(page_png), lang=lang)
    except pytesseract.TesseractError:
        # Language pack missing — retry with the default English model.
        text = pytesseract.image_to_string(Image.open(page_png))

    floor_match = _FLOOR_RE.search(text)
    floor_label = re.sub(r"\s+", " ", floor_match.group(1)).strip().upper() if floor_match else None
    floor_value = None
    if floor_label:
        value_match = _FLOOR_VALUE_RE.search(floor_label)
        if value_match:
            try:
                floor_value = float(value_match.group(0).replace(" ", ""))
            except ValueError:
                floor_value = None

    view_match = _VIEW_RE.search(text)
    view = None
    if view_match:
        raw = view_match.group(1).lower()
        view = _VIEW_CANON.get(raw, raw)

    return {
        "page": page_png.name,
        "floor_label": floor_label,
        "floor_value": floor_value,
        "view": view,
        "legend_chars": len(text),
    }


def build_page_map(pages_dir: str) -> dict[str, dict[str, Any]]:
    """Return {page_filename: {floor_label, floor_value, view, ...}} for all pages.

    Empty (and harmless) when Tesseract is unavailable.
    """
    if not _tesseract_ready():
        return {}
    page_map: dict[str, dict[str, Any]] = {}
    for png in sorted(Path(pages_dir).glob("*.png")):
        try:
            page_map[png.name] = read_legend(png)
        except Exception:
            logger.warning("Legend OCR failed for %s", png.name, exc_info=True)
            page_map[png.name] = {"page": png.name, "floor_label": None, "view": None, "error": True}
    return page_map


def inject_floor_markers(cad_facts: dict[str, Any], page_map: dict[str, dict[str, Any]]) -> int:
    """Feed legend-derived floor labels into cad_facts level markers.

    The pipeline names levels from ``inventory_hints.level_markers``; by adding
    the OCR floor labels there, levels get named from the legend ("NIVEL 2")
    instead of the generic "level_01". Returns how many markers were added.
    """
    if not page_map:
        return 0
    hints = cad_facts.setdefault("inventory_hints", {})
    markers = hints.setdefault("level_markers", [])
    existing = {
        str(m.get("content", "") if isinstance(m, dict) else m).strip().upper()
        for m in markers
    }
    added = 0
    for entry in page_map.values():
        label = (entry.get("floor_label") or "").strip()
        if not label or label.upper() in existing:
            continue
        markers.append({"content": label, "source": "legend_ocr", "page": entry.get("page")})
        existing.add(label.upper())
        added += 1
    return added
