"""FPDF helpers with a Unicode-capable font when available."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from fpdf import FPDF

_FONT_FAMILY = "DuplaSans"


@lru_cache(maxsize=1)
def _unicode_font_paths() -> tuple[str, str] | None:
    bundled = Path(__file__).resolve().parent / "fonts"
    candidates: list[tuple[str, str]] = []
    if bundled.exists():
        candidates.append(
            (
                str(bundled / "DejaVuSans.ttf"),
                str(bundled / "DejaVuSans-Bold.ttf"),
            )
        )
    candidates.extend(
        [
            (
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ),
            (
                "/Library/Fonts/Arial Unicode.ttf",
                "/Library/Fonts/Arial Unicode.ttf",
            ),
            (
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            ),
        ]
    )
    for regular, bold in candidates:
        if os.path.isfile(regular):
            bold_path = bold if os.path.isfile(bold) else regular
            return regular, bold_path
    return None


def create_unicode_pdf() -> tuple[FPDF, str]:
    """Return an FPDF instance and font family name safe for Spanish/Unicode text."""
    pdf = FPDF()
    paths = _unicode_font_paths()
    if paths is not None:
        regular, bold = paths
        pdf.add_font(_FONT_FAMILY, "", regular)
        pdf.add_font(_FONT_FAMILY, "B", bold)
        return pdf, _FONT_FAMILY
    return pdf, "Helvetica"
