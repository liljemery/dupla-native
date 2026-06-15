"""task_card_comments

Revision ID: 013
Revises: 012
Create Date: 2026-04-18

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "013_task_card_comments"
down_revision = "012_chat_member_last_read"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_card_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["card_id"], ["task_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_card_comments_card_id",
        "task_card_comments",
        ["card_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_task_card_comments_card_id", table_name="task_card_comments")
    op.drop_table("task_card_comments")
