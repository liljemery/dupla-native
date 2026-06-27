"""Project file disciplines and coordination bucket helpers."""

from __future__ import annotations

import re
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
    # Abreviaturas habituales en obra / UI
    "arq": "arquitectura",
    "est": "estructura",
    "elc": "electrica",
    "elec": "electrica",
    "mec": "mecanica",
    "plo": "plomeria",
    "san": "plomeria",
    "arquitectonicos": "arquitectura",
    "arquitectónico": "arquitectura",
    "arquitectonicas": "arquitectura",
    "arquitectónicas": "arquitectura",
    "tecnico": "estructura",
    "técnico": "estructura",
    "tecnicos": "estructura",
    "técnicos": "estructura",
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


# Word stems (substring match) that flag a discipline from the file name alone.
# Order matters: the broad ARQUITECTURA bucket is checked last.
_DISCIPLINE_FILENAME_HINTS: tuple[tuple[FileDiscipline, tuple[str, ...]], ...] = (
    (FileDiscipline.ELECTRICA, (
        "electric", "electr", "eléctr", "ilumin", "luminar", "tomacorr",
        "tablero", "acometida", "circuito", "alumbrado",
    )),
    (FileDiscipline.PLOMERIA, (
        "sanitar", "plomer", "fontaner", "hidrosanit", "hidraulic", "hidráulic",
        "agua potable", "aguas negras", "drenaje", "desague", "desagüe",
        "cisterna", "pluvial",
    )),
    (FileDiscipline.MECANICA, (
        "mecanic", "mecánic", "climatiz", "climatización", "hvac",
        "aire acond", "ventilac", "ducto", "extraccion", "extracción",
    )),
    (FileDiscipline.ESTRUCTURA, (
        "estructur", "encofrad", "cimient", "zapata", "fundacion", "fundación",
        "refuerzo", "pilote", "viga", "columna", "losa",
    )),
    (FileDiscipline.ARQUITECTURA, (
        "arquitect", "acabado", "mobiliar", "fachada", "alzado",
        "carpinteria", "carpintería", "ventaneria", "ventanería", "planta arq",
    )),
)

# Sheet-code patterns: a discipline code followed by a number/sep, as used on
# real plan sets — e.g. "ES-05@11", "ARQ.-", "IE-12", "IS-3", "IM-2". Ordered so
# more specific codes win (ES estructura before a bare E). Single ambiguous
# letters (A/E/S/M) are intentionally excluded to avoid mislabelling.
_DISCIPLINE_CODE_PATTERNS: tuple[tuple[FileDiscipline, "re.Pattern[str]"], ...] = (
    (FileDiscipline.ARQUITECTURA, re.compile(r"\barq")),
    (FileDiscipline.ESTRUCTURA, re.compile(r"\b(?:est|es)[-_ .]?\d")),
    (FileDiscipline.ELECTRICA, re.compile(r"\b(?:iee|ie|elec|el)[-_ .]?\d")),
    (FileDiscipline.PLOMERIA, re.compile(r"\b(?:ihs|is|ip|san|plo)[-_ .]?\d")),
    (FileDiscipline.MECANICA, re.compile(r"\b(?:im|mec)[-_ .]?\d")),
)


def guess_discipline_from_filename(name: str | None) -> FileDiscipline | None:
    """Best-effort discipline from the file name alone (no binary read).

    Deterministic match (descriptive words first, then plan sheet codes) so
    auto-categorisation works even when the OpenAI suggestion is unavailable or
    fails. Returns None when nothing matches, so the file is left 'sin
    clasificar' rather than mislabelled.
    """
    if not name:
        return None
    text = name.lower()
    for discipline, keywords in _DISCIPLINE_FILENAME_HINTS:
        if any(kw in text for kw in keywords):
            return discipline
    for discipline, pattern in _DISCIPLINE_CODE_PATTERNS:
        if pattern.search(text):
            return discipline
    return None


# Discipline briefing: a short "what this sheet may contain" note used as the
# description when no richer (LLM) description is available. Written like the
# heads-up a senior estimator gives before quantifying a sheet of that type.
DISCIPLINE_BRIEFINGS: dict[FileDiscipline, str] = {
    FileDiscipline.ARQUITECTURA: (
        "Este plano puede contener información sobre distribución de espacios, "
        "muros y tabiques, acabados (pisos, cielos, pintura), puertas y ventanas "
        "y mobiliario fijo. Útil para cuantificar albañilería, carpintería y terminaciones."
    ),
    FileDiscipline.ESTRUCTURA: (
        "Este plano puede contener información sobre elementos estructurales: "
        "columnas, vigas, losas, zapatas y cimentación, con secciones, refuerzo de "
        "acero y resistencia del hormigón (f'c). Útil para cuantificar volúmenes de "
        "hormigón, encofrado y acero de refuerzo."
    ),
    FileDiscipline.ELECTRICA: (
        "Este plano puede contener información sobre instalaciones eléctricas: "
        "tableros, circuitos, canalizaciones, tomacorrientes, interruptores y "
        "luminarias. Útil para cuantificar puntos, salidas y conductores."
    ),
    FileDiscipline.MECANICA: (
        "Este plano puede contener información sobre instalaciones mecánicas / "
        "climatización (HVAC): ductos, equipos, difusores, rejillas y ventilación. "
        "Útil para cuantificar ductería y equipos."
    ),
    FileDiscipline.PLOMERIA: (
        "Este plano puede contener información sobre instalaciones hidrosanitarias: "
        "agua potable, aguas negras, drenaje pluvial, tuberías, piezas sanitarias, "
        "registros y cisterna. Útil para cuantificar tubería, puntos de agua/desagüe y piezas."
    ),
}


def discipline_briefing(discipline: FileDiscipline | None) -> str:
    """Short per-discipline 'what this sheet may contain' briefing, or '' when unknown."""
    if discipline is None:
        return ""
    return DISCIPLINE_BRIEFINGS.get(discipline, "")
