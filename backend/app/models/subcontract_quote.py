from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project


class SubcontractQuote(Base):
    __tablename__ = "subcontract_quotes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="subcontract_quotes")
    lines: Mapped[list["SubcontractQuoteLine"]] = relationship(
        back_populates="quote",
        cascade="all, delete-orphan",
    )


class SubcontractQuoteLine(Base):
    __tablename__ = "subcontract_quote_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subcontract_quotes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_label: Mapped[str] = mapped_column(String(512), nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="MXN")
    external_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    quote: Mapped["SubcontractQuote"] = relationship(back_populates="lines")
