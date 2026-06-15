from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import DEFAULT_WORKSPACE_UUID
from app.schemas.auth import UserResponse
from app.services.workspace_service import WorkspaceService


async def build_user_response(session: AsyncSession, user: User) -> UserResponse:
    ws_svc = WorkspaceService(session)
    workspaces = await ws_svc.workspaces_for_user(user)
    available = [
        {
            "uuid": str(w.id),
            "name": ws_svc.workspace_display_name(w),
            "is_default": w.id == DEFAULT_WORKSPACE_UUID,
        }
        for w in workspaces
    ]
    active_ws = None
    active_name = None
    if user.active_workspace_id is not None:
        for w in workspaces:
            if w.id == user.active_workspace_id:
                active_ws = w.id
                active_name = ws_svc.workspace_display_name(w)
                break
    if active_ws is None and workspaces:
        active_ws = workspaces[0].id
        active_name = ws_svc.workspace_display_name(workspaces[0])
    base = UserResponse.from_user(user)
    return base.model_copy(
        update={
            "active_workspace_uuid": active_ws,
            "active_workspace_name": active_name,
            "available_workspaces": available,
        }
    )
