"""chat conversations (general, direct, group)

Revision ID: 004_chat_conversations
Revises: 003_task_card_assignee_archive
"""

import uuid
from collections.abc import Sequence
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_chat_conversations"
down_revision: Optional[str] = "003_task_card_assignee_archive"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

GENERAL_CONVERSATION_ID = "b0000001-0000-4000-8000-000000000001"


def upgrade() -> None:
    kind_enum = postgresql.ENUM("GENERAL", "DIRECT", "GROUP", name="chat_conversation_kind", create_type=True)
    kind_enum.create(op.get_bind(), checkfirst=True)
    kind_column = postgresql.ENUM(
        "GENERAL", "DIRECT", "GROUP", name="chat_conversation_kind", create_type=False
    )

    op.create_table(
        "chat_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", kind_column, nullable=False),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "chat_conversation_members",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["chat_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("conversation_id", "user_id"),
    )

    op.add_column(
        "chat_messages",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    general_uuid = uuid.UUID(GENERAL_CONVERSATION_ID)
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO chat_conversations (id, kind, title, created_at, last_message_at) "
            "VALUES (:id, 'GENERAL', NULL, NOW(), NULL)"
        ),
        {"id": general_uuid},
    )
    conn.execute(
        sa.text("UPDATE chat_messages SET conversation_id = :id WHERE conversation_id IS NULL"),
        {"id": general_uuid},
    )

    op.alter_column("chat_messages", "conversation_id", nullable=False)
    op.create_foreign_key(
        "fk_chat_messages_conversation_id",
        "chat_messages",
        "chat_conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])
    op.create_index(
        "ix_chat_messages_conversation_created",
        "chat_messages",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_conversation_created", table_name="chat_messages")
    op.drop_index("ix_chat_messages_conversation_id", table_name="chat_messages")
    op.drop_constraint("fk_chat_messages_conversation_id", "chat_messages", type_="foreignkey")
    op.drop_column("chat_messages", "conversation_id")
    op.drop_table("chat_conversation_members")
    op.drop_table("chat_conversations")
    kind_enum = postgresql.ENUM("GENERAL", "DIRECT", "GROUP", name="chat_conversation_kind", create_type=False)
    kind_enum.drop(op.get_bind(), checkfirst=True)
