from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class WorkspaceSummary(BaseModel):
    uuid: UUID
    name: str
    is_default: bool = False


class CreateWorkspaceRequest(BaseModel):
    new_workspace_name: str = Field(min_length=1, max_length=255)
    default_workspace_name: str | None = Field(default=None, max_length=255)


class RenameWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class SetUserWorkspacesRequest(BaseModel):
    workspace_uuids: list[UUID] = Field(min_length=1)


class UserWorkspacesResponse(BaseModel):
    workspace_uuids: list[UUID] = Field(default_factory=list)


class UserPreferencesPatch(BaseModel):
    active_workspace_uuid: UUID | None = None
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
