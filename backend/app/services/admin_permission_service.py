from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.permission_catalog import ALL_PERMISSION_KEYS, SYSTEM_ROLE_SLUGS
from app.models.rbac import Role
from app.models.user import User, UserRole
from app.repositories.permission_repository import PermissionRepository
from app.repositories.user_repository import UserRepository
from app.services.permission_service import PermissionService

_SLUG_RE = re.compile(r"^[A-Z0-9_]{2,64}$")


class AdminPermissionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._perms = PermissionRepository(session)
        self._users = UserRepository(session)
        self._perm_svc = PermissionService(session)

    async def list_catalog(self) -> list[dict]:
        rows = await self._perms.list_permissions()
        return [{"key": p.key, "label": p.label, "category": p.category} for p in rows]

    async def list_roles_with_permissions(self) -> list[dict]:
        roles = await self._perms.list_roles()
        out: list[dict] = []
        for role in roles:
            keys = await self._perms.list_role_permission_keys(role.id)
            out.append(
                {
                    "uuid": role.id,
                    "slug": role.slug,
                    "name": role.name,
                    "is_system": role.is_system,
                    "is_deletable": role.is_deletable,
                    "permissions": sorted(keys),
                }
            )
        return out

    async def create_role(self, name: str, slug: str | None = None) -> Role:
        clean_name = name.strip()
        if not clean_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombre requerido")
        role_slug = (slug or clean_name.upper().replace(" ", "_")).upper()
        if not _SLUG_RE.match(role_slug):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slug inválido (use A-Z, 0-9, _)",
            )
        if role_slug in SYSTEM_ROLE_SLUGS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Slug reservado para rol de sistema",
            )
        existing = await self._perms.get_role_by_slug(role_slug)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe un rol con ese slug",
            )
        return await self._perms.create_custom_role(role_slug, clean_name)

    async def update_role(self, role_uuid: UUID, name: str) -> Role:
        role = await self._perms.get_role_by_uuid(role_uuid)
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado")
        clean = name.strip()
        if not clean:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombre requerido")
        role.name = clean
        await self._session.flush()
        return role

    async def delete_role(self, role_uuid: UUID) -> None:
        role = await self._perms.get_role_by_uuid(role_uuid)
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado")
        if role.is_system or not role.is_deletable:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede eliminar un rol de sistema",
            )
        count = await self._perms.count_users_with_role(role.id)
        if count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El rol tiene usuarios asignados",
            )
        await self._perms.delete_role(role.id)

    async def set_role_permissions(self, role_uuid: UUID, permission_keys: list[str]) -> None:
        role = await self._perms.get_role_by_uuid(role_uuid)
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado")
        keys = frozenset(permission_keys)
        unknown = keys - ALL_PERMISSION_KEYS
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Permisos desconocidos: {sorted(unknown)}",
            )
        if role.slug == UserRole.GERENCIA.value and "admin.permissions.manage" not in keys:
            gerencia_count = await self._perms.count_users_with_role_slug(UserRole.GERENCIA.value)
            if gerencia_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Gerencia debe conservar admin.permissions.manage",
                )
        await self._perms.set_role_permissions(role.id, keys)

    async def get_user_permissions_detail(self, user_uuid: UUID) -> dict:
        user = await self._users.get_by_uuid(user_uuid)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
        roles = await self._perms.list_user_roles(user.id)
        overrides = await self._perms.list_user_overrides(user.id)
        effective = await self._perm_svc.resolve(user)
        return {
            "role_uuids": [r.id for r in roles],
            "role_slugs": [r.slug for r in roles],
            "permissions": sorted(effective),
            "overrides": [
                {"permission_key": o.permission_key, "granted": o.granted} for o in overrides
            ],
        }

    async def set_user_roles(self, actor: User, user_uuid: UUID, role_uuids: list[UUID]) -> None:
        if not role_uuids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Al menos un rol debe asignarse",
            )
        user = await self._users.get_by_uuid(user_uuid)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
        actor_perms = await self._perm_svc.resolve(actor)
        roles: list[Role] = []
        for rid in role_uuids:
            role = await self._perms.get_role_by_uuid(rid)
            if role is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Rol {rid} no existe",
                )
            if role.slug in (UserRole.GERENCIA.value, "TEAM_LEADER") and "admin.permissions.manage" not in actor_perms:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo Gerencia puede asignar roles Gerencia o Líder de equipo",
                )
            roles.append(role)
        await self._validate_last_gerencia(user, roles)
        await self._perms.set_user_roles(user.id, role_uuids)

    async def set_user_overrides(
        self,
        user_uuid: UUID,
        overrides: list[tuple[str, bool]],
    ) -> None:
        user = await self._users.get_by_uuid(user_uuid)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
        for key, _ in overrides:
            if key not in ALL_PERMISSION_KEYS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Permiso desconocido: {key}",
                )
        await self._perms.set_user_overrides(user.id, overrides)

    async def _validate_last_gerencia(self, user: User, new_roles: list[Role]) -> None:
        had_gerencia = await self._perms.user_has_role_slug(user.id, UserRole.GERENCIA.value)
        will_have = any(r.slug == UserRole.GERENCIA.value for r in new_roles)
        if had_gerencia and not will_have:
            count = await self._perms.count_users_with_role_slug(UserRole.GERENCIA.value)
            if count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No se puede quitar el último usuario con rol Gerencia",
                )
