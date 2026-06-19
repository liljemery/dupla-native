"""Virtual discipline folder paths aligned with coordination manifest staging."""

from __future__ import annotations

# ponytail: single source in backend runtime; mirrors coordination-service DISCIPLINE_STAGING_DIRS.
DISCIPLINE_FOLDER_REL_PATHS: dict[str, tuple[str, ...]] = {
    "arquitectura": ("PLANOS RECIBIDOS", "ARQUITECTONICOS"),
    "estructura": ("PLANOS RECIBIDOS", "TECNICOS", "ESTRUCTURAL"),
    "mecanica": ("PLANOS RECIBIDOS", "TECNICOS", "MECANICA"),
    "electrica": ("PLANOS RECIBIDOS", "TECNICOS", "ELECTRICO"),
    "plomeria": ("PLANOS RECIBIDOS", "TECNICOS", "SANITARIO"),
    "sin_clasificar": ("PLANOS RECIBIDOS", "SIN_CLASIFICAR"),
}

DISCIPLINE_FOLDER_BUCKETS: tuple[str, ...] = tuple(DISCIPLINE_FOLDER_REL_PATHS.keys())
