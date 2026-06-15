from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.chat_message import ChatMessage
from app.models.user import User


class ChatAuthorResponse(BaseModel):
    uuid: UUID
    email: EmailStr
    first_name: str
    last_name: str


class ChatMessageResponse(BaseModel):
    uuid: UUID
    conversation_uuid: UUID
    body: str
    created_at: datetime
    author: ChatAuthorResponse

    @classmethod
    def from_row(cls, msg: ChatMessage, author: User) -> ChatMessageResponse:
        return cls(
            uuid=msg.id,
            conversation_uuid=msg.conversation_id,
            body=msg.body,
            created_at=msg.created_at,
            author=ChatAuthorResponse(
                uuid=author.id,
                email=author.email,
                first_name=author.first_name,
                last_name=author.last_name,
            ),
        )


class ChatPostRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ChatConversationResponse(BaseModel):
    uuid: UUID
    kind: str
    display_title: str
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    unread_count: int = 0
    participant_count: Optional[int] = None
    participants: Optional[list[ChatAuthorResponse]] = None
    project_uuid: Optional[UUID] = Field(
        default=None,
        description="Solo conversaciones PROJECT: UUID público de la obra.",
    )


class ChatDirectCreateRequest(BaseModel):
    user_uuid: UUID


class ChatGroupCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    member_uuids: list[UUID] = Field(min_length=1, max_length=50)


class ChatUserDirectoryItem(BaseModel):
    uuid: UUID
    email: EmailStr
    first_name: str
    last_name: str
