from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PermissionCatalogItem(BaseModel):
    key: str
    label: str
    category: str


class RoleWithPermissionsResponse(BaseModel):
    uuid: UUID
    slug: str
    name: str
    is_system: bool
    is_deletable: bool
    permissions: list[str]


class CreateRoleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=64)


class UpdateRoleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class SetRolePermissionsRequest(BaseModel):
    permissions: list[str]


class PermissionOverrideItem(BaseModel):
    permission_key: str
    granted: bool


class SetUserPermissionsRequest(BaseModel):
    overrides: list[PermissionOverrideItem] = Field(default_factory=list)


class SetUserRolesRequest(BaseModel):
    role_uuids: list[UUID] = Field(min_length=1)


class UserPermissionsDetailResponse(BaseModel):
    role_uuids: list[UUID]
    role_slugs: list[str]
    permissions: list[str]
    overrides: list[PermissionOverrideItem]
