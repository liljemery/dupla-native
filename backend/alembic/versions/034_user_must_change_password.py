"""Revision: user must_change_password flag

Revises: 033_password_reset_tokens
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "034_user_must_change_password"
down_revision = "033_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.execute(sa.text("UPDATE users SET must_change_password = false"))
    op.alter_column("users", "must_change_password", server_default=sa.text("true"))


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
