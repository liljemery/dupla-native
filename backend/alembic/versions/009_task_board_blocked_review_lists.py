"""Add Bloqueado and En revisión task lists

Revision ID: 009_task_board_blocked_review
Revises: 008_project_updated_at
"""

from collections.abc import Sequence
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_task_board_blocked_review"
down_revision: Optional[str] = "008_project_updated_at"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

LIST_TODO = "a0000001-0000-4000-8000-000000000001"
LIST_DOING = "a0000001-0000-4000-8000-000000000002"
LIST_DONE = "a0000001-0000-4000-8000-000000000003"
LIST_BLOCKED = "a0000001-0000-4000-8000-000000000004"
LIST_REVIEW = "a0000001-0000-4000-8000-000000000005"


def upgrade() -> None:
    op.execute(
        sa.text(
            f"UPDATE task_lists SET position = 4 WHERE id = '{LIST_DONE}'::uuid"
        )
    )
    op.execute(
        sa.text(
            f"UPDATE task_lists SET position = 2 WHERE id = '{LIST_DOING}'::uuid"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO task_lists (id, title, position) VALUES "
            f"('{LIST_BLOCKED}'::uuid, 'Bloqueado', 1), "
            f"('{LIST_REVIEW}'::uuid, 'En revisión', 3)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DELETE FROM task_lists WHERE id IN ('{LIST_BLOCKED}'::uuid, '{LIST_REVIEW}'::uuid)"))
    op.execute(
        sa.text(
            f"UPDATE task_lists SET position = 2 WHERE id = '{LIST_DONE}'::uuid"
        )
    )
    op.execute(
        sa.text(
            f"UPDATE task_lists SET position = 1 WHERE id = '{LIST_DOING}'::uuid"
        )
    )
