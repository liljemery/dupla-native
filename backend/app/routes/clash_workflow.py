from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user, get_workspace_context
from app.domain.workspace_context import WorkspaceContext
from app.models.user import User
from app.services.clash_export_service import ClashExportService, content_disposition_header
from app.services.clash_service import ClashService
from app.services.clash_workflow_service import ClashWorkflowService

router = APIRouter(prefix="/api/projects", tags=["clash-workflow"])


class StatusBody(BaseModel):
    status: str
    comment: Optional[str] = None


class DecisionBody(BaseModel):
    decision: str
    comment: Optional[str] = None


class AssignBody(BaseModel):
    assigned_to: str


class CommentBody(BaseModel):
    comment: str


class ReanalysisBody(BaseModel):
    outcome: Optional[str] = None


def _query_filters(**kwargs: str | None) -> dict[str, str]:
    return {k: v for k, v in kwargs.items() if v}


@router.get("/{project_uuid}/clash-workflow/dashboard")
async def clash_workflow_dashboard(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    priority: Annotated[Optional[str], Query()] = None,
    severity: Annotated[Optional[str], Query()] = None,
    status_filter: Annotated[Optional[str], Query(alias="status")] = None,
    level_id: Annotated[Optional[str], Query()] = None,
    discipline: Annotated[Optional[str], Query()] = None,
    assigned_to: Annotated[Optional[str], Query()] = None,
    dwg: Annotated[Optional[str], Query()] = None,
) -> dict[str, Any]:
    svc = ClashWorkflowService(session, ws_ctx.workspace_id)
    data = await svc.get_dashboard(
        current,
        project_uuid,
        _query_filters(
            priority=priority,
            severity=severity,
            status=status_filter,
            level_id=level_id,
            discipline=discipline,
            assigned_to=assigned_to,
            dwg=dwg,
        ),
    )
    await session.commit()
    return data


