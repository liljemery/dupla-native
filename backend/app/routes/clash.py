from datetime import datetime
from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_workspace_context, require_budget_access
from app.domain.workspace_context import WorkspaceContext
from app.models.user import User
from app.services.clash_export_service import ClashExportService, content_disposition_header
from app.services.clash_service import ClashService
from app.services.control_points_service import ControlPointsService

router = APIRouter(prefix="/api/projects", tags=["clash"])


class EnqueueClashJobRequest(BaseModel):
    coordination_profile: Optional[str] = None
    folder_uuid: Optional[UUID] = None


class ClashJobResponse(BaseModel):
    id: UUID
    project_id: UUID
    job_id: str
    status: str
    coordination_profile: Optional[str]
    error: Optional[str]
    progress: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class ProjectFilesCountResponse(BaseModel):
    total: int


def _clash_job_response(job) -> ClashJobResponse:
    progress = getattr(job, "extraction_progress", None)
    return ClashJobResponse(
        id=job.id,
        project_id=job.project_id,
        job_id=job.job_id,
        status=job.status,
        coordination_profile=job.coordination_profile,
        error=job.error,
        progress=progress if isinstance(progress, dict) else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get(
    "/{project_uuid}/files/count",
    response_model=ProjectFilesCountResponse,
    summary="Total project files across all folders",
)
async def get_project_files_count(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ProjectFilesCountResponse:
    svc = ClashService(session, ws_ctx.workspace_id)
    total = await svc.count_all_project_files(current, project_uuid)
    return ProjectFilesCountResponse(total=total)


@router.get(
    "/{project_uuid}/coordination/folders",
    summary="List all file folders with paths for coordination picker",
    response_model=list[dict[str, Any]],
)
async def list_coordination_folders(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[dict[str, Any]]:
    svc = ClashService(session, ws_ctx.workspace_id)
    return await svc.list_coordination_folders(current, project_uuid)


@router.get(
    "/{project_uuid}/coordination/inventory",
    summary="Pre-flight inventory for clash analysis from a source folder",
    response_model=dict[str, Any],
)
async def get_coordination_inventory(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    folder_uuid: Annotated[Optional[UUID], Query()] = None,
) -> dict[str, Any]:
    svc = ClashService(session, ws_ctx.workspace_id)
    return await svc.get_coordination_inventory(current, project_uuid, folder_uuid=folder_uuid)


@router.post(
    "/{project_uuid}/clash/jobs",
    response_model=ClashJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue clash detection job",
)
async def enqueue_clash_job(
    project_uuid: UUID,
    body: EnqueueClashJobRequest,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ClashJobResponse:
    svc = ClashService(session, ws_ctx.workspace_id)
    job = await svc.enqueue_clash_job(
        current,
        project_uuid,
        profile_slug=body.coordination_profile,
        folder_uuid=body.folder_uuid,
    )
    await session.commit()
    return _clash_job_response(job)


@router.get(
    "/{project_uuid}/clash/jobs/latest",
    response_model=ClashJobResponse,
    summary="Get latest clash job status (syncs from coordination service)",
)
async def get_latest_clash_job(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ClashJobResponse:
    svc = ClashService(session, ws_ctx.workspace_id)
    job = await svc.get_latest_job(current, project_uuid)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No clash job found for this project")
    job = await svc.sync_job_status(job)
    await session.commit()
    return _clash_job_response(job)


@router.get(
    "/{project_uuid}/structural-analysis-report",
    summary="Get structural / clash analysis report for Hallazgos tab",
    response_model=dict[str, Any],
)
async def get_structural_analysis_report(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    svc = ClashService(session, ws_ctx.workspace_id)
    report = await svc.get_structural_analysis_report(current, project_uuid)
    await session.commit()
    return report


@router.get(
    "/{project_uuid}/clash/jobs/latest/exports/technical.pdf",
    summary="Download technical clash report PDF for the latest completed job",
)
async def export_latest_clash_technical_pdf(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = ClashExportService(session, ws_ctx.workspace_id)
    data, filename = await svc.export_technical_pdf(current, project_uuid)
    await session.commit()
    return Response(
        content=data,
        media_type="application/pdf",
        headers=content_disposition_header(filename),
    )


@router.get(
    "/{project_uuid}/clash/jobs/latest/exports/human.pdf",
    summary="Download human/architect clash report PDF for the latest completed job",
)
async def export_latest_clash_human_pdf(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = ClashExportService(session, ws_ctx.workspace_id)
    data, filename = await svc.export_human_pdf(current, project_uuid)
    await session.commit()
    return Response(
        content=data,
        media_type="application/pdf",
        headers=content_disposition_header(filename),
    )


@router.get(
    "/{project_uuid}/clash/jobs/{job_id}/exports/technical.pdf",
    summary="Download technical clash report PDF for a specific job",
)
async def export_clash_technical_pdf(
    project_uuid: UUID,
    job_id: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = ClashExportService(session, ws_ctx.workspace_id)
    data, filename = await svc.export_technical_pdf(current, project_uuid, job_id=job_id)
    await session.commit()
    return Response(
        content=data,
        media_type="application/pdf",
        headers=content_disposition_header(filename),
    )


@router.get(
    "/{project_uuid}/clash/jobs/{job_id}/exports/human.pdf",
    summary="Download human/architect clash report PDF for a specific job",
)
async def export_clash_human_pdf(
    project_uuid: UUID,
    job_id: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = ClashExportService(session, ws_ctx.workspace_id)
    data, filename = await svc.export_human_pdf(current, project_uuid, job_id=job_id)
    await session.commit()
    return Response(
        content=data,
        media_type="application/pdf",
        headers=content_disposition_header(filename),
    )


# ---------------------------------------------------------------------------
# Layer C — Manual alignment control points
# ---------------------------------------------------------------------------


class ControlPointInput(BaseModel):
    label: str
    model_xy: list[float]
    ref_xy: list[float]


class UpsertControlPointsRequest(BaseModel):
    discipline: str
    reference: str = "ARQ"
    points: list[ControlPointInput]


@router.get(
    "/{project_uuid}/coordination/control-points",
    summary="List Layer C manual alignment control points for this project",
    response_model=list[dict[str, Any]],
)
async def list_control_points(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[dict[str, Any]]:
    svc = ControlPointsService(session, ws_ctx.workspace_id)
    return await svc.list_control_points(current, project_uuid)


@router.put(
    "/{project_uuid}/coordination/control-points",
    summary="Upsert Layer C manual alignment control points for a discipline",
    response_model=dict[str, Any],
)
async def upsert_control_points(
    project_uuid: UUID,
    body: UpsertControlPointsRequest,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    svc = ControlPointsService(session, ws_ctx.workspace_id)
    data = await svc.upsert_control_points(
        current,
        project_uuid,
        discipline=body.discipline,
        reference=body.reference,
        points=[p.model_dump() for p in body.points],
    )
    await session.commit()
    return data


@router.delete(
    "/{project_uuid}/coordination/control-points/{discipline}",
    summary="Delete Layer C control points for a discipline",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_control_points(
    project_uuid: UUID,
    discipline: str,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> None:
    svc = ControlPointsService(session, ws_ctx.workspace_id)
    await svc.delete_control_points(current, project_uuid, discipline)
    await session.commit()
