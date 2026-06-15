"""Project file disciplines and coordination bucket helpers."""

from __future__ import annotations

from enum import Enum


class FileDiscipline(str, Enum):
    ARQUITECTURA = "arquitectura"
    ESTRUCTURA = "estructura"
    MECANICA = "mecanica"
    ELECTRICA = "electrica"
    PLOMERIA = "plomeria"


class FileIngestStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


DISCIPLINE_BUCKETS: tuple[str, ...] = (
    "arquitectura",
    "estructura",
    "mecanica",
    "electrica",
    "plomeria",
    "sin_clasificar",
)

CLASSIFIED_BUCKETS: frozenset[str] = frozenset(
    b for b in DISCIPLINE_BUCKETS if b != "sin_clasificar"
)

DISCIPLINE_LABELS: dict[str, str] = {
    "arquitectura": "Arquitectura",
    "estructura": "Estructura",
    "mecanica": "Mecánica",
    "electrica": "Eléctrica",
    "plomeria": "Plomería",
    "sin_clasificar": "Sin clasificar",
}

DISCIPLINE_SHORT: dict[str, str] = {
    "arquitectura": "ARQ",
    "estructura": "EST",
    "mecanica": "MEC",
    "electrica": "ELC",
    "plomeria": "PLO",
    "sin_clasificar": "—",
}

BUCKET_TO_RUNNER: dict[str, str] = {
    "arquitectura": "ARQUITECTURA",
    "estructura": "ESTRUCTURA",
    "electrica": "ELECTRICIDAD",
    "mecanica": "CLIMATIZACION",
    "plomeria": "FONTANERIA",
}


def parse_discipline(raw: str | None) -> FileDiscipline | None:
    if raw is None or raw.strip() == "":
        return None
    v = raw.strip().lower()
    for d in FileDiscipline:
        if d.value == v:
            return d
    return None


def discipline_bucket(raw: str | None) -> str:
    if not raw or not str(raw).strip():
        return "sin_clasificar"
    parsed = parse_discipline(str(raw).strip())
    if parsed is not None:
        return parsed.value
    key = str(raw).strip().lower()
    if key in CLASSIFIED_BUCKETS:
        return key
    return "sin_clasificar"
