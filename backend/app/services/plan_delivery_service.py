from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.project_updated import touch_project_updated_at
from app.models.plan_delivery_request import PlanDeliveryRequest
from app.models.user import User
from app.repositories.plan_delivery_repository import PlanDeliveryRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.plan_delivery import (
    PlanDeliveryRequestCreate,
    PlanDeliveryRequestPatch,
    PlanDeliveryRequestResponse,
    PlanDeliveryStatus,
)
from app.services.project_service import ProjectService


class PlanDeliveryService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self._session = session
        self._repo = PlanDeliveryRepository(session)
        self._projects = ProjectService(session, workspace_id)
        self._project_repo = ProjectRepository(session)

    async def list_rows(self, user: User, project_uuid: UUID) -> list[PlanDeliveryRequestResponse]:
        project = await self._projects.get_project(user, project_uuid)
        rows = await self._repo.list_by_project(project.id)
        return [PlanDeliveryRequestResponse.from_row(r) for r in rows]

    async def create_row(
        self,
        user: User,
        project_uuid: UUID,
        body: PlanDeliveryRequestCreate,
    ) -> PlanDeliveryRequestResponse:
        project = await self._projects.get_project(user, project_uuid)
        next_seq = (await self._repo.max_sequence(project.id)) + 1
        row = PlanDeliveryRequest(
            project_id=project.id,
            sequence_number=next_seq,
            request_date=body.request_date,
            description=body.description.strip(),
            delivery_date=body.delivery_date,
            days_count=body.days_count,
            status=body.status.value,
        )
        await self._repo.add(row)
        touch_project_updated_at(project)
        await self._project_repo.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="PLAN_DELIVERY_CREATED",
            payload={
                "row_uuid": str(row.id),
                "sequence_number": row.sequence_number,
                "request_number": row.request_number,
                "description": (row.description or "")[:300],
            },
        )
        await self._session.commit()
        await self._session.refresh(row)
        return PlanDeliveryRequestResponse.from_row(row)

    async def patch_row(
        self,
        user: User,
        project_uuid: UUID,
        row_uuid: UUID,
        body: PlanDeliveryRequestPatch,
    ) -> PlanDeliveryRequestResponse:
        project = await self._projects.get_project(user, project_uuid)
        row = await self._repo.get_by_uuid(project.id, row_uuid)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada")
        raw = body.model_dump(exclude_unset=True)
        if "request_date" in raw:
            row.request_date = raw["request_date"]
        if "description" in raw:
            row.description = (raw["description"] or "").strip()
        if "delivery_date" in raw:
            row.delivery_date = raw["delivery_date"]
        if "days_count" in raw:
            row.days_count = raw["days_count"]
        if "status" in raw:
            s = raw["status"]
            row.status = s.value if isinstance(s, PlanDeliveryStatus) else str(s)
        row.updated_at = datetime.now(timezone.utc)
        touch_project_updated_at(project)
        if raw:
            diff = body.model_dump(exclude_unset=True, mode="json")
            await self._project_repo.record_event(
                project_id=project.id,
                actor_user_id=user.id,
                event_type="PLAN_DELIVERY_UPDATED",
                payload={
                    "row_uuid": str(row.id),
                    "sequence_number": row.sequence_number,
                    "request_number": row.request_number,
                    "changes": diff,
                },
            )
        await self._session.commit()
        await self._session.refresh(row)
        return PlanDeliveryRequestResponse.from_row(row)

    async def delete_row(self, user: User, project_uuid: UUID, row_uuid: UUID) -> None:
        project = await self._projects.get_project(user, project_uuid)
        row = await self._repo.get_by_uuid(project.id, row_uuid)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada")
        payload = {
            "row_uuid": str(row.id),
            "sequence_number": row.sequence_number,
            "request_number": row.request_number,
            "description": (row.description or "")[:300],
        }
        await self._repo.delete(row)
        touch_project_updated_at(project)
        await self._project_repo.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="PLAN_DELIVERY_DELETED",
            payload=payload,
        )
        await self._session.commit()

    async def list_models_for_export(self, user: User, project_uuid: UUID) -> tuple[str, list[PlanDeliveryRequest]]:
        project = await self._projects.get_project(user, project_uuid)
        rows = await self._repo.list_by_project(project.id)
        return project.name, rows
