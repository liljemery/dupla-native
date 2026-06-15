from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_workspace_context, require_elevated_access, require_gerencia
from app.domain.workspace_context import WorkspaceContext
from app.models.user import User
from app.models.workspace import DEFAULT_WORKSPACE_UUID
from app.schemas.admin import (
    AdminCreateUserRequest,
    AdminImportUsersRequest,
    AdminImportUsersResponse,
    AdminUpdateUserRequest,
)
from app.schemas.auth import UserResponse
from app.schemas.workspace import (
    CreateWorkspaceRequest,
    RenameWorkspaceRequest,
    SetUserWorkspacesRequest,
    UserWorkspacesResponse,
    WorkspaceSummary,
)
from app.services.admin_service import AdminService
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _workspace_summary(ws_svc: WorkspaceService, ws) -> WorkspaceSummary:
    return WorkspaceSummary(
        uuid=ws.id,
        name=ws_svc.workspace_display_name(ws),
        is_default=ws.id == DEFAULT_WORKSPACE_UUID,
    )


@router.get(
    "/workspaces",
    response_model=list[WorkspaceSummary],
    summary="Listar workspaces",
)
async def list_workspaces_admin(
    _: Annotated[User, Depends(require_elevated_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[WorkspaceSummary]:
    ws_svc = WorkspaceService(session)
    rows = await ws_svc.list_workspaces()
    return [_workspace_summary(ws_svc, w) for w in rows]


@router.post(
    "/workspaces",
    response_model=WorkspaceSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Crear workspace",
    description="Solo Gerencia.",
)
async def create_workspace_admin(
    body: CreateWorkspaceRequest,
    _: Annotated[User, Depends(require_gerencia)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceSummary:
    ws_svc = WorkspaceService(session)
    ws = await ws_svc.create_workspace(
        new_workspace_name=body.new_workspace_name,
        default_workspace_name=body.default_workspace_name,
    )
    await session.commit()
    return _workspace_summary(ws_svc, ws)


@router.patch(
    "/workspaces/{workspace_uuid}",
    response_model=WorkspaceSummary,
    summary="Renombrar workspace",
    description="Solo Gerencia.",
)
async def patch_workspace_admin(
    workspace_uuid: UUID,
    body: RenameWorkspaceRequest,
    _: Annotated[User, Depends(require_gerencia)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceSummary:
    ws_svc = WorkspaceService(session)
    ws = await ws_svc.rename_workspace(workspace_uuid, body.name)
    await session.commit()
    return _workspace_summary(ws_svc, ws)


@router.put(
    "/users/{user_uuid}/workspaces",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Asignar workspaces a usuario",
    description="Solo Gerencia.",
)
async def set_user_workspaces_admin(
    user_uuid: UUID,
    body: SetUserWorkspacesRequest,
    _: Annotated[User, Depends(require_gerencia)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    ws_svc = WorkspaceService(session)
    await ws_svc.set_user_workspaces(user_uuid, body.workspace_uuids)
    await session.commit()


@router.get(
    "/users/{user_uuid}/workspaces",
    response_model=UserWorkspacesResponse,
    summary="Workspaces asignados a usuario",
    description="Solo Gerencia.",
)
async def get_user_workspaces_admin(
    user_uuid: UUID,
    _: Annotated[User, Depends(require_gerencia)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserWorkspacesResponse:
    ws_svc = WorkspaceService(session)
    uuids = await ws_svc.list_user_workspace_uuids(user_uuid)
    return UserWorkspacesResponse(workspace_uuids=uuids)


@router.get(
    "/users",
    response_model=list[UserResponse],
    summary="Listar usuarios",
    description="Gerencia o Líder de equipo. Incluye módulos asignados.",
)
async def list_users_admin(
    _: Annotated[User, Depends(require_elevated_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[UserResponse]:
    svc = AdminService(session, ws_ctx.workspace_id)
    users = await svc.list_users()
    return [UserResponse.from_user(u) for u in users]


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario",
    description="Crea credenciales y asigna módulos. Solo Gerencia.",
)
async def create_user_admin(
    body: AdminCreateUserRequest,
    _: Annotated[User, Depends(require_gerencia)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> UserResponse:
    svc = AdminService(session, ws_ctx.workspace_id)
    user = await svc.create_user(body)
    await session.commit()
    return UserResponse.from_user(user)


@router.post(
    "/users/import",
    response_model=AdminImportUsersResponse,
    summary="Importar usuarios",
    description="Crea usuarios en lote con contraseña temporal generada. Solo Gerencia.",
)
async def import_users_admin(
    body: AdminImportUsersRequest,
    _: Annotated[User, Depends(require_gerencia)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> AdminImportUsersResponse:
    svc = AdminService(session, ws_ctx.workspace_id)
    result = await svc.import_users(body.users)
    await session.commit()
    return result


@router.patch(
    "/users/{user_uuid}",
    response_model=UserResponse,
    summary="Actualizar usuario",
    description="Correo, rol, módulos y opcionalmente contraseña. Gerencia o Líder de equipo.",
)
async def update_user_admin(
    user_uuid: UUID,
    body: AdminUpdateUserRequest,
    actor: Annotated[User, Depends(require_elevated_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> UserResponse:
    svc = AdminService(session, ws_ctx.workspace_id)
    user = await svc.update_user(actor, user_uuid, body)
    await session.commit()
    return UserResponse.from_user(user)


@router.delete(
    "/users/{user_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar usuario",
    description="Elimina credenciales y datos asociados en cascada. Gerencia o Líder de equipo.",
    responses={
        400: {"description": "No se puede eliminar (cuenta propia o último Gerencia)"},
        404: {"description": "Usuario no encontrado"},
    },
)
async def delete_user_admin(
    user_uuid: UUID,
    actor: Annotated[User, Depends(require_elevated_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> None:
    svc = AdminService(session, ws_ctx.workspace_id)
    await svc.delete_user(actor.id, user_uuid)
    await session.commit()
