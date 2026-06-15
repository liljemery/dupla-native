"""task card assignee and archive

Revision ID: 003_task_card_assignee_archive
Revises: 002_chat_task_board
"""

from collections.abc import Sequence
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_task_card_assignee_archive"
down_revision: Optional[str] = "002_chat_task_board"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column(
        "task_cards",
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "task_cards",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "task_cards",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_task_cards_assignee_id_users",
        "task_cards",
        "users",
        ["assignee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_task_cards_assignee_id", "task_cards", ["assignee_id"])
    op.create_index("ix_task_cards_archived", "task_cards", ["archived"])


def downgrade() -> None:
    op.drop_index("ix_task_cards_archived", table_name="task_cards")
    op.drop_index("ix_task_cards_assignee_id", table_name="task_cards")
    op.drop_constraint("fk_task_cards_assignee_id_users", "task_cards", type_="foreignkey")
    op.drop_column("task_cards", "archived_at")
    op.drop_column("task_cards", "archived")
    op.drop_column("task_cards", "assignee_id")
