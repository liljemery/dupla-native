"""
Optional heuristic validation of CAD layer names against declared discipline.

Not blocking -- only logs warnings when layer names suggest the DWG may not
match the declared discipline.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Any

logger = logging.getLogger("dupla.layer_validation")

DISCIPLINE_LAYER_HINTS: dict[str, set[str]] = {
    "arquitectura": {"arq", "muro", "puerta", "ventana", "piso", "techo", "door", "window"},
    "estructura": {"est", "col", "viga", "zapata", "losa", "ciment", "beam", "column", "slab"},
    "electrico": {"ele", "elec", "luminaria", "toma", "panel", "circuito", "switch", "outlet"},
    "sanitario": {"san", "plom", "tuberia", "drenaje", "agua", "inodoro", "pipe", "drain"},
}


def _normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in t if not unicodedata.combining(ch))


def validate_layers_for_discipline(
    cad_facts: dict[str, Any],
    declared_discipline: str,
) -> list[str]:
    """Return warning messages if layer names suggest a discipline mismatch.

    Returns an empty list if layers are consistent or no check is possible.
    """
    inventory = cad_facts.get("inventory_hints", {})
    layer_names: list[str] = inventory.get("layer_names", [])
    if not layer_names:
        return []

    normalized_layers = [_normalize(name) for name in layer_names]

    hints = DISCIPLINE_LAYER_HINTS.get(declared_discipline, set())
    if not hints:
        return []

    declared_hits = sum(
        1 for layer in normalized_layers
        if any(hint in layer for hint in hints)
    )

    warnings: list[str] = []
    other_discipline_hits: dict[str, int] = {}
    for other_disc, other_hints in DISCIPLINE_LAYER_HINTS.items():
        if other_disc == declared_discipline:
            continue
        other_discipline_hits[other_disc] = sum(
            1 for layer in normalized_layers
            if any(hint in layer for hint in other_hints)
        )

    best_other = max(other_discipline_hits, key=other_discipline_hits.get, default=None)
    if best_other and other_discipline_hits[best_other] > declared_hits * 2 and other_discipline_hits[best_other] > 3:
        warnings.append(
            f"Layer names suggest this DWG might be '{best_other}' rather than "
            f"'{declared_discipline}' (found {other_discipline_hits[best_other]} "
            f"'{best_other}' layer hints vs {declared_hits} '{declared_discipline}' hints)."
        )

    return warnings
