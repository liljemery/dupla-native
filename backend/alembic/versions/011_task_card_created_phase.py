"""task_cards: fase del flujo en la que se creó la tarea

Revision ID: 011_task_card_created_phase
Revises: 010_user_roles_gerencia
"""

from collections.abc import Sequence
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_task_card_created_phase"
down_revision: Optional[str] = "010_user_roles_gerencia"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column(
        "task_cards",
        sa.Column("created_in_phase", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("task_cards", "created_in_phase")
