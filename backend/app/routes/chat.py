from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis_client import chat_message_epoch_bump
from app.db.session import get_db
from app.dependencies import get_current_user, get_workspace_context
from app.domain.workspace_context import WorkspaceContext
from app.models.user import User
from app.schemas.chat import (
    ChatConversationResponse,
    ChatDirectCreateRequest,
    ChatGroupCreateRequest,
    ChatMessageResponse,
    ChatPostRequest,
    ChatUserDirectoryItem,
)
from app.services.chat_service import ChatService
from app.services.workspace_bootstrap_service import general_conversation_uuid_for_workspace

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get(
    "/conversations",
    response_model=list[ChatConversationResponse],
    summary="Listar conversaciones",
    description="Incluye el canal general y los chats directos o grupos en los que participas.",
)
async def list_conversations(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[ChatConversationResponse]:
    svc = ChatService(session, ws_ctx.workspace_id)
    return await svc.list_conversations(current)


@router.post(
    "/conversations/direct",
    response_model=ChatConversationResponse,
    summary="Abrir u obtener chat directo",
)
async def open_direct_conversation(
    body: ChatDirectCreateRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ChatConversationResponse:
    svc = ChatService(session, ws_ctx.workspace_id)
    res = await svc.get_or_create_direct(current, body.user_uuid)
    await session.commit()
    return res


@router.post(
    "/conversations/group",
    response_model=ChatConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear grupo",
)
async def create_group_conversation(
    body: ChatGroupCreateRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ChatConversationResponse:
    svc = ChatService(session, ws_ctx.workspace_id)
    res = await svc.create_group(current, body.title, body.member_uuids)
    await session.commit()
    return res


@router.get(
    "/directory",
    response_model=list[ChatUserDirectoryItem],
    summary="Usuarios para chat",
    description="Lista de usuarios (excepto tú) para iniciar un chat directo o armar un grupo.",
)
async def chat_directory(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[ChatUserDirectoryItem]:
    svc = ChatService(session, ws_ctx.workspace_id)
    return await svc.list_directory(current)


@router.delete(
    "/conversations/{conversation_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar conversación",
    description="Solo chats directos o grupos. No aplica al canal general ni a chats de proyecto.",
)
async def delete_conversation(
    conversation_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> None:
    svc = ChatService(session, ws_ctx.workspace_id)
    await svc.delete_conversation(current, conversation_uuid)
    await session.commit()
    await chat_message_epoch_bump(conversation_uuid, ws_ctx.workspace_id)


@router.get(
    "/conversations/{conversation_uuid}/messages",
    response_model=list[ChatMessageResponse],
    summary="Mensajes de una conversación",
)
async def list_conversation_messages(
    conversation_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    after_uuid: Annotated[Optional[UUID], Query(description="UUID del último mensaje conocido")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[ChatMessageResponse]:
    svc = ChatService(session, ws_ctx.workspace_id)
    return await svc.list_conversation_messages(current, conversation_uuid, after_uuid, limit)


@router.post(
    "/conversations/{conversation_uuid}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar mensaje en una conversación",
)
async def post_conversation_message(
    conversation_uuid: UUID,
    body: ChatPostRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ChatMessageResponse:
    svc = ChatService(session, ws_ctx.workspace_id)
    msg = await svc.post_conversation_message(current, conversation_uuid, body)
    await session.commit()
    await chat_message_epoch_bump(conversation_uuid, ws_ctx.workspace_id)
    return msg


@router.get(
    "/messages",
    response_model=list[ChatMessageResponse],
    summary="Mensajes del chat general (compatibilidad)",
    description="Equivalente al canal «Avisos generales». Preferir /conversations/{uuid}/messages.",
)
async def list_chat_messages(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    after_uuid: Annotated[Optional[UUID], Query(description="UUID del último mensaje conocido")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[ChatMessageResponse]:
    svc = ChatService(session, ws_ctx.workspace_id)
    return await svc.list_messages(current, after_uuid, limit)


@router.post(
    "/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar al chat general (compatibilidad)",
)
async def post_chat_message(
    body: ChatPostRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ChatMessageResponse:
    svc = ChatService(session, ws_ctx.workspace_id)
    msg = await svc.post_message(current, body)
    await session.commit()
    await chat_message_epoch_bump(
        general_conversation_uuid_for_workspace(ws_ctx.workspace_id),
        ws_ctx.workspace_id,
    )
    return msg
