from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.project import Project


class ProjectResponse(BaseModel):
    uuid: UUID
    name: str
    client_name: Optional[str]
    project_kind: str
    status: str
    workflow_phase: str
    workflow_meta: dict[str, Any]
    project_bootstrap_criteria: list[Any]
    specifications_document: dict[str, Any]
    created_by_user_uuid: Optional[UUID] = None
    updated_at: datetime
    project_code: Optional[str] = None
    location_text: Optional[str] = None
    estimated_area_sqm: Optional[Decimal] = None
    floor_levels_count: Optional[int] = None
    deadline: Optional[date] = None
    responsible_user_uuid: Optional[UUID] = None
    responsible_external_name: Optional[str] = None
    responsible_external_email: Optional[str] = None
    workflow_template_uuid: UUID
    current_workflow_step_uuid: UUID
    current_step_title: Optional[str] = None
    current_step_behavior_kind: Optional[str] = None
    current_step_icon_key: Optional[str] = None
    archived_at: Optional[datetime] = None

    @classmethod
    def from_project(cls, project: Project) -> ProjectResponse:
        area = project.estimated_area_sqm
        area_out: Optional[Decimal] = None
        if area is not None:
            area_out = Decimal(str(area)) if not isinstance(area, Decimal) else area
        cur_step = project.current_workflow_step
        return cls(
            uuid=project.id,
            name=project.name,
            client_name=project.client_name,
            project_kind=project.project_kind,
            status=project.status,
            workflow_phase=project.workflow_phase,
            workflow_meta=project.workflow_meta or {},
            project_bootstrap_criteria=project.project_bootstrap_criteria or [],
            specifications_document=project.specifications_document or {},
            created_by_user_uuid=project.created_by,
            updated_at=project.updated_at,
            project_code=project.project_code,
            location_text=project.location_text,
            estimated_area_sqm=area_out,
            floor_levels_count=project.floor_levels_count,
            deadline=project.deadline,
            responsible_user_uuid=project.responsible_user_id,
            responsible_external_name=project.responsible_external_name,
            responsible_external_email=project.responsible_external_email,
            workflow_template_uuid=project.workflow_template_id,
            current_workflow_step_uuid=project.current_workflow_step_id,
            current_step_title=cur_step.title if cur_step is not None else None,
            current_step_behavior_kind=cur_step.behavior_kind if cur_step is not None else None,
            current_step_icon_key=cur_step.icon_key if cur_step is not None else None,
            archived_at=project.archived_at,
        )


class ProjectMemberEntry(BaseModel):
    uuid: UUID
    email: EmailStr
    first_name: str
    last_name: str


class ProjectMembersPutRequest(BaseModel):
    member_user_uuids: list[UUID] = Field(default_factory=list)
