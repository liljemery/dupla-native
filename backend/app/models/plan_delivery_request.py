from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project


def _format_sdp(sequence_number: int) -> str:
    return f"SDP {sequence_number:04d}"


class PlanDeliveryRequest(Base):
    """GA-FO-03 — Control Entrega de Planos (por proyecto)."""

    __tablename__ = "plan_delivery_requests"
    __table_args__ = (UniqueConstraint("project_id", "sequence_number", name="uq_plan_delivery_project_seq"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    days_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SOLICITADO")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    project: Mapped["Project"] = relationship(back_populates="plan_delivery_requests")

    @property
    def request_number(self) -> str:
        return _format_sdp(self.sequence_number)
