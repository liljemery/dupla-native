from collections.abc import Sequence
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project, ProjectArchitectureData
from app.models.project_member import ProjectMember
from app.models.rbac import UserRoleAssignment
from app.models.user import User, UserModule
from app.repositories.permission_repository import PermissionRepository


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_uuid(self, user_uuid: UUID) -> Optional[User]:
        result = await self._session.execute(
            select(User)
            .options(
                selectinload(User.modules),
                selectinload(User.role_assignments).selectinload(UserRoleAssignment.role),
                selectinload(User.permission_overrides),
            )
            .where(User.id == user_uuid),
        )
        return result.scalar_one_or_none()

    async def has_module(self, user_uuid: UUID, module_id: int) -> bool:
        result = await self._session.execute(
            select(UserModule).where(
                UserModule.user_id == user_uuid,
                UserModule.module_id == module_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_all_ordered(self) -> Sequence[User]:
        result = await self._session.execute(
            select(User)
            .options(
                selectinload(User.modules),
                selectinload(User.role_assignments).selectinload(UserRoleAssignment.role),
            )
            .order_by(User.email)
        )
        return result.scalars().unique().all()

    async def delete_module_links_for_user(self, user_id: UUID) -> None:
        await self._session.execute(delete(UserModule).where(UserModule.user_id == user_id))

    async def count_by_role_slug(self, slug: str, perm_repo: PermissionRepository) -> int:
        return await perm_repo.count_users_with_role_slug(slug)

    async def list_elevated_user_ids_by_module(
        self,
        module_id: int,
        perm_repo: PermissionRepository,
    ) -> list[UUID]:
        q = (
            select(User.id)
            .join(UserModule, UserModule.user_id == User.id)
            .where(UserModule.module_id == module_id)
        )
        rows = (await self._session.execute(q)).scalars().all()
        elevated: list[UUID] = []
        for user_id in rows:
            perms = await perm_repo.resolve_permission_keys(user_id)
            if "projects.view_all" in perms or "workspace.access_all" in perms:
                elevated.append(user_id)
        return elevated

    async def clear_blocking_references(self, user_id: UUID) -> None:
        await self._session.execute(
            update(Project).where(Project.created_by == user_id).values(created_by=None)
        )
        await self._session.execute(
            update(ProjectArchitectureData)
            .where(ProjectArchitectureData.last_updated_by == user_id)
            .values(last_updated_by=None)
        )

    async def delete_by_uuid(self, user_id: UUID) -> None:
        await self.clear_blocking_references(user_id)
        await self.delete_module_links_for_user(user_id)
        await self._session.execute(delete(User).where(User.id == user_id))

    def add(self, user: User) -> None:
        self._session.add(user)

    def add_module_link(self, link: UserModule) -> None:
        self._session.add(link)

    async def list_ids_by_module_and_roles(
        self,
        module_id: int,
        role_slugs: list[str],
        perm_repo: PermissionRepository,
    ) -> list[UUID]:
        if not role_slugs:
            return []
        q = (
            select(User.id)
            .join(UserModule, UserModule.user_id == User.id)
            .where(UserModule.module_id == module_id)
        )
        rows = (await self._session.execute(q)).scalars().all()
        slug_set = set(role_slugs)
        matched: list[UUID] = []
        for user_id in rows:
            user_slugs = await perm_repo.list_user_role_slugs(user_id)
            if slug_set.intersection(user_slugs):
                matched.append(user_id)
        return matched

    async def first_team_member_with_role(
        self,
        project_id: UUID,
        role_slug: str,
        perm_repo: PermissionRepository,
    ) -> Optional[UUID]:
        q = (
            select(User.id)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project_id)
            .limit(50)
        )
        rows = (await self._session.execute(q)).scalars().all()
        for user_id in rows:
            if role_slug in await perm_repo.list_user_role_slugs(user_id):
                return user_id
        return None
