from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user, get_workspace_context, require_task_creator, require_task_operator
from app.domain.workspace_context import WorkspaceContext
from app.models.user import User
from app.schemas.task_board import (
    TaskAssigneeOption,
    TaskBoardResponse,
    TaskCardCommentCreateRequest,
    TaskCardCommentResponse,
    TaskCardCreateRequest,
    TaskCardPatchRequest,
    TaskCardResponse,
)
from app.services.task_board_service import TaskBoardService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get(
    "/assignees",
    response_model=list[TaskAssigneeOption],
    summary="Usuarios asignables",
    description=(
        "Por defecto: usuarios con módulo Arquitectura. "
        "Con `project_uuid`, solo el equipo del proyecto (creador + miembros)."
    ),
)
async def list_task_assignees(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    project_uuid: Annotated[
        Optional[UUID],
        Query(description="Limitar al equipo de este proyecto"),
    ] = None,
) -> list[TaskAssigneeOption]:
    svc = TaskBoardService(session, ws_ctx.workspace_id)
    return await svc.list_assignees(current, project_uuid)


@router.get(
    "/board",
    response_model=TaskBoardResponse,
    summary="Tablero de tareas",
    description=(
        "Solo tareas visibles para el usuario actual (asignadas a él o sin asignar creadas por él). "
        "`project_uuid` filtra por proyecto. `include_archived=1` añade `archived_cards`. "
        "`assignee_uuid` distinto del usuario actual devuelve 403."
    ),
)
async def get_task_board(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    include_archived: Annotated[bool, Query(description="Incluir lista de tarjetas archivadas")] = False,
    mine: Annotated[bool, Query(description="Solo tareas asignadas a mí")] = False,
    assignee_uuid: Annotated[
        Optional[UUID],
        Query(description="Filtrar por usuario asignado (UUID)"),
    ] = None,
    project_uuid: Annotated[
        Optional[UUID],
        Query(description="Filtrar tarjetas vinculadas a un proyecto"),
    ] = None,
) -> TaskBoardResponse:
    svc = TaskBoardService(session, ws_ctx.workspace_id)
    return await svc.get_board(
        viewer=current,
        include_archived=include_archived,
        mine=mine,
        filter_assignee=assignee_uuid,
        filter_project=project_uuid,
    )


@router.post(
    "/cards",
    response_model=TaskCardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear tarjeta",
    description="Gerencia, Control, Presupuesto y Arquitectura.",
)
async def create_task_card(
    body: TaskCardCreateRequest,
    current: Annotated[User, Depends(require_task_creator)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> TaskCardResponse:
    svc = TaskBoardService(session, ws_ctx.workspace_id)
    card = await svc.create_card(current, body)
    await session.commit()
    loaded = await svc.get_card_for_response(card.id)
    return TaskCardResponse.from_card(loaded)


@router.get(
    "/cards/{card_uuid}/comments",
    response_model=list[TaskCardCommentResponse],
    summary="Comentarios de la tarjeta",
)
async def list_task_card_comments(
    card_uuid: UUID,
    current: Annotated[User, Depends(require_task_operator)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[TaskCardCommentResponse]:
    svc = TaskBoardService(session, ws_ctx.workspace_id)
    rows = await svc.list_card_comments(current, card_uuid)
    return [TaskCardCommentResponse.from_row(r) for r in rows]


@router.post(
    "/cards/{card_uuid}/comments",
    response_model=TaskCardCommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir comentario a la tarjeta",
)
async def create_task_card_comment(
    card_uuid: UUID,
    body: TaskCardCommentCreateRequest,
    current: Annotated[User, Depends(require_task_operator)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> TaskCardCommentResponse:
    svc = TaskBoardService(session, ws_ctx.workspace_id)
    row = await svc.add_card_comment(current, card_uuid, body.body)
    await session.commit()
    return TaskCardCommentResponse.from_row(row)


@router.patch(
    "/cards/{card_uuid}",
    response_model=TaskCardResponse,
    summary="Actualizar, mover, archivar o asignar tarjeta",
    description="Gerencia, Control, Presupuesto y Arquitectura.",
)
async def patch_task_card(
    card_uuid: UUID,
    body: TaskCardPatchRequest,
    current: Annotated[User, Depends(require_task_operator)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> TaskCardResponse:
    svc = TaskBoardService(session, ws_ctx.workspace_id)
    await svc.patch_card(current, card_uuid, body)
    await session.commit()
    loaded = await svc.get_card_for_response(card_uuid)
    return TaskCardResponse.from_card(loaded)


@router.delete(
    "/cards/{card_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar tarjeta del tablero",
)
async def delete_task_card(
    card_uuid: UUID,
    current: Annotated[User, Depends(require_task_operator)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = TaskBoardService(session, ws_ctx.workspace_id)
    await svc.delete_card(current, card_uuid)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
