from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect

from app.domain.user_permissions import primary_role_slug
from app.models.user import User, UserRole
from app.services.permission_service import PermissionService


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT bearer token")
    token_type: str = Field(default="bearer", description="Always bearer for OAuth2 password flow")
    must_change_password: bool = Field(
        default=False,
        description="Si true, el usuario debe cambiar la contraseña antes de usar la aplicación.",
    )


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordResponse(BaseModel):
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    dev_reset_token: str | None = Field(
        default=None,
        description="Solo development con DEV_EXPOSE_RESET_TOKEN=true y sin SMTP.",
    )


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    password: str = Field(min_length=8, max_length=128)


class ResetPasswordResponse(BaseModel):
    message: str


class PermissionOverrideResponse(BaseModel):
    permission_key: str
    granted: bool


class UserResponse(BaseModel):
    uuid: UUID = Field(..., description="Public user identifier")
    email: EmailStr
    first_name: str
    last_name: str
    role: UserRole = Field(..., description="Rol principal (compatibilidad UI)")
    role_uuids: list[UUID] = Field(default_factory=list)
    role_slugs: list[str] = Field(default_factory=list)
    role_names: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    permission_overrides: list[PermissionOverrideResponse] = Field(default_factory=list)
    module_ids: list[int] = Field(default_factory=list, description="Módulos asignados")
    must_change_password: bool = False
    active_workspace_uuid: UUID | None = None
    active_workspace_name: str | None = None
    available_workspaces: list[dict] = Field(default_factory=list)

    @classmethod
    async def from_user(cls, user: User, perm_svc: PermissionService) -> UserResponse:
        st = inspect(user)
        if "modules" in st.unloaded:
            mids: list[int] = []
        else:
            mids = [m.module_id for m in user.modules]

        role_slugs = await perm_svc.list_user_role_slugs(user)
        roles = await perm_svc.repo.list_user_roles(user.id)
        overrides = await perm_svc.repo.list_user_overrides(user.id)
        permissions = sorted(await perm_svc.resolve(user))
        primary = UserRole(primary_role_slug(role_slugs))

        return cls(
            uuid=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=primary,
            role_uuids=[r.id for r in roles],
            role_slugs=[r.slug for r in roles],
            role_names=[r.name for r in roles],
            permissions=permissions,
            permission_overrides=[
                PermissionOverrideResponse(permission_key=o.permission_key, granted=o.granted)
                for o in overrides
            ],
            module_ids=mids,
            must_change_password=user.must_change_password,
        )
