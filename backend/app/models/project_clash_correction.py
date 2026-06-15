from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project_clash_item import ProjectClashItem


class ProjectClashCorrection(Base):
    """A corrected DWG revision uploaded for a clash.

    The original DWG is never overwritten: ``original_dwg`` keeps the reference
    name and ``stored_path`` points at the newly uploaded revision on disk.
    ``result`` / ``reanalysis_run_id`` are filled once a re-analysis records
    whether the clash disappeared (resolved) or persists (still_present).
    """

    __tablename__ = "project_clash_corrections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clash_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_clash_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_clash_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target: Mapped[str] = mapped_column(String(16), nullable=False)
    revision_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_dwg: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    stored_path: Mapped[str] = mapped_column(Text(), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    result: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reanalysis_run_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    clash_item: Mapped["ProjectClashItem"] = relationship(back_populates="corrections")
