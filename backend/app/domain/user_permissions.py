from __future__ import annotations

from app.models.user import User, UserRole
from app.services.permission_service import PermissionService

PRIMARY_ROLE_ORDER = (
    UserRole.GERENCIA.value,
    UserRole.CONTROL.value,
    UserRole.PRESUPUESTO.value,
    UserRole.ARQUITECTURA.value,
)


def primary_role_slug(role_slugs: list[str]) -> str:
    for slug in PRIMARY_ROLE_ORDER:
        if slug in role_slugs:
            return slug
    return role_slugs[0] if role_slugs else UserRole.ARQUITECTURA.value


async def is_gerencia(user: User, perm_svc: PermissionService) -> bool:
    slugs = await perm_svc.list_user_role_slugs(user)
    return UserRole.GERENCIA.value in slugs


async def has_elevated_access(user: User, perm_svc: PermissionService) -> bool:
    perms = await perm_svc.resolve(user)
    return "admin.access" in perms or "dashboard.view" in perms


async def can_create_users(user: User, perm_svc: PermissionService) -> bool:
    return await perm_svc.has(user, "admin.users.create")


async def can_assign_team_leader(user: User, perm_svc: PermissionService) -> bool:
    return await perm_svc.has(user, "admin.permissions.manage")


async def can_view_budget(user: User, perm_svc: PermissionService) -> bool:
    return await perm_svc.has(user, "budget.view")


async def has_workspace_access_all(user: User, perm_svc: PermissionService) -> bool:
    return await perm_svc.has(user, "workspace.access_all")
