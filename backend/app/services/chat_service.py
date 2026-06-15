from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, intersect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.chat_conversation import (
    ChatConversation,
    ChatConversationKind,
    ChatConversationMember,
)
from app.cache.redis_client import (
    cache_get_json,
    cache_set_json,
    chat_message_epoch_get,
    scoped_redis_key,
)
from app.config import get_settings
from app.models.chat_message import ChatMessage
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.repositories.workspace_repository import WorkspaceRepository
from app.services.project_service import ProjectService
from app.services.workspace_bootstrap_service import general_conversation_uuid_for_workspace
from app.schemas.chat import (
    ChatAuthorResponse,
    ChatConversationResponse,
    ChatMessageResponse,
    ChatPostRequest,
    ChatUserDirectoryItem,
)


def _chat_messages_cache_key(
    workspace_id: uuid.UUID,
    conversation_uuid: uuid.UUID,
    epoch: int,
    after_uuid: Optional[uuid.UUID],
    limit: int,
) -> str:
    after_part = str(after_uuid) if after_uuid is not None else "none"
    inner = f"chat:messages:{conversation_uuid}:{epoch}:{after_part}:{limit}"
    return scoped_redis_key(workspace_id, inner)


class ChatService:
    def __init__(self, session: AsyncSession, workspace_id: uuid.UUID) -> None:
        self._session = session
        self._workspace_id = workspace_id
        self._workspaces = WorkspaceRepository(session)

    def _general_conversation_id(self) -> uuid.UUID:
        return general_conversation_uuid_for_workspace(self._workspace_id)

    async def _get_general_conversation(self) -> ChatConversation:
        conv_id = self._general_conversation_id()
        conv = await self._session.get(ChatConversation, conv_id)
        if conv is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Canal general no configurado",
            )
        return conv

    async def _get_conversation(self, conversation_uuid: uuid.UUID) -> ChatConversation:
        conv = await self._session.get(ChatConversation, conversation_uuid)
        if conv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversación no encontrada")
        return conv

    async def _assert_can_access(self, user: User, conv: ChatConversation) -> None:
        if conv.workspace_id != self._workspace_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversación no encontrada")
        if conv.kind == ChatConversationKind.GENERAL:
            return
        if conv.kind == ChatConversationKind.PROJECT:
            stmt = select(ChatConversationMember).where(
                ChatConversationMember.conversation_id == conv.id,
                ChatConversationMember.user_id == user.id,
            )
            row = (await self._session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversación no encontrada")
            return
        stmt = select(ChatConversationMember).where(
            ChatConversationMember.conversation_id == conv.id,
            ChatConversationMember.user_id == user.id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversación no encontrada")

    async def _ensure_general_membership(self, user: User) -> None:
        conv_id = self._general_conversation_id()
        stmt = select(ChatConversationMember).where(
            ChatConversationMember.conversation_id == conv_id,
            ChatConversationMember.user_id == user.id,
        )
        if (await self._session.execute(stmt)).scalar_one_or_none() is None:
            self._session.add(
                ChatConversationMember(
                    conversation_id=conv_id,
                    user_id=user.id,
                )
            )
            await self._session.flush()

    async def _ensure_member(self, user: User, conv: ChatConversation) -> ChatConversationMember:
        stmt = select(ChatConversationMember).where(
            ChatConversationMember.conversation_id == conv.id,
            ChatConversationMember.user_id == user.id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return row
        m = ChatConversationMember(conversation_id=conv.id, user_id=user.id)
        self._session.add(m)
        await self._session.flush()
        return m

    async def _last_message_preview(self, conversation_id: uuid.UUID) -> Optional[str]:
        q = (
            select(ChatMessage.body)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        raw = (await self._session.execute(q)).scalar_one_or_none()
        if raw is None:
            return None
        text = " ".join(raw.strip().split())
        if len(text) <= 140:
            return text
        return text[:137] + "…"

    async def _participant_count(self, conversation_id: uuid.UUID) -> int:
        q = select(func.count()).select_from(ChatConversationMember).where(
            ChatConversationMember.conversation_id == conversation_id
        )
        return int((await self._session.execute(q)).scalar_one() or 0)

    async def _participants_by_conversation(
        self, conversation_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[ChatAuthorResponse]]:
        if not conversation_ids:
            return {}
        q = (
            select(
                ChatConversationMember.conversation_id,
                User.id,
                User.email,
                User.first_name,
                User.last_name,
            )
            .join(User, User.id == ChatConversationMember.user_id)
            .where(ChatConversationMember.conversation_id.in_(conversation_ids))
            .order_by(User.email.asc())
        )
        rows = list((await self._session.execute(q)).all())
        out: dict[uuid.UUID, list[ChatAuthorResponse]] = {}
        for conv_id, uid, email, fn, ln in rows:
            out.setdefault(conv_id, []).append(
                ChatAuthorResponse(uuid=uid, email=email, first_name=fn, last_name=ln)
            )
        return out

    async def _participants_by_project(
        self, project_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[ChatAuthorResponse]]:
        if not project_ids:
            return {}
        q = (
            select(
                ProjectMember.project_id,
                User.id,
                User.email,
                User.first_name,
                User.last_name,
            )
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id.in_(project_ids))
            .order_by(User.email.asc())
        )
        rows = list((await self._session.execute(q)).all())
        out: dict[uuid.UUID, list[ChatAuthorResponse]] = {}
        for project_id, uid, email, fn, ln in rows:
            out.setdefault(project_id, []).append(
                ChatAuthorResponse(uuid=uid, email=email, first_name=fn, last_name=ln)
            )
        return out

    async def _unread_count(self, user: User, conv: ChatConversation) -> int:
        await self._ensure_member(user, conv)
        stmt = select(ChatConversationMember).where(
            ChatConversationMember.conversation_id == conv.id,
            ChatConversationMember.user_id == user.id,
        )
        mem = (await self._session.execute(stmt)).scalar_one_or_none()
        if mem is None:
            return 0
        threshold = mem.last_read_at
        if threshold is None:
            threshold = datetime(1970, 1, 1, tzinfo=timezone.utc)
        q = (
            select(func.count())
            .select_from(ChatMessage)
            .where(
                ChatMessage.conversation_id == conv.id,
                ChatMessage.author_id != user.id,
                ChatMessage.created_at > threshold,
            )
        )
        return int((await self._session.execute(q)).scalar_one() or 0)

    async def _mark_conversation_read(self, user: User, conv: ChatConversation) -> None:
        mem = await self._ensure_member(user, conv)
        sub = select(func.max(ChatMessage.created_at)).where(ChatMessage.conversation_id == conv.id)
        mx = (await self._session.execute(sub)).scalar_one_or_none()
        if mx is not None:
            mem.last_read_at = mx

    async def _conversation_to_response(
        self,
        conv: ChatConversation,
        user: User,
        *,
        last_message_preview: Optional[str] = None,
        unread_count: int = 0,
        participant_count: Optional[int] = None,
        participants: Optional[list[ChatAuthorResponse]] = None,
    ) -> ChatConversationResponse:
        if conv.kind == ChatConversationKind.GENERAL:
            return ChatConversationResponse(
                uuid=conv.id,
                kind=conv.kind.value,
                display_title="Avisos generales",
                last_message_at=conv.last_message_at,
                last_message_preview=last_message_preview,
                unread_count=unread_count,
                participant_count=participant_count,
                participants=None,
            )
        if conv.kind == ChatConversationKind.GROUP:
            return ChatConversationResponse(
                uuid=conv.id,
                kind=conv.kind.value,
                display_title=(conv.title or "Grupo").strip() or "Grupo",
                last_message_at=conv.last_message_at,
                last_message_preview=last_message_preview,
                unread_count=unread_count,
                participant_count=participant_count,
                participants=participants,
            )
        if conv.kind == ChatConversationKind.PROJECT:
            title = "Proyecto"
            proj_uuid: Optional[uuid.UUID] = None
            if conv.project_id is not None:
                proj = await self._session.get(Project, conv.project_id)
                if proj is not None:
                    title = proj.name
                    proj_uuid = proj.id
            return ChatConversationResponse(
                uuid=conv.id,
                kind=conv.kind.value,
                display_title=f"Chat · {title}",
                last_message_at=conv.last_message_at,
                last_message_preview=last_message_preview,
                unread_count=unread_count,
                participant_count=participant_count,
                participants=participants,
                project_uuid=proj_uuid,
            )
        stmt = (
            select(User)
            .join(ChatConversationMember, ChatConversationMember.user_id == User.id)
            .where(
                ChatConversationMember.conversation_id == conv.id,
                User.id != user.id,
            )
        )
        other = (await self._session.execute(stmt)).scalar_one_or_none()
        label = other.email if other is not None else "Chat directo"
        return ChatConversationResponse(
            uuid=conv.id,
            kind=conv.kind.value,
            display_title=label,
            last_message_at=conv.last_message_at,
            last_message_preview=last_message_preview,
            unread_count=unread_count,
            participant_count=participant_count,
            participants=None,
        )

    async def list_conversations(self, user: User) -> list[ChatConversationResponse]:
        await self._ensure_general_membership(user)
        member_subq = select(ChatConversationMember.conversation_id).where(
            ChatConversationMember.user_id == user.id
        )
        q = select(ChatConversation).where(
            ChatConversation.workspace_id == self._workspace_id,
            (
                (ChatConversation.kind == ChatConversationKind.GENERAL)
                | (ChatConversation.id.in_(member_subq))
            ),
        )
        rows = list((await self._session.execute(q)).scalars().all())

        def sort_key(c: ChatConversation) -> tuple[int, float]:
            ts = (c.last_message_at or c.created_at).timestamp()
            primary = 0 if c.kind == ChatConversationKind.GENERAL else 1
            return (primary, -ts)

        rows.sort(key=sort_key)
        group_ids = [c.id for c in rows if c.kind == ChatConversationKind.GROUP]
        project_ids = [c.project_id for c in rows if c.kind == ChatConversationKind.PROJECT and c.project_id]
        participants_map = await self._participants_by_conversation(group_ids)
        project_participants_map = await self._participants_by_project(project_ids)
        out: list[ChatConversationResponse] = []
        for conv in rows:
            preview = await self._last_message_preview(conv.id)
            unread = await self._unread_count(user, conv)
            pcount = await self._participant_count(conv.id)
            parts: Optional[list[ChatAuthorResponse]] = None
            if conv.kind == ChatConversationKind.GROUP:
                parts = participants_map.get(conv.id)
            elif conv.kind == ChatConversationKind.PROJECT and conv.project_id is not None:
                parts = project_participants_map.get(conv.project_id)
                if parts is not None:
                    pcount = len(parts)
            out.append(
                await self._conversation_to_response(
                    conv,
                    user,
                    last_message_preview=preview,
                    unread_count=unread,
                    participant_count=pcount,
                    participants=parts,
                )
            )
        return out

    async def list_directory(self, user: User) -> list[ChatUserDirectoryItem]:
        member_ids = await self._workspaces.list_member_user_ids(self._workspace_id)
        if not member_ids:
            return []
        q = (
            select(User)
            .where(User.id.in_(member_ids), User.id != user.id)
            .order_by(User.email.asc())
        )
        users = list((await self._session.execute(q)).scalars().all())
        return [
            ChatUserDirectoryItem(
                uuid=u.id,
                email=u.email,
                first_name=u.first_name,
                last_name=u.last_name,
            )
            for u in users
        ]

    async def get_or_create_direct(self, user: User, other_uuid: uuid.UUID) -> ChatConversationResponse:
        if other_uuid == user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes abrir un chat contigo mismo",
            )
        other = await self._session.get(User, other_uuid)
        if other is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

        inter_q = intersect(
            select(ChatConversationMember.conversation_id).where(ChatConversationMember.user_id == user.id),
            select(ChatConversationMember.conversation_id).where(ChatConversationMember.user_id == other.id),
        )
        stmt = select(ChatConversation).where(
            ChatConversation.kind == ChatConversationKind.DIRECT,
            ChatConversation.id.in_(inter_q),
        )
        existing = (await self._session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return await self._conversation_to_response(existing, user)

        now = datetime.now(timezone.utc)
        conv = ChatConversation(
            id=uuid.uuid4(),
            kind=ChatConversationKind.DIRECT,
            title=None,
            created_at=now,
            last_message_at=None,
            workspace_id=self._workspace_id,
        )
        self._session.add(conv)
        self._session.add(ChatConversationMember(conversation_id=conv.id, user_id=user.id))
        self._session.add(ChatConversationMember(conversation_id=conv.id, user_id=other.id))
        await self._session.flush()
        return await self._conversation_to_response(conv, user)

    async def create_group(self, user: User, title: str, member_uuids: list[uuid.UUID]) -> ChatConversationResponse:
        ids_set: set[uuid.UUID] = {user.id}
        for uid in member_uuids:
            ids_set.add(uid)
        if len(ids_set) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Un grupo necesita al menos dos personas distintas",
            )

        for uid in ids_set:
            u = await self._session.get(User, uid)
            if u is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Usuario no encontrado: {uid}",
                )

        now = datetime.now(timezone.utc)
        conv = ChatConversation(
            id=uuid.uuid4(),
            kind=ChatConversationKind.GROUP,
            title=title.strip(),
            created_at=now,
            last_message_at=None,
            workspace_id=self._workspace_id,
        )
        self._session.add(conv)
        for uid in ids_set:
            self._session.add(ChatConversationMember(conversation_id=conv.id, user_id=uid))
        await self._session.flush()
        pcount = await self._participant_count(conv.id)
        pmap = await self._participants_by_conversation([conv.id])
        parts = pmap.get(conv.id)
        return await self._conversation_to_response(
            conv,
            user,
            participant_count=pcount,
            participants=parts,
        )

    async def list_conversation_messages(
        self,
        user: User,
        conversation_uuid: uuid.UUID,
        after_uuid: Optional[uuid.UUID],
        limit: int,
    ) -> list[ChatMessageResponse]:
        conv = await self._get_conversation(conversation_uuid)
        await self._assert_can_access(user, conv)
        cap = min(max(limit, 1), 200)
        settings = get_settings()
        epoch = await chat_message_epoch_get(conv.id, self._workspace_id)
        cache_key = _chat_messages_cache_key(self._workspace_id, conv.id, epoch, after_uuid, cap)
        cached = await cache_get_json(cache_key)
        if isinstance(cached, list):
            out = [ChatMessageResponse.model_validate(x) for x in cached]
            await self._mark_conversation_read(user, conv)
            await self._session.flush()
            return out
        if after_uuid is None:
            q = (
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conv.id)
                .options(joinedload(ChatMessage.author))
                .order_by(ChatMessage.created_at.desc())
                .limit(cap)
            )
            rows = list((await self._session.execute(q)).unique().scalars().all())
            rows.reverse()
        else:
            ref = await self._session.get(ChatMessage, after_uuid)
            if ref is None or ref.conversation_id != conv.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Mensaje de referencia no encontrado",
                )
            q = (
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conv.id)
                .options(joinedload(ChatMessage.author))
                .where(
                    (ChatMessage.created_at > ref.created_at)
                    | ((ChatMessage.created_at == ref.created_at) & (ChatMessage.id > ref.id))
                )
                .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
                .limit(cap)
            )
            rows = list((await self._session.execute(q)).unique().scalars().all())

        out: list[ChatMessageResponse] = []
        for msg in rows:
            author = msg.author
            if author is None:
                continue
            out.append(ChatMessageResponse.from_row(msg, author))
        await self._mark_conversation_read(user, conv)
        await self._session.flush()
        payload = [m.model_dump(mode="json") for m in out]
        await cache_set_json(cache_key, payload, settings.cache_ttl_seconds)
        return out

    async def post_conversation_message(
        self,
        user: User,
        conversation_uuid: uuid.UUID,
        body: ChatPostRequest,
    ) -> ChatMessageResponse:
        conv = await self._get_conversation(conversation_uuid)
        await self._assert_can_access(user, conv)
        now = datetime.now(timezone.utc)
        msg = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            author_id=user.id,
            body=body.body.strip(),
            created_at=now,
        )
        self._session.add(msg)
        conv.last_message_at = now
        await self._session.flush()
        return ChatMessageResponse.from_row(msg, user)

    async def list_messages(self, user: User, after_uuid: Optional[uuid.UUID], limit: int) -> list[ChatMessageResponse]:
        general = await self._get_general_conversation()
        return await self.list_conversation_messages(user, general.id, after_uuid, limit)

    async def post_message(self, author: User, body: ChatPostRequest) -> ChatMessageResponse:
        general = await self._get_general_conversation()
        return await self.post_conversation_message(author, general.id, body)

    async def delete_conversation(self, user: User, conversation_uuid: uuid.UUID) -> None:
        conv = await self._get_conversation(conversation_uuid)
        if conv.workspace_id != self._workspace_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversación no encontrada")
        if conv.kind in (ChatConversationKind.GENERAL, ChatConversationKind.PROJECT):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta conversación no se puede eliminar",
            )
        await self._assert_can_access(user, conv)
        await self._session.delete(conv)
        await self._session.flush()

    async def get_or_create_project_conversation(
        self,
        user: User,
        project_uuid: uuid.UUID,
    ) -> ChatConversationResponse:
        ps = ProjectService(self._session, self._workspace_id)
        project = await ps.get_project(user, project_uuid)
        stmt = select(ChatConversation).where(
            ChatConversation.kind == ChatConversationKind.PROJECT,
            ChatConversation.project_id == project.id,
            ChatConversation.workspace_id == self._workspace_id,
        )
        conv = (await self._session.execute(stmt)).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if conv is None:
            conv = ChatConversation(
                id=uuid.uuid4(),
                kind=ChatConversationKind.PROJECT,
                title=None,
                created_at=now,
                last_message_at=None,
                project_id=project.id,
                workspace_id=self._workspace_id,
            )
            self._session.add(conv)
            self._session.add(ChatConversationMember(conversation_id=conv.id, user_id=user.id))
            await self._session.flush()
        else:
            m_stmt = select(ChatConversationMember).where(
                ChatConversationMember.conversation_id == conv.id,
                ChatConversationMember.user_id == user.id,
            )
            existing_m = (await self._session.execute(m_stmt)).scalar_one_or_none()
            if existing_m is None:
                self._session.add(ChatConversationMember(conversation_id=conv.id, user_id=user.id))
                await self._session.flush()
        parts: Optional[list[ChatAuthorResponse]] = None
        pcount: Optional[int] = None
        if conv.project_id is not None:
            project_parts_map = await self._participants_by_project([conv.project_id])
            parts = project_parts_map.get(conv.project_id)
            if parts is not None:
                pcount = len(parts)
        return await self._conversation_to_response(
            conv,
            user,
            participant_count=pcount,
            participants=parts,
        )
