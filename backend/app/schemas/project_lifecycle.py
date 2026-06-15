from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.inspection import inspect

from app.models.architecture_revision import ArchitectureRevision
from app.models.project_technical_finding import ProjectTechnicalFinding
from app.models.project_event import ProjectEvent
from app.models.project_file import ProjectFile
from app.models.project_file_folder import ProjectFileFolder
from app.models.subcontract_quote import SubcontractQuote, SubcontractQuoteLine
from app.models.user_notification import UserNotification


class ProjectTransitionRequest(BaseModel):
    target_phase: Optional[str] = Field(default=None, max_length=64)
    target_step_uuid: Optional[UUID] = None

    @model_validator(mode="after")
    def need_phase_or_step(self) -> ProjectTransitionRequest:
        if not self.target_phase and not self.target_step_uuid:
            raise ValueError("Indica target_phase o target_step_uuid")
        return self


class ProjectPatchRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    client_name: Optional[str] = Field(default=None, max_length=255)
    project_code: Optional[str] = Field(default=None, max_length=80)
    location_text: Optional[str] = None
    estimated_area_sqm: Optional[Decimal] = None
    floor_levels_count: Optional[int] = Field(default=None, ge=0)
    deadline: Optional[date] = None
    responsible_user_uuid: Optional[UUID] = None
    responsible_external_name: Optional[str] = Field(default=None, max_length=255)
    responsible_external_email: Optional[str] = Field(default=None, max_length=255)


class BootstrapCriteriaReplaceRequest(BaseModel):
    criteria: list[dict[str, Any]] = Field(default_factory=list)


class SpecificationsReplaceRequest(BaseModel):
    document: dict[str, Any] = Field(default_factory=dict)


class PliegoGenerateRequest(BaseModel):
    force: bool = False


class WorkflowMetaPatchRequest(BaseModel):
    budget_pipeline: Optional[dict[str, Any]] = None


class ProjectEventResponse(BaseModel):
    uuid: UUID
    event_type: str
    payload: dict[str, Any]
    actor_user_uuid: Optional[UUID]
    actor_email: Optional[str]
    created_at: datetime

    @classmethod
    def from_row(cls, row: ProjectEvent) -> ProjectEventResponse:
        st = inspect(row)
        actor = None if "actor" in st.unloaded else row.actor
        return cls(
            uuid=row.id,
            event_type=row.event_type,
            payload=row.payload or {},
            actor_user_uuid=row.actor_user_id,
            actor_email=actor.email if actor is not None else None,
            created_at=row.created_at,
        )


class ProjectEventsPageResponse(BaseModel):
    items: list[ProjectEventResponse]
    total: int
    limit: int
    offset: int


class ProjectFileResponse(BaseModel):
    uuid: UUID
    original_name: str
    mime: Optional[str]
    category: Optional[str]
    folder_uuid: Optional[UUID]
    description: Optional[str]
    discipline: Optional[str]
    ingest_status: str
    counts_for_budget: bool
    created_by_uuid: Optional[UUID]
    created_at: datetime

    @classmethod
    def from_row(cls, row: ProjectFile) -> ProjectFileResponse:
        return cls(
            uuid=row.id,
            original_name=row.original_name,
            mime=row.mime,
            category=row.category,
            folder_uuid=row.folder_id,
            description=row.description,
            discipline=row.discipline,
            ingest_status=row.ingest_status,
            counts_for_budget=row.counts_for_budget,
            created_by_uuid=row.created_by,
            created_at=row.created_at,
        )


class ProjectFilesListResponse(BaseModel):
    items: list[ProjectFileResponse]
    total: int
    limit: int
    offset: int


class ProjectFileSearchResponse(BaseModel):
    """Archivo con ruta legible desde la raíz del proyecto (para resultados de búsqueda)."""

    uuid: UUID
    original_name: str
    mime: Optional[str]
    category: Optional[str]
    folder_uuid: Optional[UUID]
    description: Optional[str]
    discipline: Optional[str]
    ingest_status: str
    created_by_uuid: Optional[UUID]
    created_at: datetime
    path: str

    @classmethod
    def from_row_with_path(cls, row: ProjectFile, path: str) -> ProjectFileSearchResponse:
        base = ProjectFileResponse.from_row(row)
        return cls(**base.model_dump(), path=path)


class ProjectFileFolderResponse(BaseModel):
    uuid: UUID
    name: str
    parent_uuid: Optional[UUID]
    created_at: datetime

    @classmethod
    def from_row(cls, row: ProjectFileFolder) -> ProjectFileFolderResponse:
        return cls(
            uuid=row.id,
            name=row.name,
            parent_uuid=row.parent_id,
            created_at=row.created_at,
        )


class ProjectFileFolderCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    parent_uuid: Optional[UUID] = None


class ProjectFileFolderPatchRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    parent_uuid: Optional[UUID] = None


class ProjectFilePatchRequest(BaseModel):
    original_name: Optional[str] = Field(default=None, min_length=1, max_length=512)
    description: Optional[str] = Field(default=None, max_length=8000)
    discipline: Optional[str] = Field(default=None, max_length=32)
    folder_uuid: Optional[UUID] = None
    ingest_status: Optional[str] = Field(default=None, max_length=20)


class ArchitectureRevisionCreateRequest(BaseModel):
    decision: str = Field(..., min_length=1, max_length=20)
    notes: Optional[str] = Field(default=None, max_length=4000)
    checklist: dict[str, Any] = Field(default_factory=dict)


class ArchitectureRevisionResponse(BaseModel):
    uuid: UUID
    version: int
    revision_role: str
    decision: str
    notes: Optional[str]
    checklist: dict[str, Any]
    checked_by_uuid: Optional[UUID]
    created_at: datetime

    @classmethod
    def from_row(cls, row: ArchitectureRevision) -> ArchitectureRevisionResponse:
        return cls(
            uuid=row.id,
            version=row.version,
            revision_role=row.revision_role,
            decision=row.decision.value,
            notes=row.notes,
            checklist=row.checklist or {},
            checked_by_uuid=row.checked_by,
            created_at=row.created_at,
        )


class SubcontractQuoteLineResponse(BaseModel):
    uuid: UUID
    item_label: str
    provider: Optional[str]
    price: Decimal
    currency: str
    external_ref: Optional[str]

    @classmethod
    def from_row(cls, row: SubcontractQuoteLine) -> SubcontractQuoteLineResponse:
        return cls(
            uuid=row.id,
            item_label=row.item_label,
            provider=row.provider,
            price=row.price,
            currency=row.currency,
            external_ref=row.external_ref,
        )


class SubcontractQuoteResponse(BaseModel):
    uuid: UUID
    title: Optional[str]
    created_at: datetime
    lines: list[SubcontractQuoteLineResponse]

    @classmethod
    def from_row(cls, row: SubcontractQuote) -> SubcontractQuoteResponse:
        st = inspect(row)
        raw_lines = [] if "lines" in st.unloaded else row.lines
        lines = sorted(raw_lines, key=lambda x: str(x.id))
        return cls(
            uuid=row.id,
            title=row.title,
            created_at=row.created_at,
            lines=[SubcontractQuoteLineResponse.from_row(l) for l in lines],
        )


class SubcontractQuoteCreateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)


class SubcontractLineCreateRequest(BaseModel):
    item_label: str = Field(..., min_length=1, max_length=512)
    provider: Optional[str] = Field(default=None, max_length=255)
    price: Decimal = Field(..., ge=Decimal("0"))
    currency: str = Field(default="MXN", max_length=8)
    external_ref: Optional[str] = Field(default=None, max_length=255)


class TechnicalFindingCreateRequest(BaseModel):
    discipline: str = Field(..., min_length=1, max_length=64)
    severity: str = Field(..., min_length=1, max_length=32)
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    evidence_ref: Optional[str] = None


class TechnicalFindingResponse(BaseModel):
    uuid: UUID
    discipline: str
    severity: str
    title: str
    description: str
    evidence_ref: Optional[str]
    created_at: datetime
    created_by_user_uuid: Optional[UUID]

    @classmethod
    def from_row(cls, row: ProjectTechnicalFinding) -> TechnicalFindingResponse:
        return cls(
            uuid=row.id,
            discipline=row.discipline,
            severity=row.severity,
            title=row.title,
            description=row.description,
            evidence_ref=row.evidence_ref,
            created_at=row.created_at,
            created_by_user_uuid=row.created_by,
        )


class UserNotificationResponse(BaseModel):
    uuid: UUID
    project_uuid: Optional[UUID]
    kind: str
    title: str
    body: Optional[str]
    read_at: Optional[datetime]
    created_at: datetime

    @classmethod
    def from_row(cls, row: UserNotification) -> UserNotificationResponse:
        return cls(
            uuid=row.id,
            project_uuid=row.project_id,
            kind=row.kind,
            title=row.title,
            body=row.body,
            read_at=row.read_at,
            created_at=row.created_at,
        )
