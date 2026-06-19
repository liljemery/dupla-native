from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.file_discipline import FileDiscipline


@dataclass(frozen=True)
class MotorDisciplineInference:
    discipline: FileDiscipline | None
    method: str
    confidence: float
    snapshot: dict[str, Any]
    aps: dict[str, Any] | None
