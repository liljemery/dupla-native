from __future__ import annotations

import uuid
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.permission_catalog import (
    ALL_PERMISSION_KEYS,
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSION_CATALOG,
    SYSTEM_ROLE_LABELS,
    SYSTEM_ROLE_SLUGS,
)
from app.models.rbac import (
    Permission,
    Role,
    RolePermission,
    UserPermissionOverride,
    UserRoleAssignment,
)
from app.models.user import User


class PermissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_catalog(self) -> None:
        for perm in PERMISSION_CATALOG:
            existing = await self._session.get(Permission, perm.key)
            if existing is None:
                self._session.add(
                    Permission(key=perm.key, label=perm.label, category=perm.category)
                )
        await self._session.flush()

        for slug in SYSTEM_ROLE_SLUGS:
            role = await self.get_role_by_slug(slug)
            if role is None:
                role = Role(
                    slug=slug,
                    name=SYSTEM_ROLE_LABELS[slug],
                    is_system=True,
                    is_deletable=False,
                )
                self._session.add(role)
                await self._session.flush()
            granted = DEFAULT_ROLE_PERMISSIONS.get(slug, frozenset())
            for key in granted:
                link = await self._session.get(
                    RolePermission,
                    {"role_id": role.id, "permission_key": key},
                )
                if link is None:
                    self._session.add(
                        RolePermission(role_id=role.id, permission_key=key, granted=True)
                    )
        await self._session.flush()

    async def get_role_by_slug(self, slug: str) -> Role | None:
        result = await self._session.execute(select(Role).where(Role.slug == slug))
        return result.scalar_one_or_none()

    async def get_role_by_uuid(self, role_uuid: UUID) -> Role | None:
        result = await self._session.execute(select(Role).where(Role.id == role_uuid))
        return result.scalar_one_or_none()

    async def list_roles(self) -> Sequence[Role]:
        result = await self._session.execute(select(Role).order_by(Role.is_system.desc(), Role.name))
        return result.scalars().all()

    async def list_permissions(self) -> Sequence[Permission]:
        result = await self._session.execute(
            select(Permission).order_by(Permission.category, Permission.key)
        )
        return result.scalars().all()

    async def list_role_permission_keys(self, role_id: UUID) -> frozenset[str]:
        result = await self._session.execute(
            select(RolePermission.permission_key).where(
                RolePermission.role_id == role_id,
                RolePermission.granted.is_(True),
            )
        )
        return frozenset(result.scalars().all())

    async def set_role_permissions(self, role_id: UUID, granted_keys: frozenset[str]) -> None:
        await self._session.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        for key in granted_keys:
            self._session.add(RolePermission(role_id=role_id, permission_key=key, granted=True))
        await self._session.flush()

    async def list_user_role_slugs(self, user_id: UUID) -> list[str]:
        result = await self._session.execute(
            select(Role.slug)
            .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.id)
            .where(UserRoleAssignment.user_id == user_id)
            .order_by(Role.slug)
        )
        return list(result.scalars().all())

    async def list_user_roles(self, user_id: UUID) -> Sequence[Role]:
        result = await self._session.execute(
            select(Role)
            .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.id)
            .where(UserRoleAssignment.user_id == user_id)
            .order_by(Role.slug)
        )
        return result.scalars().all()

    async def set_user_roles(self, user_id: UUID, role_ids: list[UUID]) -> None:
        await self._session.execute(
            delete(UserRoleAssignment).where(UserRoleAssignment.user_id == user_id)
        )
        for role_id in role_ids:
            self._session.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
        await self._session.flush()

    async def list_user_overrides(self, user_id: UUID) -> Sequence[UserPermissionOverride]:
        result = await self._session.execute(
            select(UserPermissionOverride).where(UserPermissionOverride.user_id == user_id)
        )
        return result.scalars().all()

    async def set_user_overrides(
        self,
        user_id: UUID,
        overrides: list[tuple[str, bool]],
    ) -> None:
        await self._session.execute(
            delete(UserPermissionOverride).where(UserPermissionOverride.user_id == user_id)
        )
        for key, granted in overrides:
            self._session.add(
                UserPermissionOverride(user_id=user_id, permission_key=key, granted=granted)
            )
        await self._session.flush()

    async def resolve_permission_keys(self, user_id: UUID) -> frozenset[str]:
        role_perms = await self._session.execute(
            select(RolePermission.permission_key)
            .join(UserRoleAssignment, UserRoleAssignment.role_id == RolePermission.role_id)
            .where(
                UserRoleAssignment.user_id == user_id,
                RolePermission.granted.is_(True),
            )
        )
        effective: set[str] = set(role_perms.scalars().all())
        overrides = await self.list_user_overrides(user_id)
        for override in overrides:
            if override.granted:
                effective.add(override.permission_key)
            else:
                effective.discard(override.permission_key)
        return frozenset(effective)

    async def count_users_with_role_slug(self, slug: str) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(UserRoleAssignment)
            .join(Role, Role.id == UserRoleAssignment.role_id)
            .where(Role.slug == slug)
        )
        return int(result.scalar_one())

    async def user_has_role_slug(self, user_id: UUID, slug: str) -> bool:
        result = await self._session.execute(
            select(UserRoleAssignment.user_id)
            .join(Role, Role.id == UserRoleAssignment.role_id)
            .where(UserRoleAssignment.user_id == user_id, Role.slug == slug)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    def add_role(self, role: Role) -> None:
        self._session.add(role)

    async def delete_role(self, role_id: UUID) -> None:
        await self._session.execute(delete(Role).where(Role.id == role_id))

    async def count_users_with_role(self, role_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(UserRoleAssignment)
            .where(UserRoleAssignment.role_id == role_id)
        )
        return int(result.scalar_one())

    def validate_permission_keys(self, keys: frozenset[str]) -> None:
        unknown = keys - ALL_PERMISSION_KEYS
        if unknown:
            raise ValueError(f"Unknown permission keys: {sorted(unknown)}")

    async def assign_roles_by_slugs(self, user_id: UUID, slugs: list[str]) -> None:
        role_ids: list[UUID] = []
        for slug in slugs:
            role = await self.get_role_by_slug(slug)
            if role is None:
                raise ValueError(f"Role slug not found: {slug}")
            role_ids.append(role.id)
        await self.set_user_roles(user_id, role_ids)

    async def create_custom_role(self, slug: str, name: str) -> Role:
        role = Role(
            id=uuid.uuid4(),
            slug=slug.upper().replace(" ", "_"),
            name=name.strip(),
            is_system=False,
            is_deletable=True,
        )
        self.add_role(role)
        await self._session.flush()
        return role
