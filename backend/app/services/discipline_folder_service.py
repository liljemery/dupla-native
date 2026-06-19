"""Ensure virtual discipline folder tree per project."""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.discipline_folder_paths import DISCIPLINE_FOLDER_BUCKETS, DISCIPLINE_FOLDER_REL_PATHS
from app.models.project_file_folder import ProjectFileFolder

_folder_tree_locks: dict[UUID, asyncio.Lock] = {}


def _folder_tree_lock(project_id: UUID) -> asyncio.Lock:
    return _folder_tree_locks.setdefault(project_id, asyncio.Lock())


async def _find_child_folder(
    session: AsyncSession,
    project_id: UUID,
    parent_id: UUID | None,
    name: str,
) -> ProjectFileFolder | None:
    q = (
        select(ProjectFileFolder)
        .where(
            ProjectFileFolder.project_id == project_id,
            ProjectFileFolder.parent_id == parent_id if parent_id is not None else ProjectFileFolder.parent_id.is_(None),
            ProjectFileFolder.name == name,
        )
        .order_by(ProjectFileFolder.created_at.asc())
        .limit(1)
    )
    return (await session.execute(q)).scalar_one_or_none()


async def _ensure_folder_path(
    session: AsyncSession,
    project_id: UUID,
    segments: tuple[str, ...],
    *,
    created_by: UUID | None,
) -> UUID | None:
    parent_id: UUID | None = None
    for segment in segments:
        existing = await _find_child_folder(session, project_id, parent_id, segment)
        if existing is None:
            row = ProjectFileFolder(
                project_id=project_id,
                parent_id=parent_id,
                name= segment,
                created_by=created_by,
            )
            session.add(row)
            await session.flush()
            parent_id = row.id
        else:
            parent_id = existing.id
    return parent_id


async def ensure_discipline_folder_tree(
    session: AsyncSession,
    project_id: UUID,
    *,
    created_by: UUID | None,
) -> dict[str, UUID]:
    """Create discipline folder segments idempotently; returns bucket -> leaf folder id."""
    async with _folder_tree_lock(project_id):
        out: dict[str, UUID] = {}
        for bucket in DISCIPLINE_FOLDER_BUCKETS:
            leaf_id = await _ensure_folder_path(
                session,
                project_id,
                DISCIPLINE_FOLDER_REL_PATHS[bucket],
                created_by=created_by,
            )
            if leaf_id is not None:
                out[bucket] = leaf_id
        return out


async def resolve_discipline_folder_id(
    session: AsyncSession,
    project_id: UUID,
    discipline_bucket: str,
    *,
    created_by: UUID | None = None,
) -> UUID | None:
    bucket = discipline_bucket if discipline_bucket in DISCIPLINE_FOLDER_REL_PATHS else "sin_clasificar"
    async with _folder_tree_lock(project_id):
        return await _ensure_folder_path(
            session,
            project_id,
            DISCIPLINE_FOLDER_REL_PATHS[bucket],
            created_by=created_by,
        )
