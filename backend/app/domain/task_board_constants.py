"""Constantes del tablero de tareas (3 columnas por workspace)."""

from __future__ import annotations

import uuid
from uuid import UUID

DEFAULT_TASK_LIST_TITLES: tuple[str, str, str] = ("Por Hacer", "En Progreso", "Completado")


def task_list_uuid_for_workspace(workspace_id: UUID, position: int) -> UUID:
    return uuid.uuid5(workspace_id, f"dupla:task_list:{position}")


def normalize_task_list_bucket(title: str) -> int:
    """0 = por hacer, 1 = en progreso, 2 = completado."""
    t = title.strip().lower()
    if "completado" in t or "hecho" in t:
        return 2
    if "progreso" in t or "revisión" in t or "revision" in t:
        return 1
    return 0


def is_completed_task_list_title(title: str) -> bool:
    return normalize_task_list_bucket(title) == 2


def canonical_task_list_id(workspace_id: UUID, position: int) -> UUID:
    return task_list_uuid_for_workspace(workspace_id, position)


def canonical_task_list_ids(workspace_id: UUID) -> frozenset[UUID]:
    return frozenset(canonical_task_list_id(workspace_id, i) for i in range(len(DEFAULT_TASK_LIST_TITLES)))
