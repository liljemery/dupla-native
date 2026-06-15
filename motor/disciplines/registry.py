"""
Discipline engine discovery and registration.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import DisciplineConfig, DisciplineEngine

logger = logging.getLogger("dupla.disciplines")

_REGISTRY: dict[str, type] = {}


def register_engine(discipline_id: str, engine_class: type) -> None:
    _REGISTRY[discipline_id] = engine_class
    logger.debug("Registered discipline engine: %s -> %s", discipline_id, engine_class.__name__)


def get_engine(discipline_id: str, **kwargs: Any) -> DisciplineEngine:
    if discipline_id not in _REGISTRY:
        raise KeyError(
            f"No engine registered for discipline '{discipline_id}'. "
            f"Available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[discipline_id](**kwargs)


def available_disciplines() -> list[str]:
    return sorted(_REGISTRY)


def _auto_register() -> None:
    """Import built-in discipline packages so they self-register."""
    try:
        from disciplines.arquitectura import engine as _  # noqa: F401
    except ImportError:
        pass
    try:
        from disciplines.estructura import engine as _  # noqa: F401
    except ImportError:
        pass
    try:
        from disciplines.electrico import engine as _  # noqa: F401
    except ImportError:
        pass
    try:
        from disciplines.sanitario import engine as _  # noqa: F401
    except ImportError:
        pass


_auto_register()