@router.get("/{project_uuid}/clash-workflow/filters")
async def clash_workflow_filters(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    svc = ClashWorkflowService(session, ws_ctx.workspace_id)
    data = await svc.get_filters(current, project_uuid)
    await session.commit()
    return data


@router.get("/{project_uuid}/clash-workflow/clashes")
async def clash_workflow_list(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    priority: Annotated[Optional[str], Query()] = None,
    severity: Annotated[Optional[str], Query()] = None,
    status_filter: Annotated[Optional[str], Query(alias="status")] = None,
    level_id: Annotated[Optional[str], Query()] = None,
    discipline: Annotated[Optional[str], Query()] = None,
    assigned_to: Annotated[Optional[str], Query()] = None,
    dwg: Annotated[Optional[str], Query()] = None,
) -> list[dict[str, Any]]:
    svc = ClashWorkflowService(session, ws_ctx.workspace_id)
    rows = await svc.list_clashes(
        current,
        project_uuid,
        _query_filters(
            priority=priority,
            severity=severity,
            status=status_filter,
            level_id=level_id,
            discipline=discipline,
            assigned_to=assigned_to,
            dwg=dwg,
        ),
    )
    await session.commit()
    return rows


@router.get("/{project_uuid}/clash-workflow/clashes/{item_id}")
async def clash_workflow_detail(
    project_uuid: UUID,
    item_id: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    svc = ClashWorkflowService(session, ws_ctx.workspace_id)
    data = await svc.get_clash_detail(current, project_uuid, item_id)
    await session.commit()
    return data


@router.post("/{project_uuid}/clash-workflow/clashes/{item_id}/status")
async def clash_workflow_status(
    project_uuid: UUID,
    item_id: UUID,
    body: StatusBody,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    svc = ClashWorkflowService(session, ws_ctx.workspace_id)
    data = await svc.change_status(current, project_uuid, item_id, body.status, body.comment)
    await session.commit()
    return data


@router.post("/{project_uuid}/clash-workflow/clashes/{item_id}/decision")
async def clash_workflow_decision(
    project_uuid: UUID,
    item_id: UUID,
    body: DecisionBody,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    svc = ClashWorkflowService(session, ws_ctx.workspace_id)
    data = await svc.record_decision(current, project_uuid, item_id, body.decision, body.comment)
    await session.commit()
    return data


@router.post("/{project_uuid}/clash-workflow/clashes/{item_id}/assign")
async def clash_workflow_assign(
    project_uuid: UUID,
    item_id: UUID,
    body: AssignBody,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    svc = ClashWorkflowService(session, ws_ctx.workspace_id)
    data = await svc.assign(current, project_uuid, item_id, body.assigned_to)
    await session.commit()
    return data


@router.post("/{project_uuid}/clash-workflow/clashes/{item_id}/comment")
async def clash_workflow_comment(
    project_uuid: UUID,
    item_id: UUID,
    body: CommentBody,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    svc = ClashWorkflowService(session, ws_ctx.workspace_id)
    data = await svc.add_comment(current, project_uuid, item_id, body.comment)
    await session.commit()
    return data


@router.post("/{project_uuid}/clash-workflow/clashes/{item_id}/corrections")
async def clash_workflow_upload_correction(
    project_uuid: UUID,
    item_id: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    target: Annotated[str, Form()],
    revision_name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    content = await file.read()
    svc = ClashWorkflowService(session, ws_ctx.workspace_id)
    data = await svc.upload_correction(
        current,
        project_uuid,
        item_id,
        target=target,
        revision_name=revision_name,
        filename=file.filename or "correccion.dwg",
        content=content,
    )
    await session.commit()
    return data


@router.post("/{project_uuid}/clash-workflow/clashes/{item_id}/reanalysis")
async def clash_workflow_reanalysis(
    project_uuid: UUID,
    item_id: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> dict[str, Any]:
    """Enqueue a real motor re-analysis for the corrected document pair.

    The item transitions to ``pending_reanalysis`` immediately. Resolution
    (``resolved`` / ``still_present``) is set automatically when the motor job
    completes.
    """
    svc = ClashWorkflowService(session, ws_ctx.workspace_id)
    data = await svc.request_reanalysis(current, project_uuid, item_id)
    await session.commit()
    return data


@router.get("/{project_uuid}/clash-workflow/tiles/{filename}")
async def clash_workflow_tile(
    project_uuid: UUID,
    filename: str,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> FileResponse:
    clash_svc = ClashService(session, ws_ctx.workspace_id)
    job = await clash_svc.get_latest_job(current, project_uuid)
    if job is None or job.status != "completed":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tile not found")
    wf = ClashWorkflowService(session, ws_ctx.workspace_id)
    await wf.ensure_ingested(job, actor=current.email)
    path = wf.resolve_tile(job, filename)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tile not found")
    return FileResponse(path, media_type="image/svg+xml")


@router.get("/{project_uuid}/clash/jobs/latest/exports/technical.xlsx")
async def export_latest_clash_technical_excel(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = ClashExportService(session, ws_ctx.workspace_id)
    data, filename = await svc.export_technical_excel(current, project_uuid)
    await session.commit()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition_header(filename),
    )


@router.get("/{project_uuid}/clash/jobs/{job_id}/exports/technical.xlsx")
async def export_clash_technical_excel(
    project_uuid: UUID,
    job_id: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = ClashExportService(session, ws_ctx.workspace_id)
    data, filename = await svc.export_technical_excel(current, project_uuid, job_id=job_id)
    await session.commit()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition_header(filename),
    )


@router.get("/{project_uuid}/clash/jobs/latest/exports/final-technical.pdf")
async def export_final_technical_pdf(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = ClashExportService(session, ws_ctx.workspace_id)
    data, filename = await svc.export_final_technical_pdf(current, project_uuid)
    await session.commit()
    return Response(content=data, media_type="application/pdf", headers=content_disposition_header(filename))


@router.get("/{project_uuid}/clash/jobs/latest/exports/final-technical.xlsx")
async def export_final_technical_excel(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = ClashExportService(session, ws_ctx.workspace_id)
    data, filename = await svc.export_final_technical_excel(current, project_uuid)
    await session.commit()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=content_disposition_header(filename),
    )


@router.get("/{project_uuid}/clash/jobs/latest/exports/final-human.pdf")
async def export_final_human_pdf(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = ClashExportService(session, ws_ctx.workspace_id)
    data, filename = await svc.export_final_human_pdf(current, project_uuid)
    await session.commit()
    return Response(content=data, media_type="application/pdf", headers=content_disposition_header(filename))
