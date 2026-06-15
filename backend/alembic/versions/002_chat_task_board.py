"""chat messages and task board

Revision ID: 002_chat_task_board
Revises: 001_initial
"""

from collections.abc import Sequence
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_chat_task_board"
down_revision: Optional[str] = "001_initial"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

LIST_TODO = "a0000001-0000-4000-8000-000000000001"
LIST_DOING = "a0000001-0000-4000-8000-000000000002"
LIST_DONE = "a0000001-0000-4000-8000-000000000003"


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])

    op.create_table(
        "task_lists",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "task_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("list_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["list_id"], ["task_lists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_cards_list_id", "task_cards", ["list_id"])

    op.execute(
        sa.text(
            "INSERT INTO task_lists (id, title, position) VALUES "
            f"('{LIST_TODO}'::uuid, 'Por hacer', 0), "
            f"('{LIST_DOING}'::uuid, 'En progreso', 1), "
            f"('{LIST_DONE}'::uuid, 'Hecho', 2)"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_task_cards_list_id", table_name="task_cards")
    op.drop_table("task_cards")
    op.drop_table("task_lists")
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_table("chat_messages")
