from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateStep


class WorkflowTemplateStepInput(BaseModel):
    """Un ítem del PUT de pasos; la lista completa sustituye todos los pasos (uuid ignorado)."""

    uuid: Optional[UUID] = None
    stable_key: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=255)
    behavior_kind: str = Field(..., min_length=1, max_length=64)
    blocked_by_stable_key: Optional[str] = None
    requires_approval_role: Optional[str] = Field(default=None, max_length=32)
    on_enter_actions: list[dict[str, Any]] = Field(default_factory=list)
    icon_key: Optional[str] = Field(default=None, max_length=64)


class WorkflowTemplateStepsPutRequest(BaseModel):
    steps: list[WorkflowTemplateStepInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def non_empty(self) -> WorkflowTemplateStepsPutRequest:
        if not self.steps:
            raise ValueError("Debe existir al menos un paso")
        return self


class WorkflowTemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""


class WorkflowTemplatePatchRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    archived: Optional[bool] = None
    icon_key: Optional[str] = Field(default=None, min_length=1, max_length=64)


class WorkflowTemplateStepResponse(BaseModel):
    uuid: UUID
    sort_index: int
    stable_key: str
    title: str
    behavior_kind: str
    blocked_by_step_uuid: Optional[UUID] = None
    requires_approval_role: Optional[str] = None
    on_enter_actions: list[dict[str, Any]] = Field(default_factory=list)
    icon_key: str = "GitBranch"

    @classmethod
    def from_orm_step(cls, s: WorkflowTemplateStep) -> WorkflowTemplateStepResponse:
        return cls(
            uuid=s.id,
            sort_index=s.sort_index,
            stable_key=s.stable_key,
            title=s.title,
            behavior_kind=s.behavior_kind,
            blocked_by_step_uuid=s.blocked_by_step_id,
            requires_approval_role=s.requires_approval_role,
            on_enter_actions=list(s.on_enter_actions or []),
            icon_key=s.icon_key,
        )


class WorkflowTemplateDetailResponse(BaseModel):
    uuid: UUID
    name: str
    description: str
    icon_key: str = "GitBranch"
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowTemplateStepResponse] = Field(default_factory=list)

    @classmethod
    def from_template(cls, t: WorkflowTemplate) -> WorkflowTemplateDetailResponse:
        steps = sorted(t.steps, key=lambda s: s.sort_index)
        card_icon = steps[0].icon_key if steps else t.icon_key
        return cls(
            uuid=t.id,
            name=t.name,
            description=t.description,
            icon_key=card_icon,
            archived_at=t.archived_at,
            created_at=t.created_at,
            updated_at=t.updated_at,
            steps=[WorkflowTemplateStepResponse.from_orm_step(s) for s in steps],
        )


class WorkflowTemplateListItemResponse(BaseModel):
    uuid: UUID
    name: str
    description: str
    icon_key: str = "GitBranch"
    archived_at: Optional[datetime] = None
    preview_projects: list[dict[str, Any]] = Field(default_factory=list)
