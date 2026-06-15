from datetime import datetime
from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_workspace_context, require_budget_access
from app.domain.workspace_context import WorkspaceContext
from app.models.user import User
from app.services.budget_service import BudgetService

router = APIRouter(prefix="/api/projects", tags=["budget"])


class EnqueueBudgetJobRequest(BaseModel):
    discipline: Optional[str] = None


class BudgetJobResponse(BaseModel):
    id: UUID
    project_id: UUID
    job_id: str
    status: str
    discipline: Optional[str]
    error: Optional[str]
    created_at: datetime
    updated_at: datetime


@router.post(
    "/{project_uuid}/budget/jobs",
    response_model=BudgetJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue budget processing job",
)
async def enqueue_budget_job(
    project_uuid: UUID,
    body: EnqueueBudgetJobRequest,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> BudgetJobResponse:
    svc = BudgetService(session, ws_ctx.workspace_id)
    job = await svc.enqueue_budget_job(
        current,
        project_uuid,
        discipline=body.discipline,
    )
    await session.commit()
    return BudgetJobResponse(
        id=job.id,
        project_id=job.project_id,
        job_id=job.job_id,
        status=job.status,
        discipline=job.discipline,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get(
    "/{project_uuid}/budget/jobs/latest",
    response_model=BudgetJobResponse,
    summary="Get latest budget job status (syncs from processor)",
)
async def get_latest_budget_job(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> BudgetJobResponse:
    svc = BudgetService(session, ws_ctx.workspace_id)
    job = await svc.get_latest_job(current, project_uuid)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No budget job found for this project")
    job = await svc.sync_job_status(job)
    await session.commit()
    return BudgetJobResponse(
        id=job.id,
        project_id=job.project_id,
        job_id=job.job_id,
        status=job.status,
        discipline=job.discipline,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get(
    "/{project_uuid}/budget/result",
    summary="Get completed budget JSON",
    response_model=dict[str, Any],
)
async def get_budget_result(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    svc = BudgetService(session, ws_ctx.workspace_id)
    return await svc.get_budget_result(current, project_uuid)
