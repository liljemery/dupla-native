from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_workspace_context, require_permission
from app.domain.workspace_context import WorkspaceContext
from app.domain.workflow_phase import WorkflowPhase
from app.models.project import Project
from app.models.task_board import TaskCard, TaskList
from app.models.user import User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class DashboardSummaryResponse(BaseModel):
    projects_by_phase: dict[str, int]
    pending_task_cards: int
    projects_past_deadline: int


@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    current: Annotated[User, Depends(require_permission("dashboard.view"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> DashboardSummaryResponse:
    del current
    ws_id = ws_ctx.workspace_id
    q_ph = (
        select(Project.workflow_phase, func.count())
        .where(Project.workspace_id == ws_id)
        .group_by(Project.workflow_phase)
    )
    phase_rows = (await session.execute(q_ph)).all()
    projects_by_phase = {str(r[0]): int(r[1]) for r in phase_rows}

    done_title = func.lower(TaskList.title)
    done_ids = (
        select(TaskList.id)
        .where(
            TaskList.workspace_id == ws_id,
            or_(done_title.like("%completado%"), done_title.like("%hecho%")),
        )
        .scalar_subquery()
    )
    q_tasks = (
        select(func.count())
        .select_from(TaskCard)
        .join(TaskList, TaskCard.list_id == TaskList.id)
        .where(
            TaskList.workspace_id == ws_id,
            TaskCard.archived.is_(False),
            TaskCard.list_id.not_in(done_ids),
        )
    )
    pending_task_cards = int((await session.execute(q_tasks)).scalar_one() or 0)

    today = date.today()
    q_late = select(func.count()).select_from(Project).where(
        Project.workspace_id == ws_id,
        Project.deadline.isnot(None),
        Project.deadline < today,
        Project.workflow_phase != WorkflowPhase.COMPLETE.value,
    )
    projects_past_deadline = int((await session.execute(q_late)).scalar_one() or 0)

    return DashboardSummaryResponse(
        projects_by_phase=projects_by_phase,
        pending_task_cards=pending_task_cards,
        projects_past_deadline=projects_past_deadline,
    )
