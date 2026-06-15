from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.models.plan_delivery_request import PlanDeliveryRequest


class PlanDeliveryStatus(str, Enum):
    SOLICITADO = "SOLICITADO"
    EN_PROCESO = "EN_PROCESO"
    ENTREGADO = "ENTREGADO"
    CANCELADO = "CANCELADO"


class PlanDeliveryRequestCreate(BaseModel):
    request_date: Optional[date] = None
    description: str = Field(default="", max_length=2000)
    delivery_date: Optional[date] = None
    days_count: Optional[int] = Field(default=None, ge=0)
    status: PlanDeliveryStatus = PlanDeliveryStatus.SOLICITADO


class PlanDeliveryRequestPatch(BaseModel):
    request_date: Optional[date] = None
    description: Optional[str] = Field(default=None, max_length=2000)
    delivery_date: Optional[date] = None
    days_count: Optional[int] = Field(default=None, ge=0)
    status: Optional[PlanDeliveryStatus] = None


def _resolved_days(row: PlanDeliveryRequest) -> Optional[int]:
    if row.days_count is not None:
        return row.days_count
    if row.request_date is not None and row.delivery_date is not None:
        return (row.delivery_date - row.request_date).days
    return None


class PlanDeliveryRequestResponse(BaseModel):
    uuid: uuid.UUID
    request_number: str
    sequence_number: int
    request_date: Optional[date] = None
    description: str
    delivery_date: Optional[date] = None
    days_count: Optional[int] = None
    days_resolved: Optional[int] = None
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: PlanDeliveryRequest) -> PlanDeliveryRequestResponse:
        return cls(
            uuid=row.id,
            request_number=row.request_number,
            sequence_number=row.sequence_number,
            request_date=row.request_date,
            description=row.description,
            delivery_date=row.delivery_date,
            days_count=row.days_count,
            days_resolved=_resolved_days(row),
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
