from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    # Lucide icon export name (e.g. GitBranch); allowed values enforced in API.
    icon_key: Mapped[str] = mapped_column(String(64), nullable=False, default="GitBranch")
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    created_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by_user_id],
    )
    steps: Mapped[list["WorkflowTemplateStep"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="WorkflowTemplateStep.sort_index",
    )
    projects: Mapped[list["Project"]] = relationship(back_populates="workflow_template")


class WorkflowTemplateStep(Base):
    __tablename__ = "workflow_template_steps"
    __table_args__ = (UniqueConstraint("workflow_template_id", "stable_key", name="uq_workflow_template_step_stable"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_index: Mapped[int] = mapped_column(Integer(), nullable=False)
    stable_key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Lucide icon name; same allowlist as workflow_templates.icon_key.
    icon_key: Mapped[str] = mapped_column(String(64), nullable=False, default="GitBranch")
    behavior_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    blocked_by_step_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_template_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    requires_approval_role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    on_enter_actions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    template: Mapped["WorkflowTemplate"] = relationship(back_populates="steps")
    blocked_by_step: Mapped[Optional["WorkflowTemplateStep"]] = relationship(
        remote_side="WorkflowTemplateStep.id",
        foreign_keys=[blocked_by_step_id],
    )
