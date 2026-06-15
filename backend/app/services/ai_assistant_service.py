from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis_client import ai_assistant_context_load, ai_assistant_context_save
from app.config import get_settings
from app.domain.ai_project_snapshot import build_project_snapshot_markdown
from app.domain.platform_ai_context_loader import build_ai_assistant_system_prompt
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.schemas.ai_assistant import (
    AiAssistantChatResponse,
    AiAssistantHistoryMessage,
    AiAssistantHistoryResponse,
)
from app.services.project_service import ProjectService


class AiAssistantService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _workspace_id(self, user: User) -> UUID:
        if user.active_workspace_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sin workspace activo",
            )
        return user.active_workspace_id

    async def history(self, user: User, project_uuid: Optional[UUID] = None) -> AiAssistantHistoryResponse:
        workspace_id = await self._workspace_id(user)
        turns = await ai_assistant_context_load(user.id, workspace_id, project_uuid)
        return AiAssistantHistoryResponse(
            messages=[AiAssistantHistoryMessage(role=m["role"], content=m["content"]) for m in turns],
        )

    async def _project_snapshot_block(self, user: User, project_uuid: UUID) -> str:
        workspace_id = await self._workspace_id(user)
        project_svc = ProjectService(self._session, workspace_id)
        project = await project_svc.get_project(user, project_uuid)
        repo = ProjectRepository(self._session)
        file_count = await repo.count_project_files(project.id)
        members = await project_svc.list_project_members(user, project_uuid)
        return build_project_snapshot_markdown(
            project,
            file_count=file_count,
            member_count=len(members),
        )

    async def chat(
        self,
        user: User,
        message: str,
        *,
        project_uuid: Optional[UUID] = None,
    ) -> AiAssistantChatResponse:
        settings = get_settings()
        key = (settings.openai_api_key or "").strip()
        if not key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dupla Assistant no configurado (definí OPENAI_API_KEY en backend/.env).",
            )

        system_prompt = build_ai_assistant_system_prompt()
        if project_uuid is not None:
            snapshot = await self._project_snapshot_block(user, project_uuid)
            system_prompt += (
                "\n\n---\n\n## Proyecto que el usuario tiene abierto ahora\n\n"
                "El usuario está dentro del workspace de este proyecto. Usá estos datos para preguntas sobre "
                "**este** proyecto. No mezcles con otros proyectos.\n\n"
                f"{snapshot}"
            )

        workspace_id = await self._workspace_id(user)
        prior = await ai_assistant_context_load(user.id, workspace_id, project_uuid)
        max_msgs = settings.ai_assistant_max_context_messages
        trimmed = prior[-max_msgs:] if len(prior) > max_msgs else prior

        api_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        api_messages.extend(trimmed)
        api_messages.append({"role": "user", "content": message.strip()})

        client = AsyncOpenAI(api_key=key)
        completion = await client.chat.completions.create(
            model=settings.openai_model,
            messages=api_messages,
            temperature=0.2,
            max_tokens=2048,
        )
        choice = completion.choices[0].message.content
        reply = (choice or "").strip()
        if not reply:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="El modelo no devolvió texto.",
            )

        updated = trimmed + [{"role": "user", "content": message.strip()}, {"role": "assistant", "content": reply}]
        if len(updated) > max_msgs:
            updated = updated[-max_msgs:]
        await ai_assistant_context_save(
            user.id,
            workspace_id,
            updated,
            settings.ai_assistant_context_ttl_seconds,
            project_uuid=project_uuid,
        )

        return AiAssistantChatResponse(reply=reply)
