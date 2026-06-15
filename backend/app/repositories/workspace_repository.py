from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import DEFAULT_WORKSPACE_UUID, Workspace, WorkspaceMember


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, workspace_id: UUID) -> Optional[Workspace]:
        return await self._session.get(Workspace, workspace_id)

    async def get_by_uuid(self, workspace_uuid: UUID) -> Optional[Workspace]:
        return await self.get_by_id(workspace_uuid)

    async def list_all_ordered(self) -> list[Workspace]:
        q = select(Workspace).order_by(Workspace.created_at.asc())
        return list((await self._session.execute(q)).scalars().all())

    async def get_default(self) -> Optional[Workspace]:
        return await self.get_by_id(DEFAULT_WORKSPACE_UUID)

    async def get_default_or_first(self) -> Optional[Workspace]:
        ws = await self.get_default()
        if ws is not None:
            return ws
        q = select(Workspace).order_by(Workspace.created_at.asc()).limit(1)
        return (await self._session.execute(q)).scalar_one_or_none()

    async def count(self) -> int:
        q = select(Workspace)
        return len(list((await self._session.execute(q)).scalars().all()))

    async def add(self, workspace: Workspace) -> Workspace:
        self._session.add(workspace)
        await self._session.flush()
        return workspace

    async def user_is_member(self, user_id: UUID, workspace_id: UUID) -> bool:
        q = select(WorkspaceMember.user_id).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        return (await self._session.execute(q)).scalar_one_or_none() is not None

    async def list_member_user_ids(self, workspace_id: UUID) -> list[UUID]:
        q = select(WorkspaceMember.user_id).where(WorkspaceMember.workspace_id == workspace_id)
        return list((await self._session.execute(q)).scalars().all())

    async def list_workspaces_for_user(self, user_id: UUID) -> list[Workspace]:
        q = (
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.created_at.asc())
        )
        return list((await self._session.execute(q)).scalars().all())

    async def replace_members(self, workspace_id: UUID, user_ids: set[UUID]) -> None:
        q = select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        existing = list((await self._session.execute(q)).scalars().all())
        existing_ids = {m.user_id for m in existing}
        for uid in user_ids - existing_ids:
            self._session.add(
                WorkspaceMember(
                    workspace_id=workspace_id,
                    user_id=uid,
                    created_at=datetime.now(timezone.utc),
                )
            )
        for m in existing:
            if m.user_id not in user_ids:
                await self._session.delete(m)
        await self._session.flush()

    async def add_member(self, workspace_id: UUID, user_id: UUID) -> None:
        if await self.user_is_member(user_id, workspace_id):
            return
        self._session.add(
            WorkspaceMember(
                workspace_id=workspace_id,
                user_id=user_id,
                created_at=datetime.now(timezone.utc),
            )
        )
        await self._session.flush()

    async def create_workspace(self, name: Optional[str]) -> Workspace:
        now = datetime.now(timezone.utc)
        ws = Workspace(
            id=uuid.uuid4(),
            name=name,
            created_at=now,
            updated_at=now,
        )
        return await self.add(ws)
