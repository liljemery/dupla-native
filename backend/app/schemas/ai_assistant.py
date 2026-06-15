from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AiAssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=12000)
    """Si el usuario está en el workspace del proyecto, enviar su UUID para contexto e historial aparte."""

    project_uuid: Optional[UUID] = None


class AiAssistantChatResponse(BaseModel):
    reply: str


class AiAssistantHistoryMessage(BaseModel):
    role: str
    content: str


class AiAssistantHistoryResponse(BaseModel):
    messages: list[AiAssistantHistoryMessage]
