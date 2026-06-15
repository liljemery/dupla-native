from __future__ import annotations

from enum import StrEnum


class ProjectKind(StrEnum):
    """Tipo de obra / contratación."""

    TENDER = "TENDER"
    CLIENT = "CLIENT"
    DEVELOPMENT = "DEVELOPMENT"
