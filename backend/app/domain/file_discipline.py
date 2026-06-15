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


DISCIPLINE_ALIASES: dict[str, str] = {
    "fontaneria": "plomeria",
    "fontanería": "plomeria",
    "sanitario": "plomeria",
    "sanitaria": "plomeria",
    "hidrosanitario": "plomeria",
    "hidrosanitaria": "plomeria",
    "plomería": "plomeria",
    "electrico": "electrica",
    "eléctrico": "electrica",
    "electricidad": "electrica",
    "estructural": "estructura",
    "arquitectonico": "arquitectura",
    "arquitectónico": "arquitectura",
    "arquitectonica": "arquitectura",
    "arquitectónica": "arquitectura",
    "mecanico": "mecanica",
    "mecánico": "mecanica",
    "mecánica": "mecanica",
    "climatizacion": "mecanica",
    "climatización": "mecanica",
}


def parse_discipline(raw: str | None) -> FileDiscipline | None:
    if raw is None or raw.strip() == "":
        return None
    v = raw.strip().lower()
    v = DISCIPLINE_ALIASES.get(v, v)
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
    key = DISCIPLINE_ALIASES.get(str(raw).strip().lower(), str(raw).strip().lower())
    if key in CLASSIFIED_BUCKETS:
        return key
    return "sin_clasificar"
