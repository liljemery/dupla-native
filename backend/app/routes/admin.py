from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import (
    get_permission_service,
    get_workspace_context,
    require_permission,
)
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
from app.schemas.rbac import (
    CreateRoleRequest,
    PermissionCatalogItem,
    PermissionOverrideItem,
    RoleWithPermissionsResponse,
    SetRolePermissionsRequest,
    SetUserPermissionsRequest,
    SetUserRolesRequest,
    UpdateRoleRequest,
    UserPermissionsDetailResponse,
)
from app.schemas.workspace import (
    CreateWorkspaceRequest,
    RenameWorkspaceRequest,
    SetUserWorkspacesRequest,
    UserWorkspacesResponse,
    WorkspaceSummary,
)
from app.services.admin_permission_service import AdminPermissionService
from app.services.admin_service import AdminService
from app.services.permission_service import PermissionService
from app.services.user_profile_service import build_user_response
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _workspace_summary(ws_svc: WorkspaceService, ws) -> WorkspaceSummary:
    return WorkspaceSummary(
        uuid=ws.id,
        name=ws_svc.workspace_display_name(ws),
        is_default=ws.id == DEFAULT_WORKSPACE_UUID,
    )


@router.get(
    "/permissions/catalog",
    response_model=list[PermissionCatalogItem],
    summary="Catálogo de permisos",
)
async def list_permissions_catalog(
    _: Annotated[User, Depends(require_permission("admin.permissions.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[PermissionCatalogItem]:
    svc = AdminPermissionService(session)
    rows = await svc.list_catalog()
    return [PermissionCatalogItem(**r) for r in rows]


@router.get(
    "/roles",
    response_model=list[RoleWithPermissionsResponse],
    summary="Roles y permisos",
)
async def list_roles_admin(
    _: Annotated[User, Depends(require_permission("admin.access"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[RoleWithPermissionsResponse]:
    svc = AdminPermissionService(session)
    rows = await svc.list_roles_with_permissions()
    return [RoleWithPermissionsResponse(**r) for r in rows]


@router.post(
    "/roles",
    response_model=RoleWithPermissionsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear rol custom",
)
async def create_role_admin(
    body: CreateRoleRequest,
    _: Annotated[User, Depends(require_permission("admin.permissions.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RoleWithPermissionsResponse:
    svc = AdminPermissionService(session)
    role = await svc.create_role(body.name, body.slug)
    await session.commit()
    rows = await svc.list_roles_with_permissions()
    match = next(r for r in rows if r["uuid"] == role.id)
    return RoleWithPermissionsResponse(**match)


@router.patch(
    "/roles/{role_uuid}",
    response_model=RoleWithPermissionsResponse,
    summary="Renombrar rol",
)
async def patch_role_admin(
    role_uuid: UUID,
    body: UpdateRoleRequest,
    _: Annotated[User, Depends(require_permission("admin.permissions.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RoleWithPermissionsResponse:
    svc = AdminPermissionService(session)
    role = await svc.update_role(role_uuid, body.name)
    await session.commit()
    keys = await svc._perms.list_role_permission_keys(role.id)
    return RoleWithPermissionsResponse(
        uuid=role.id,
        slug=role.slug,
        name=role.name,
        is_system=role.is_system,
        is_deletable=role.is_deletable,
        permissions=sorted(keys),
    )


@router.delete(
    "/roles/{role_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar rol custom",
)
async def delete_role_admin(
    role_uuid: UUID,
    _: Annotated[User, Depends(require_permission("admin.permissions.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    svc = AdminPermissionService(session)
    await svc.delete_role(role_uuid)
    await session.commit()


@router.put(
    "/roles/{role_uuid}/permissions",
    response_model=RoleWithPermissionsResponse,
    summary="Actualizar permisos de un rol",
)
async def set_role_permissions_admin(
    role_uuid: UUID,
    body: SetRolePermissionsRequest,
    _: Annotated[User, Depends(require_permission("admin.permissions.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RoleWithPermissionsResponse:
    svc = AdminPermissionService(session)
    await svc.set_role_permissions(role_uuid, body.permissions)
    await session.commit()
    role = await svc._perms.get_role_by_uuid(role_uuid)
    assert role is not None
    keys = await svc._perms.list_role_permission_keys(role.id)
    return RoleWithPermissionsResponse(
        uuid=role.id,
        slug=role.slug,
        name=role.name,
        is_system=role.is_system,
        is_deletable=role.is_deletable,
        permissions=sorted(keys),
    )


@router.get(
    "/users/{user_uuid}/permissions",
    response_model=UserPermissionsDetailResponse,
    summary="Permisos efectivos de usuario",
)
async def get_user_permissions_admin(
    user_uuid: UUID,
    _: Annotated[User, Depends(require_permission("admin.permissions.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserPermissionsDetailResponse:
    svc = AdminPermissionService(session)
    detail = await svc.get_user_permissions_detail(user_uuid)
    return UserPermissionsDetailResponse(
        role_uuids=detail["role_uuids"],
        role_slugs=detail["role_slugs"],
        permissions=detail["permissions"],
        overrides=[PermissionOverrideItem(**o) for o in detail["overrides"]],
    )


@router.put(
    "/users/{user_uuid}/permissions",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Overrides de permisos por usuario",
)
async def set_user_permissions_admin(
    user_uuid: UUID,
    body: SetUserPermissionsRequest,
    _: Annotated[User, Depends(require_permission("admin.permissions.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    svc = AdminPermissionService(session)
    await svc.set_user_overrides(
        user_uuid,
        [(o.permission_key, o.granted) for o in body.overrides],
    )
    await session.commit()


@router.put(
    "/users/{user_uuid}/roles",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Asignar roles a usuario",
)
async def set_user_roles_admin(
    user_uuid: UUID,
    body: SetUserRolesRequest,
    actor: Annotated[User, Depends(require_permission("admin.permissions.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    svc = AdminPermissionService(session)
    await svc.set_user_roles(actor, user_uuid, body.role_uuids)
    await session.commit()


@router.get(
    "/workspaces",
    response_model=list[WorkspaceSummary],
    summary="Listar workspaces",
)
async def list_workspaces_admin(
    _: Annotated[User, Depends(require_permission("admin.access"))],
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
)
async def create_workspace_admin(
    body: CreateWorkspaceRequest,
    _: Annotated[User, Depends(require_permission("admin.workspaces.manage"))],
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
)
async def patch_workspace_admin(
    workspace_uuid: UUID,
    body: RenameWorkspaceRequest,
    _: Annotated[User, Depends(require_permission("admin.workspaces.manage"))],
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
)
async def set_user_workspaces_admin(
    user_uuid: UUID,
    body: SetUserWorkspacesRequest,
    _: Annotated[User, Depends(require_permission("admin.workspaces.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    ws_svc = WorkspaceService(session)
    await ws_svc.set_user_workspaces(user_uuid, body.workspace_uuids)
    await session.commit()


@router.get(
    "/users/{user_uuid}/workspaces",
    response_model=UserWorkspacesResponse,
    summary="Workspaces asignados a usuario",
)
async def get_user_workspaces_admin(
    user_uuid: UUID,
    _: Annotated[User, Depends(require_permission("admin.workspaces.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserWorkspacesResponse:
    ws_svc = WorkspaceService(session)
    uuids = await ws_svc.list_user_workspace_uuids(user_uuid)
    return UserWorkspacesResponse(workspace_uuids=uuids)


@router.get(
    "/users",
    response_model=list[UserResponse],
    summary="Listar usuarios",
)
async def list_users_admin(
    _: Annotated[User, Depends(require_permission("admin.users.list"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    perm_svc: Annotated[PermissionService, Depends(get_permission_service)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[UserResponse]:
    svc = AdminService(session, ws_ctx.workspace_id)
    users = await svc.list_users()
    return [await UserResponse.from_user(u, perm_svc) for u in users]


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario",
)
async def create_user_admin(
    body: AdminCreateUserRequest,
    actor: Annotated[User, Depends(require_permission("admin.users.create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    perm_svc: Annotated[PermissionService, Depends(get_permission_service)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> UserResponse:
    svc = AdminService(session, ws_ctx.workspace_id)
    user = await svc.create_user(actor, body)
    await session.commit()
    return await UserResponse.from_user(user, perm_svc)


@router.post(
    "/users/import",
    response_model=AdminImportUsersResponse,
    summary="Importar usuarios",
)
async def import_users_admin(
    body: AdminImportUsersRequest,
    actor: Annotated[User, Depends(require_permission("admin.users.create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> AdminImportUsersResponse:
    svc = AdminService(session, ws_ctx.workspace_id)
    result = await svc.import_users(actor, body.users)
    await session.commit()
    return result


@router.patch(
    "/users/{user_uuid}",
    response_model=UserResponse,
    summary="Actualizar usuario",
)
async def update_user_admin(
    user_uuid: UUID,
    body: AdminUpdateUserRequest,
    actor: Annotated[User, Depends(require_permission("admin.users.edit"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    perm_svc: Annotated[PermissionService, Depends(get_permission_service)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> UserResponse:
    svc = AdminService(session, ws_ctx.workspace_id)
    user = await svc.update_user(actor, user_uuid, body)
    await session.commit()
    return await UserResponse.from_user(user, perm_svc)


@router.delete(
    "/users/{user_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar usuario",
)
async def delete_user_admin(
    user_uuid: UUID,
    actor: Annotated[User, Depends(require_permission("admin.users.delete"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> None:
    svc = AdminService(session, ws_ctx.workspace_id)
    await svc.delete_user(actor, user_uuid)
    await session.commit()
