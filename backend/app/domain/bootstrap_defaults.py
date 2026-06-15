from __future__ import annotations

from typing import Any

# IDs alineados con `frontend/src/constants/defaultBootstrapCriteria.ts`
_BOOTSTRAP_ENTRIES: tuple[tuple[str, str], ...] = (
    (
        "dupla-bootstrap-estructural",
        "Planos estructurales (cimentaciones, zapatas, columnas y vigas)",
    ),
    ("dupla-bootstrap-tecnicos", "Planos técnicos"),
    (
        "dupla-bootstrap-elementos",
        "Planos con información completa por cada elemento",
    ),
)


def default_bootstrap_criteria() -> list[dict[str, Any]]:
    return [
        {"id": sid, "label": label, "required": True, "done": False}
        for sid, label in _BOOTSTRAP_ENTRIES
    ]
