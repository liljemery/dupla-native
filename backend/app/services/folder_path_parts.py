"""Shared folder path resolution for project file folders."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_file_folder import ProjectFileFolder


async def folder_path_parts(
    session: AsyncSession,
    project_id: UUID,
    folder_id: UUID | None,
) -> list[str]:
    if folder_id is None:
        return []
    parts: list[str] = []
    cur: UUID | None = folder_id
    for _ in range(128):
        if cur is None:
            break
        row = await session.get(ProjectFileFolder, cur)
        if row is None or row.project_id != project_id:
            break
        parts.append(row.name)
        cur = row.parent_id
    parts.reverse()
    return parts
