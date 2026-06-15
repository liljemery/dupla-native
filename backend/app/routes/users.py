from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user, get_workspace_context
from app.domain.workspace_context import WorkspaceContext
from app.models.user import User
from app.schemas.auth import UserResponse
from app.schemas.project_lifecycle import UserNotificationResponse
from app.schemas.workspace import UserPreferencesPatch
from app.services.project_lifecycle_service import ProjectLifecycleService
from app.services.user_profile_service import build_user_response
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/api", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Current user profile",
    description="Returns the authenticated user's public data (UUID, email, role). Requires Bearer JWT.",
)
async def read_me(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    return await build_user_response(session, current)


@router.patch(
    "/me/preferences",
    response_model=UserResponse,
    summary="Actualizar preferencias del usuario",
)
async def patch_me_preferences(
    body: UserPreferencesPatch,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    ws_svc = WorkspaceService(session)
    patch = body.model_dump(exclude_unset=True)
    if "active_workspace_uuid" in patch and patch["active_workspace_uuid"] is not None:
        await ws_svc.set_active_workspace(current, patch["active_workspace_uuid"])
    if "first_name" in patch and patch["first_name"] is not None:
        current.first_name = patch["first_name"]
    if "last_name" in patch and patch["last_name"] is not None:
        current.last_name = patch["last_name"]
    await session.commit()
    await session.refresh(current)
    return await build_user_response(session, current)


@router.get(
    "/me/notifications",
    response_model=list[UserNotificationResponse],
    summary="Notificaciones del usuario",
)
async def list_my_notifications(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    unread_only: Annotated[bool, Query()] = False,
) -> list[UserNotificationResponse]:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    rows = await svc.list_my_notifications(current, unread_only=unread_only)
    return [UserNotificationResponse.from_row(r) for r in rows]


@router.patch(
    "/me/notifications/{notification_uuid}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Marcar notificación como leída",
)
async def mark_notification_read(
    notification_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> None:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    await svc.mark_notification_read(current, notification_uuid)
    await session.commit()
