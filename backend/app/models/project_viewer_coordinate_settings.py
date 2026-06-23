from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProjectViewerCoordinateSettings(Base):
    __tablename__ = "project_viewer_coordinate_settings"
    __table_args__ = (UniqueConstraint("project_id", name="uq_project_viewer_coordinate_settings_project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    coordinate_space: Mapped[str] = mapped_column(String(16), nullable=False, default="world")
    scale: Mapped[float] = mapped_column(default=1.0, nullable=False)
    offset_x: Mapped[float] = mapped_column(default=0.0, nullable=False)
    offset_y: Mapped[float] = mapped_column(default=0.0, nullable=False)
    offset_z: Mapped[float] = mapped_column(default=0.0, nullable=False)
    invert_y: Mapped[bool] = mapped_column(default=False, nullable=False)
    rotation_degrees: Mapped[float] = mapped_column(default=0.0, nullable=False)
    unit_factor: Mapped[float] = mapped_column(default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)

    project = relationship("Project")
    creator = relationship("User")
