from __future__ import annotations

import uuid
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.user_permissions import primary_role_slug
from app.models.user import User, UserModule, UserRole
from app.repositories.module_repository import ModuleRepository
from app.repositories.permission_repository import PermissionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.schemas.admin import (
    AdminCreateUserRequest,
    AdminImportCreatedUser,
    AdminImportErrorRow,
    AdminImportSkippedUser,
    AdminImportUserRow,
    AdminImportUsersResponse,
    AdminUpdateUserRequest,
)
from app.security.password import hash_password
from app.security.temporary_password import generate_temporary_password
from app.services.admin_permission_service import AdminPermissionService
from app.services.permission_service import PermissionService


class AdminService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self._session = session
        self._workspace_id = workspace_id
        self._users = UserRepository(session)
        self._modules = ModuleRepository(session)
        self._workspaces = WorkspaceRepository(session)
        self._perms = PermissionRepository(session)
        self._perm_svc = PermissionService(session)
        self._perm_admin = AdminPermissionService(session)

    async def list_users(self) -> list[User]:
        member_ids = set(await self._workspaces.list_member_user_ids(self._workspace_id))
        rows = list(await self._users.list_all_ordered())
        return [u for u in rows if u.id in member_ids]

    async def create_user(self, actor: User, body: AdminCreateUserRequest) -> User:
        existing = await self._users.get_by_email(body.email)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe un usuario con este correo",
            )
        await self._validate_modules(body.module_ids)

        uid = uuid.uuid4()
        user = User(
            id=uid,
            email=body.email,
            first_name=body.first_name,
            last_name=body.last_name,
            password_hash=hash_password(body.password),
        )
        self._users.add(user)
        for mid in body.module_ids:
            self._users.add_module_link(UserModule(user_id=uid, module_id=mid))
        await self._session.flush()
        await self._perm_admin.set_user_roles(actor, uid, body.role_uuids)
        await self._workspaces.add_member(self._workspace_id, uid)
        role_slugs = await self._perms.list_user_role_slugs(uid)
        if UserRole.GERENCIA.value not in role_slugs:
            user.active_workspace_id = self._workspace_id
        await self._session.flush()
        refreshed = await self._users.get_by_uuid(uid)
        assert refreshed is not None
        return refreshed

    async def import_users(self, actor: User, rows: list[AdminImportUserRow]) -> AdminImportUsersResponse:
        created: list[AdminImportCreatedUser] = []
        skipped: list[AdminImportSkippedUser] = []
        errors: list[AdminImportErrorRow] = []
        seen_emails: set[str] = set()

        for row in rows:
            email_key = row.email.lower()
            if email_key in seen_emails:
                errors.append(
                    AdminImportErrorRow(
                        email=row.email,
                        detail="Correo duplicado en la importación",
                    )
                )
                continue
            seen_emails.add(email_key)

            existing = await self._users.get_by_email(row.email)
            if existing is not None:
                skipped.append(
                    AdminImportSkippedUser(
                        email=row.email,
                        reason="Ya existe un usuario con este correo",
                    )
                )
                continue

            role = await self._perms.get_role_by_slug(row.role.value)
            if role is None:
                errors.append(
                    AdminImportErrorRow(email=row.email, detail=f"Rol {row.role.value} no existe")
                )
                continue

            password = generate_temporary_password()
            try:
                user = await self.create_user(
                    actor,
                    AdminCreateUserRequest(
                        email=row.email,
                        first_name=row.first_name,
                        last_name=row.last_name,
                        password=password,
                        role_uuids=[role.id],
                        module_ids=row.module_ids,
                    ),
                )
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, str) else "No se pudo crear el usuario"
                errors.append(AdminImportErrorRow(email=row.email, detail=detail))
                continue

            slugs = await self._perms.list_user_role_slugs(user.id)
            created.append(
                AdminImportCreatedUser(
                    uuid=str(user.id),
                    email=user.email,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    role=UserRole(primary_role_slug(slugs)),
                    password=password,
                )
            )

        return AdminImportUsersResponse(created=created, skipped=skipped, errors=errors)

    async def update_user(self, actor: User, user_uuid: uuid.UUID, body: AdminUpdateUserRequest) -> User:
        user = await self._users.get_by_uuid(user_uuid)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado",
            )
        if body.email != user.email:
            existing = await self._users.get_by_email(body.email)
            if existing is not None and existing.id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ya existe un usuario con este correo",
                )
        await self._validate_modules(body.module_ids)

        user.email = body.email
        user.first_name = body.first_name
        user.last_name = body.last_name
        if body.password:
            user.password_hash = hash_password(body.password)
            user.must_change_password = True

        await self._perm_admin.set_user_roles(actor, user_uuid, body.role_uuids)

        await self._users.delete_module_links_for_user(user.id)
        for mid in body.module_ids:
            self._users.add_module_link(UserModule(user_id=user.id, module_id=mid))
        await self._session.flush()
        refreshed = await self._users.get_by_uuid(user_uuid)
        assert refreshed is not None
        return refreshed

    async def delete_user(self, actor: User, user_uuid: uuid.UUID) -> None:
        if actor.id == user_uuid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes eliminar tu propia cuenta",
            )

        user = await self._users.get_by_uuid(user_uuid)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado",
            )

        if await self._perms.user_has_role_slug(user.id, UserRole.GERENCIA.value):
            count = await self._perms.count_users_with_role_slug(UserRole.GERENCIA.value)
            if count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No se puede eliminar el último usuario con rol Gerencia",
                )

        await self._users.delete_by_uuid(user.id)
        await self._session.flush()

    async def _validate_modules(self, module_ids: list[int]) -> None:
        seen: set[int] = set()
        for mid in module_ids:
            if mid in seen:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="module_ids no debe repetirse",
                )
            seen.add(mid)
            mod = await self._modules.get_by_id(mid)
            if mod is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Módulo {mid} no existe",
                )
