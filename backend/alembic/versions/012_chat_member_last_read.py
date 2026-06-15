"""chat_conversation_members: last_read_at for unread counts

Revision ID: 012_chat_member_last_read
Revises: 011_task_card_created_phase
"""

from collections.abc import Sequence
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_chat_member_last_read"
down_revision: Optional[str] = "011_task_card_created_phase"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column(
        "chat_conversation_members",
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_conversation_members", "last_read_at")
