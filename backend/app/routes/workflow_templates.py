from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import require_permission, get_current_user, get_workspace_context
from app.domain.workspace_context import WorkspaceContext
from app.models.user import User
from app.models.workflow_template import WorkflowTemplate
from app.schemas.project import ProjectResponse
from app.schemas.workflow_template import (
    WorkflowTemplateCreateRequest,
    WorkflowTemplateDetailResponse,
    WorkflowTemplateListItemResponse,
    WorkflowTemplatePatchRequest,
    WorkflowTemplateStepsPutRequest,
)
from app.services.project_service import ProjectService
from app.repositories.workflow_template_repository import WorkflowTemplateRepository
from app.services.workflow_template_service import WorkflowTemplateService

router = APIRouter(prefix="/api/workflow-templates", tags=["workflow-templates"])


def _card_icon_for_template(t: WorkflowTemplate) -> str:
    steps = sorted(t.steps or [], key=lambda s: s.sort_index)
    return steps[0].icon_key if steps else t.icon_key


@router.get("", response_model=list[WorkflowTemplateListItemResponse])
async def list_workflow_templates(
    current: Annotated[User, Depends(require_permission("workflow.templates.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    q: Annotated[Optional[str], Query(description="Buscar por nombre de flujo o de proyecto")] = None,
) -> list[WorkflowTemplateListItemResponse]:
    repo = WorkflowTemplateRepository(session)
    rows = await repo.search_templates_and_projects(
        workspace_id=ws_ctx.workspace_id,
        query=q,
        preview_project_limit=5,
    )
    out: list[WorkflowTemplateListItemResponse] = []
    for t, previews in rows:
        out.append(
            WorkflowTemplateListItemResponse(
                uuid=t.id,
                name=t.name,
                description=t.description,
                icon_key=_card_icon_for_template(t),
                archived_at=t.archived_at,
                preview_projects=[{"uuid": str(uid), "name": name} for uid, name in previews],
            )
        )
    return out


@router.get("/active", response_model=list[WorkflowTemplateDetailResponse])
async def list_active_templates_short(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[WorkflowTemplateDetailResponse]:
    """Selector de plantilla al crear proyecto (todos los autenticados con módulo arquitectura)."""
    repo = WorkflowTemplateRepository(session)
    rows = await repo.list_active_templates(ws_ctx.workspace_id)
    return [WorkflowTemplateDetailResponse.from_template(t) for t in rows]


@router.delete(
    "/{template_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar flujo",
    description="Solo si ningún proyecto del workspace usa esta plantilla.",
)
async def delete_workflow_template(
    template_uuid: UUID,
    current: Annotated[User, Depends(require_permission("workflow.templates.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> None:
    svc = WorkflowTemplateService(session, ws_ctx.workspace_id)
    await svc.delete_template(template_uuid)
    await session.commit()


@router.get("/{template_uuid}", response_model=WorkflowTemplateDetailResponse)
async def get_workflow_template(
    template_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> WorkflowTemplateDetailResponse:
    t = await WorkflowTemplateService(session, ws_ctx.workspace_id).get_detail(template_uuid)
    return WorkflowTemplateDetailResponse.from_template(t)


@router.post("", response_model=WorkflowTemplateDetailResponse, status_code=status.HTTP_201_CREATED)
async def post_workflow_template(
    body: WorkflowTemplateCreateRequest,
    current: Annotated[User, Depends(require_permission("workflow.templates.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> WorkflowTemplateDetailResponse:
    svc = WorkflowTemplateService(session, ws_ctx.workspace_id)
    t = await svc.create_template(current.id, name=body.name, description=body.description)
    await session.commit()
    full = await svc.get_detail(t.id)
    return WorkflowTemplateDetailResponse.from_template(full)


@router.patch("/{template_uuid}", response_model=WorkflowTemplateDetailResponse)
async def patch_workflow_template(
    template_uuid: UUID,
    body: WorkflowTemplatePatchRequest,
    current: Annotated[User, Depends(require_permission("workflow.templates.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> WorkflowTemplateDetailResponse:
    svc = WorkflowTemplateService(session, ws_ctx.workspace_id)
    t = await svc.patch_template(
        template_uuid,
        name=body.name,
        description=body.description,
        archived=body.archived,
        icon_key=body.icon_key,
    )
    await session.commit()
    full = await svc.get_detail(t.id)
    return WorkflowTemplateDetailResponse.from_template(full)


@router.put("/{template_uuid}/steps", response_model=WorkflowTemplateDetailResponse)
async def put_workflow_template_steps(
    template_uuid: UUID,
    body: WorkflowTemplateStepsPutRequest,
    current: Annotated[User, Depends(require_permission("workflow.templates.manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> WorkflowTemplateDetailResponse:
    svc = WorkflowTemplateService(session, ws_ctx.workspace_id)
    t = await svc.replace_steps(template_uuid, body.steps)
    await session.commit()
    full = await svc.get_detail(t.id)
    return WorkflowTemplateDetailResponse.from_template(full)


@router.get("/{template_uuid}/projects", response_model=list[ProjectResponse])
async def list_projects_for_template(
    template_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[ProjectResponse]:
    ps = ProjectService(session, ws_ctx.workspace_id)
    projects = await ps.list_projects_for_template(current, template_uuid)
    return [ProjectResponse.from_project(p) for p in projects]
