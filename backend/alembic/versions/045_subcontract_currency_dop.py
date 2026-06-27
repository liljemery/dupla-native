"""Subcontract quote lines: default currency DOP (República Dominicana)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "045_subcontract_currency_dop"
down_revision = "044_task_board_canonical_lists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE subcontract_quote_lines SET currency = 'DOP' WHERE currency = 'MXN'"))
    op.alter_column(
        "subcontract_quote_lines",
        "currency",
        server_default="DOP",
        existing_type=sa.String(length=8),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "subcontract_quote_lines",
        "currency",
        server_default="MXN",
        existing_type=sa.String(length=8),
        existing_nullable=False,
    )
