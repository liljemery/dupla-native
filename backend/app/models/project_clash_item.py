from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project_clash_correction import ProjectClashCorrection
    from app.models.project_clash_event import ProjectClashEvent
    from app.models.project_clash_job import ProjectClashJob


class ProjectClashItem(Base):
    __tablename__ = "project_clash_items"
    __table_args__ = (UniqueConstraint("job_id", "clash_code", name="uq_clash_job_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_clash_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clash_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="P3")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    report_confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="detected")
    reviewer_decision: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dwg_a: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    dwg_b: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    level_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    discipline_a: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    discipline_b: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    layer_a: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    layer_b: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    observation: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    recommended_action: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    action_owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    centroid_x_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    centroid_y_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bounds_minx_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bounds_miny_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bounds_maxx_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bounds_maxy_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    area_mm2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    overlap_depth_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    member_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    alignment_dx_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    alignment_dy_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    job: Mapped["ProjectClashJob"] = relationship(
        back_populates="clash_items",
        foreign_keys=[job_id],
    )
    events: Mapped[list["ProjectClashEvent"]] = relationship(
        back_populates="clash_item", cascade="all, delete-orphan"
    )
    corrections: Mapped[list["ProjectClashCorrection"]] = relationship(
        back_populates="clash_item", cascade="all, delete-orphan"
    )
