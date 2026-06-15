from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.project_price_database_file import ProjectPriceDatabaseFile


class PriceDatabaseFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_uuid: UUID
    original_name: str
    mime: Optional[str] = None
    file_size_bytes: Optional[int] = None
    status: str
    price_category: Optional[str] = None
    is_active: bool
    error_message: Optional[str] = None
    created_at: datetime

    @classmethod
    def from_row(cls, row: ProjectPriceDatabaseFile) -> PriceDatabaseFileResponse:
        return cls(
            file_uuid=row.id,
            original_name=row.original_name,
            mime=row.mime,
            file_size_bytes=row.file_size_bytes,
            status=row.status,
            price_category=row.price_category,
            is_active=row.is_active,
            error_message=row.error_message,
            created_at=row.created_at,
        )


class PriceDatabaseFileListResponse(BaseModel):
    items: list[PriceDatabaseFileResponse]
