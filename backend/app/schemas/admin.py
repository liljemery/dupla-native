from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import UserRole


class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role_uuids: list[UUID] = Field(min_length=1)
    module_ids: list[int] = Field(default_factory=lambda: [1])

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_names(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Requerido")
        return s

    @field_validator("module_ids")
    @classmethod
    def non_empty_modules(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("Al menos un módulo debe asignarse")
        return v


class AdminImportUserRow(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    role: UserRole
    module_ids: list[int] = Field(default_factory=lambda: [1])

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_import_names(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Requerido")
        return s

    @field_validator("module_ids")
    @classmethod
    def non_empty_import_modules(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("Al menos un módulo debe asignarse")
        return v


class AdminImportUsersRequest(BaseModel):
    users: list[AdminImportUserRow] = Field(min_length=1, max_length=200)


class AdminImportCreatedUser(BaseModel):
    uuid: str
    email: str
    first_name: str
    last_name: str
    role: UserRole
    password: str


class AdminImportSkippedUser(BaseModel):
    email: str
    reason: str


class AdminImportErrorRow(BaseModel):
    email: str
    detail: str


class AdminImportUsersResponse(BaseModel):
    created: list[AdminImportCreatedUser]
    skipped: list[AdminImportSkippedUser]
    errors: list[AdminImportErrorRow]


class AdminUpdateUserRequest(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    role_uuids: list[UUID] = Field(min_length=1)
    module_ids: list[int] = Field(default_factory=lambda: [1])
    password: str | None = Field(None, min_length=8, max_length=128)

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_names_update(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Requerido")
        return s

    @field_validator("module_ids")
    @classmethod
    def non_empty_modules(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("Al menos un módulo debe asignarse")
        return v
