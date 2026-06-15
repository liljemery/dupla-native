from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.inspection import inspect

from app.models.user import User, UserRole


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


class UserResponse(BaseModel):
    uuid: UUID = Field(..., description="Public user identifier")
    email: EmailStr
    first_name: str
    last_name: str
    role: UserRole
    module_ids: list[int] = Field(default_factory=list, description="Módulos asignados")
    must_change_password: bool = False
    is_team_leader: bool = False
    active_workspace_uuid: UUID | None = None
    active_workspace_name: str | None = None
    available_workspaces: list[dict] = Field(default_factory=list)

    @classmethod
    def from_user(cls, user: User) -> UserResponse:
        st = inspect(user)
        if "modules" in st.unloaded:
            mids: list[int] = []
        else:
            mids = [m.module_id for m in user.modules]
        return cls(
            uuid=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role,
            module_ids=mids,
            must_change_password=user.must_change_password,
            is_team_leader=user.is_team_leader,
        )
