"""user roles: GERENCIA, CONTROL, PRESUPUESTO, ARQUITECTURA

Revision ID: 010_user_roles_gerencia
Revises: 009_task_board_blocked_review
"""

from collections.abc import Sequence
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_user_roles_gerencia"
down_revision: Optional[str] = "009_task_board_blocked_review"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for v in ("GERENCIA", "CONTROL", "PRESUPUESTO", "ARQUITECTURA"):
            op.execute(sa.text(f"ALTER TYPE user_role ADD VALUE '{v}'"))
    op.execute(
        sa.text(
            "UPDATE users SET role = 'GERENCIA'::user_role WHERE role::text = 'MASTER'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE users SET role = 'CONTROL'::user_role WHERE role::text = 'COORDINATOR'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE users SET role = 'PRESUPUESTO'::user_role WHERE role::text = 'WORKER'"
        )
    )


def downgrade() -> None:
    raise NotImplementedError("No se revierte el cambio de roles de usuario")
