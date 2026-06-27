from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.project_kind import ProjectKind
from app.domain.workflow_phase import WorkflowPhase

if TYPE_CHECKING:
    from app.models.project_budget_job import ProjectBudgetJob
    from app.models.project_clash_job import ProjectClashJob
    from app.models.project_price_database_file import ProjectPriceDatabaseFile
    from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateStep


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    project_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ProjectKind.CLIENT.value,
    )
    status: Mapped[str] = mapped_column(String(50), default="DRAFT")
    workflow_phase: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=WorkflowPhase.AWAITING_FILES.value,
    )
    workflow_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    project_bootstrap_criteria: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    specifications_document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    project_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    coordination_profile: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    location_text: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    estimated_area_sqm: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    floor_levels_count: Mapped[Optional[int]] = mapped_column(Integer(), nullable=True)
    deadline: Mapped[Optional[date]] = mapped_column(Date(), nullable=True)
    responsible_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    responsible_external_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    responsible_external_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    workflow_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    current_workflow_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_template_steps.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    creator: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by],
        back_populates="projects_created",
    )
    responsible_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[responsible_user_id],
    )
    architecture_data: Mapped[Optional["ProjectArchitectureData"]] = relationship(
        back_populates="project",
        uselist=False,
    )
    events: Mapped[list["ProjectEvent"]] = relationship(
        "ProjectEvent",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    files: Mapped[list["ProjectFile"]] = relationship(
        "ProjectFile",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    file_folders: Mapped[list["ProjectFileFolder"]] = relationship(
        "ProjectFileFolder",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    architecture_revisions: Mapped[list["ArchitectureRevision"]] = relationship(
        "ArchitectureRevision",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    subcontract_quotes: Mapped[list["SubcontractQuote"]] = relationship(
        "SubcontractQuote",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    members: Mapped[list["ProjectMember"]] = relationship(
        "ProjectMember",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    plan_delivery_requests: Mapped[list["PlanDeliveryRequest"]] = relationship(
        "PlanDeliveryRequest",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="PlanDeliveryRequest.sequence_number",
    )
    technical_findings: Mapped[list["ProjectTechnicalFinding"]] = relationship(
        "ProjectTechnicalFinding",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    price_database_files: Mapped[list["ProjectPriceDatabaseFile"]] = relationship(
        "ProjectPriceDatabaseFile",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    workflow_template: Mapped["WorkflowTemplate"] = relationship(
        "WorkflowTemplate",
        back_populates="projects",
        foreign_keys=[workflow_template_id],
    )
    current_workflow_step: Mapped["WorkflowTemplateStep"] = relationship(
        "WorkflowTemplateStep",
        foreign_keys=[current_workflow_step_id],
    )
    budget_jobs: Mapped[list["ProjectBudgetJob"]] = relationship(
        "ProjectBudgetJob",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectBudgetJob.created_at.desc()",
    )
    clash_jobs: Mapped[list["ProjectClashJob"]] = relationship(
        "ProjectClashJob",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectClashJob.created_at.desc()",
    )


class ProjectArchitectureData(Base):
    __tablename__ = "project_architecture_data"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    materiales: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    last_updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="architecture_data")
