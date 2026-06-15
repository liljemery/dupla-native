from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan_delivery_request import PlanDeliveryRequest


class PlanDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_project(self, project_id: uuid.UUID) -> list[PlanDeliveryRequest]:
        result = await self._session.execute(
            select(PlanDeliveryRequest)
            .where(PlanDeliveryRequest.project_id == project_id)
            .order_by(PlanDeliveryRequest.sequence_number)
        )
        return list(result.scalars().all())

    async def max_sequence(self, project_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.max(PlanDeliveryRequest.sequence_number), 0)).where(
                PlanDeliveryRequest.project_id == project_id
            )
        )
        return int(result.scalar_one())

    async def get_by_uuid(self, project_id: uuid.UUID, row_id: uuid.UUID) -> Optional[PlanDeliveryRequest]:
        result = await self._session.execute(
            select(PlanDeliveryRequest).where(
                PlanDeliveryRequest.project_id == project_id,
                PlanDeliveryRequest.id == row_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, row: PlanDeliveryRequest) -> PlanDeliveryRequest:
        self._session.add(row)
        await self._session.flush()
        return row

    async def delete(self, row: PlanDeliveryRequest) -> None:
        await self._session.delete(row)
