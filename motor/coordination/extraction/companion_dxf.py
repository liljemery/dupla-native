"""Locate companion DXFs for DWG sources (same folder or project search roots)."""

from __future__ import annotations

import os
from pathlib import Path

from coordination.extraction.companion_pdf import _normalize_token, _score_pdf_match
from coordination.extraction.libredwg_convert import display_name_from_storage


def cad_stem_for_companion(path: Path) -> str:
    """Stem used for companion file pairing (ignores staging hash prefix)."""
    return Path(display_name_from_storage(path.name)).stem


def _search_roots(dwg_path: Path, extra_roots: list[Path] | None = None) -> list[Path]:
    roots: list[Path] = [dwg_path.parent]
    if extra_roots:
        roots.extend(extra_roots)
    extra = (os.getenv("NASAS09_DOWNLOADS") or "").strip()
    if extra:
        base = Path(extra)
        if base.is_dir():
            roots.append(base)
            for sub in ("ARQUITECTONICO", "ESTRUCTURAL", "ELECTRICO", "SANITARIO"):
                candidate = base / sub
                if candidate.is_dir():
                    roots.append(candidate)
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def _score_dxf_match(dwg_stem: str, dxf_stem: str, *, dwg_path: Path, dxf_path: Path) -> int:
    return _score_pdf_match(dwg_stem, dxf_stem, dwg_path=dwg_path, pdf_path=dxf_path)


def resolve_gate_dxf_cache(dwg_path: Path) -> Path | None:
    """DXF produced by upload gate at {parent}/.dxf_cache/{content_key}.dxf."""
    from coordination.extraction.cad_cache import file_cache_key

    dwg_path = Path(dwg_path)
    if not dwg_path.is_file():
        return None
    candidate = dwg_path.parent / ".dxf_cache" / f"{file_cache_key(dwg_path)}.dxf"
    return candidate if candidate.is_file() else None


def resolve_companion_dxf(
    dwg_path: Path,
    *,
    search_roots: list[Path] | None = None,
) -> Path | None:
    """Best-effort companion DXF for a DWG (exact stem, fuzzy tokens)."""
    dwg_path = Path(dwg_path)
    if not dwg_path.is_file():
        return None

    stem = cad_stem_for_companion(dwg_path)
    exact = dwg_path.parent / f"{stem}.dxf"
    for candidate in dwg_path.parent.glob("*.dxf"):
        if cad_stem_for_companion(candidate) == stem:
            return candidate
    if exact.is_file() and exact.resolve() != dwg_path.resolve():
        return exact

    best: tuple[int, Path] | None = None
    for root in _search_roots(dwg_path, search_roots):
        if not root.is_dir():
            continue
        for dxf in root.rglob("*.dxf"):
            if not dxf.is_file():
                continue
            score = _score_dxf_match(stem, dxf.stem, dwg_path=dwg_path, dxf_path=dxf)
            if score <= 0:
                continue
            if best is None or score > best[0]:
                best = (score, dxf)
    return best[1] if best else None


def is_readable_dxf(path: Path) -> bool:
    """Quick check that ezdxf can open the file (includes salvage probe)."""
    from coordination.extraction.dxf_geometry import probe_dxf_readable

    return probe_dxf_readable(path)
