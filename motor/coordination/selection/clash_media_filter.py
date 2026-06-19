"""Filtros de medios para el schedule de clash NASAS (sin dependencias pesadas)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ClashMediaSkipArgs(Protocol):
    skip_dwg: bool
    skip_pdf: bool
    include_images: bool


_EXACT_DWG_COMPANION_PDFS: set[str] = set()
MIN_EXACT_ELEMENTS_FOR_PDF_SKIP = 10


def exact_companion_pdf_names() -> set[str]:
    return set(_EXACT_DWG_COMPANION_PDFS)


def register_exact_companion_pdf(pdf_name: str) -> None:
    _EXACT_DWG_COMPANION_PDFS.add(pdf_name)


def clear_exact_companion_pdfs() -> None:
    _EXACT_DWG_COMPANION_PDFS.clear()


def should_skip_clash_media(path: Path, suffix: str, args: ClashMediaSkipArgs) -> bool:
    if suffix in {".dwg", ".dxf"} and args.skip_dwg:
        return True
    if suffix == ".pdf" and args.skip_pdf:
        return True
    if suffix == ".pdf" and path.name in _EXACT_DWG_COMPANION_PDFS:
        return True
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"} and not args.include_images:
        return True
    return False
