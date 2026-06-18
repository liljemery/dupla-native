"""Locate companion PDFs for DWG sources (same folder or NASAS09_DOWNLOADS)."""

from __future__ import annotations

import os
import re
from pathlib import Path

_DISCIPLINE_TAGS = ("ARQUITECTONICO", "ESTRUCTURAL", "ELECTRICO", "SANITARIO", "MECANICA")


def _search_roots(dwg_path: Path) -> list[Path]:
    roots: list[Path] = [dwg_path.parent]
    extra = (os.getenv("NASAS09_DOWNLOADS") or "").strip()
    if not extra:
        return roots
    base = Path(extra)
    if not base.is_dir():
        return roots
    roots.append(base)
    for sub in ("ARQUITECTONICO", "ESTRUCTURAL", "ELECTRICO", "SANITARIO"):
        candidate = base / sub
        if candidate.is_dir():
            roots.append(candidate)
    return roots


def _normalize_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _path_discipline_tag(path: Path) -> str | None:
    upper = str(path).upper()
    for tag in _DISCIPLINE_TAGS:
        if tag in upper:
            return tag
    return None


def _keyword_hints(stem: str) -> set[str]:
    low = stem.lower()
    hints: set[str] = set()
    if any(token in low for token in ("arq", "arquitect", "planta arq")):
        hints.add("arq")
    if any(token in low for token in ("estruct", "entrepiso", "es-", "losa", "viga")):
        hints.add("est")
    if any(token in low for token in ("electric", "elc", "e-", "ilumin")):
        hints.add("elc")
    if any(token in low for token in ("sanit", "hs-", "agua", "fontan", "plomer")):
        hints.add("san")
    return hints


def _score_pdf_match(dwg_stem: str, pdf_stem: str, *, dwg_path: Path, pdf_path: Path) -> int:
    dwg_norm = _normalize_token(dwg_stem)
    pdf_norm = _normalize_token(pdf_stem)
    if not dwg_norm or not pdf_norm:
        return 0

    score = 0
    if dwg_norm == pdf_norm:
        score += 100
    elif dwg_norm in pdf_norm or pdf_norm in dwg_norm:
        score += 80

    dwg_tokens = set(re.findall(r"[a-z0-9]{4,}", dwg_stem.lower()))
    pdf_tokens = set(re.findall(r"[a-z0-9]{4,}", pdf_stem.lower()))
    score += len(dwg_tokens & pdf_tokens) * 10

    if dwg_path.parent.resolve() == pdf_path.parent.resolve():
        score += 35

    dwg_disc = _path_discipline_tag(dwg_path)
    pdf_disc = _path_discipline_tag(pdf_path)
    if dwg_disc and dwg_disc == pdf_disc:
        score += 45
    elif dwg_disc and pdf_disc and dwg_disc != pdf_disc:
        score -= 50

    for hint in _keyword_hints(dwg_stem):
        if hint == "arq" and any(k in pdf_stem.lower() for k in ("arq", "arquitect")):
            score += 20
        if hint == "est" and any(k in pdf_stem.lower() for k in ("estruct", "entrepiso", "es-")):
            score += 20
        if hint == "elc" and any(k in pdf_stem.lower() for k in ("electric", "eléctric", "elc")):
            score += 20
        if hint == "san" and any(k in pdf_stem.lower() for k in ("sanit", "hs-", "agua", "fontan")):
            score += 20

    if "est" in _keyword_hints(dwg_stem) and "electric" in pdf_stem.lower():
        score -= 40
    if "elc" in _keyword_hints(dwg_stem) and "estruct" in pdf_stem.lower() and "electric" not in pdf_stem.lower():
        score -= 20

    return score


def resolve_companion_pdf(dwg_path: Path) -> Path | None:
    """Best-effort companion PDF for a DWG (exact stem, fuzzy tokens, discipline folder)."""
    dwg_path = Path(dwg_path)
    if not dwg_path.is_file():
        return None

    stem = dwg_path.stem
    best: tuple[int, Path] | None = None
    for root in _search_roots(dwg_path):
        if not root.is_dir():
            continue
        for pdf in root.rglob("*.pdf"):
            score = _score_pdf_match(stem, pdf.stem, dwg_path=dwg_path, pdf_path=pdf)
            if score <= 0:
                continue
            if best is None or score > best[0]:
                best = (score, pdf)
    return best[1] if best else None
