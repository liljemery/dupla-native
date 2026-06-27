"""Shared folder path resolution for project file folders."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_file_folder import ProjectFileFolder


def build_folder_children_map(
    folders: list[ProjectFileFolder],
) -> dict[UUID | None, list[UUID]]:
    children: dict[UUID | None, list[UUID]] = {}
    for folder in folders:
        children.setdefault(folder.parent_id, []).append(folder.id)
    return children


def build_folder_path_index(folders: list[ProjectFileFolder]) -> dict[UUID, list[str]]:
    """In-memory folder id → name segments (one pass, no DB round-trips per path)."""
    by_id = {folder.id: folder for folder in folders}
    cache: dict[UUID, list[str]] = {}

    def parts(folder_id: UUID) -> list[str]:
        if folder_id in cache:
            return cache[folder_id]
        row = by_id.get(folder_id)
        if row is None:
            return []
        if row.parent_id is None or row.parent_id not in by_id:
            cache[folder_id] = [row.name]
        else:
            cache[folder_id] = parts(row.parent_id) + [row.name]
        return cache[folder_id]

    for folder in folders:
        parts(folder.id)
    return cache


def descendant_folder_ids(
    root_folder_id: UUID,
    children: dict[UUID | None, list[UUID]],
) -> set[UUID]:
    out: set[UUID] = set()
    stack = [root_folder_id]
    while stack:
        fid = stack.pop()
        if fid in out:
            continue
        out.add(fid)
        stack.extend(children.get(fid, []))
    return out


def format_folder_path(parts: list[str], *, leaf_name: str | None = None) -> str:
    if parts:
        return "Raíz / " + " / ".join(parts)
    if leaf_name:
        return leaf_name
    return "Raíz"


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
