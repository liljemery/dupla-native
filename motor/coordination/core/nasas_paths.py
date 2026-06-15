"""Inferencia de disciplina desde rutas NASAS 09 y utilidades de desplazamiento por archivo."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from coordination.core.models_25d import Discipline

# Metadato común para filtrar interferencias entre entregas distintas (fecha/rev).
COORDINATION_ISSUE_METADATA_KEY = "coordination_issue_key"

_DATE_COMPACT = re.compile(r"\b((?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))\b")
_DATE_DMY_DOT = re.compile(
    r"\b(0?[1-9]|[12]\d|3[01])\.(0?[1-9]|1[0-2])\.((?:19|20)\d{2})\b"
)
_REV_FOLDER = re.compile(r"^rev\.?\s*(\d+)", re.IGNORECASE)


def discipline_from_nasas_relative_path(rel_posix: str) -> Discipline:
    """``rel_posix`` en minúsculas, separado por ``/``."""
    r = rel_posix.lower()
    if any(
        x in r
        for x in (
            "elect",
            "electrico",
            "ilumin",
            "electric",
            "lighting",
            "automat",
            "automation",
            "lutron",
            "cctv",
            "data y cctv",
        )
    ):
        return Discipline.MEP_ELEC
    if any(
        x in r
        for x in (
            "sanit",
            "hidro",
            "agua",
            "drenaje",
            "fontan",
            "plumb",
            "potable",
            "hs-",
        )
    ):
        return Discipline.MEP_PLUMBING
    if any(x in r for x in ("clim", "hvac", "mecan", "ventil", "a/a")):
        return Discipline.MEP_HVAC
    if any(
        x in r
        for x in (
            "estruct",
            "struct",
            "dessangles",
            "ciment",
            "cimientos",
            "viga",
            "column",
            "encofr",
        )
    ):
        return Discipline.STRUC
    return Discipline.ARCH


def file_translation_mm(path: Path, *, stride_mm: float = 12_000.0) -> tuple[float, float]:
    """
    Traslación determinista por ruta para separar planos que no comparten el mismo sistema
    de coordenadas (p. ej. distintos PDFs) y reducir choques espurios entre archivos.
    """
    h = int(hashlib.sha256(path.resolve().as_posix().encode("utf-8")).hexdigest()[:12], 16)
    nx = 97
    return (h % nx) * stride_mm, ((h // nx) % nx) * stride_mm


def translate_footprint(
    coords: list[tuple[float, float]], dx: float, dy: float
) -> list[tuple[float, float]]:
    return [(x + dx, y + dy) for x, y in coords]


def _first_calendar_key_from_stem(stem: str) -> str | None:
    """Devuelve ``d:YYYYMMDD`` usando la primera fecha encontrada en el nombre del archivo."""
    candidates: list[tuple[int, str]] = []
    for m in _DATE_COMPACT.finditer(stem):
        candidates.append((m.start(), m.group(1)))
    for m in _DATE_DMY_DOT.finditer(stem):
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        candidates.append((m.start(), f"{y}{mo:02d}{d:02d}"))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return f"d:{candidates[0][1]}"


def _rev_issue_key_from_parts(parts: tuple[str, ...]) -> str | None:
    for i, p in enumerate(parts):
        if _REV_FOLDER.match(p.strip()):
            sub = "/".join(parts[: i + 1])
            return f"rev:{sub.lower().replace(' ', '')}"
    return None


def coordination_issue_key(path: Path, nasas_root: Path | None = None) -> str:
    """
    Clave de “misma entrega” para no mezclar planos de fechas/revisiones distintas.

    1. Fecha en el nombre del archivo (``YYYYMMDD`` o ``DD.MM.YYYY``) → ``d:YYYYMMDD``.
    2. Carpeta ``REV. n`` en la ruta relativa al proyecto → ``rev:...``.
    3. Si no hay fecha ni REV: carpeta padre relativa al root (o absoluta).
    """
    path = path.resolve()
    stem = path.stem
    dated = _first_calendar_key_from_stem(stem)
    if dated:
        return dated
    parts: tuple[str, ...]
    if nasas_root is not None:
        try:
            parts = path.relative_to(nasas_root.resolve()).parts
        except ValueError:
            parts = path.parts
    else:
        parts = path.parts
    rev = _rev_issue_key_from_parts(parts)
    if rev:
        return rev
    if nasas_root is not None:
        try:
            rel = path.parent.relative_to(nasas_root.resolve())
            return f"dir:{rel.as_posix().lower()}"
        except ValueError:
            pass
    return f"dir:{path.parent.as_posix().lower()}"
