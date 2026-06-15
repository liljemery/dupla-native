"""Revision: user is_team_leader flag

Revises: 034_user_must_change_password
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "035_user_is_team_leader"
down_revision = "034_user_must_change_password"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_team_leader", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("users", "is_team_leader")
