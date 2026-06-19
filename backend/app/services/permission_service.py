from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.permission_repository import PermissionRepository


class PermissionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = PermissionRepository(session)
        self._cache: dict[UUID, frozenset[str]] = {}

    async def ensure_catalog(self) -> None:
        await self._repo.ensure_catalog()

    async def resolve(self, user: User) -> frozenset[str]:
        if user.id in self._cache:
            return self._cache[user.id]
        keys = await self._repo.resolve_permission_keys(user.id)
        self._cache[user.id] = keys
        return keys

    async def has(self, user: User, permission_key: str) -> bool:
        return permission_key in await self.resolve(user)

    async def list_user_role_slugs(self, user: User) -> list[str]:
        return await self._repo.list_user_role_slugs(user.id)

    @property
    def repo(self) -> PermissionRepository:
        return self._repo
