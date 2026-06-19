from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.workspace_context import WorkspaceContext
from app.models.user import User, UserRole
from app.models.workspace import Workspace
from app.repositories.permission_repository import PermissionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.services.permission_service import PermissionService
from app.services.workspace_bootstrap_service import bootstrap_workspace_resources


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._workspaces = WorkspaceRepository(session)
        self._users = UserRepository(session)
        self._perm_svc = PermissionService(session)

    async def list_workspaces(self) -> list[Workspace]:
        return await self._workspaces.list_all_ordered()

    async def create_workspace(
        self,
        *,
        new_workspace_name: str,
        default_workspace_name: Optional[str] = None,
    ) -> Workspace:
        name_new = new_workspace_name.strip()
        if not name_new:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre del nuevo workspace es obligatorio",
            )
        count = await self._workspaces.count()
        default_ws = await self._workspaces.get_default_or_first()
        if default_ws is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No hay workspace por defecto",
            )
        if default_ws.name is None or not str(default_ws.name).strip():
            dn = (default_workspace_name or "").strip()
            if not dn:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Asigna un nombre al workspace actual antes de crear otro",
                )
            default_ws.name = dn
            default_ws.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
        if count >= 1 and not name_new:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre del nuevo workspace es obligatorio",
            )
        ws = await self._workspaces.create_workspace(name_new)
        await bootstrap_workspace_resources(self._session, ws.id)
        return ws

    async def rename_workspace(self, workspace_uuid: UUID, name: str) -> Workspace:
        ws = await self._workspaces.get_by_uuid(workspace_uuid)
        if ws is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace no encontrado")
        cleaned = name.strip()
        if not cleaned:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre no puede estar vacío",
            )
        ws.name = cleaned
        ws.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return ws

    async def set_user_workspaces(self, user_uuid: UUID, workspace_uuids: list[UUID]) -> None:
        user = await self._users.get_by_uuid(user_uuid)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
        if await self._perm_svc.repo.user_has_role_slug(user.id, UserRole.GERENCIA.value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Gerencia no se asigna a workspaces",
            )
        ids = set(workspace_uuids)
        for wid in ids:
            ws = await self._workspaces.get_by_id(wid)
            if ws is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Workspace no encontrado: {wid}",
                )
        all_ws = await self._workspaces.list_all_ordered()
        for w in all_ws:
            member_ids = set(await self._workspaces.list_member_user_ids(w.id))
            if w.id in ids:
                member_ids.add(user.id)
            else:
                member_ids.discard(user.id)
            await self._workspaces.replace_members(w.id, member_ids)
        if user.active_workspace_id is None or user.active_workspace_id not in ids:
            user.active_workspace_id = next(iter(ids))
        await self._session.flush()

    async def set_active_workspace(self, user: User, workspace_uuid: UUID) -> Workspace:
        if await self._perm_svc.repo.user_has_role_slug(user.id, UserRole.GERENCIA.value):
            ws = await self._workspaces.get_by_uuid(workspace_uuid)
            if ws is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace no encontrado")
            user.active_workspace_id = ws.id
            await self._session.flush()
            return ws
        if not await self._workspaces.user_is_member(user.id, workspace_uuid):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sin acceso a ese workspace",
            )
        ws = await self._workspaces.get_by_uuid(workspace_uuid)
        if ws is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace no encontrado")
        user.active_workspace_id = ws.id
        await self._session.flush()
        return ws

    def workspace_display_name(self, ws: Workspace) -> str:
        if ws.name and ws.name.strip():
            return ws.name.strip()
        return "Workspace 1"

    async def workspaces_for_user(self, user: User) -> list[Workspace]:
        if await self._perm_svc.repo.user_has_role_slug(user.id, UserRole.GERENCIA.value):
            return await self._workspaces.list_all_ordered()
        return await self._workspaces.list_workspaces_for_user(user.id)

    async def list_user_workspace_uuids(self, user_uuid: UUID) -> list[UUID]:
        user = await self._users.get_by_uuid(user_uuid)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
        if await self._perm_svc.repo.user_has_role_slug(user.id, UserRole.GERENCIA.value):
            return [w.id for w in await self._workspaces.list_all_ordered()]
        return [w.id for w in await self._workspaces.list_workspaces_for_user(user.id)]
