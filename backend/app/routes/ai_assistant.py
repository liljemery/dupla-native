from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.ai_assistant import AiAssistantChatRequest, AiAssistantChatResponse, AiAssistantHistoryResponse
from app.services.ai_assistant_service import AiAssistantService

router = APIRouter(prefix="/api/me", tags=["ai-assistant"])


@router.get(
    "/ai-assistant/history",
    response_model=AiAssistantHistoryResponse,
    summary="Historial del asistente IA (Redis)",
    description="Si estás en un proyecto, pasá `project_uuid` para recuperar el hilo contextual del proyecto.",
)
async def ai_assistant_history(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    project_uuid: Annotated[Optional[UUID], Query(description="UUID del proyecto abierto en el workspace")] = None,
) -> AiAssistantHistoryResponse:
    svc = AiAssistantService(session)
    return await svc.history(current, project_uuid)


@router.post(
    "/ai-assistant/chat",
    response_model=AiAssistantChatResponse,
    summary="Enviar mensaje a Dupla Assistant",
)
async def ai_assistant_chat(
    body: AiAssistantChatRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AiAssistantChatResponse:
    svc = AiAssistantService(session)
    return await svc.chat(current, body.message, project_uuid=body.project_uuid)
