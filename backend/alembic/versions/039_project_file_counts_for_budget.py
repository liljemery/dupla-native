"""project_files counts_for_budget

Revision ID: 039_file_counts_for_budget
Revises: 038_workspace_backfill
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "039_file_counts_for_budget"
down_revision = "038_workspace_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {c["name"] for c in inspector.get_columns("project_files")}
    if "counts_for_budget" in column_names:
        return

    op.add_column(
        "project_files",
        sa.Column("counts_for_budget", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("project_files", "counts_for_budget", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {c["name"] for c in inspector.get_columns("project_files")}
    if "counts_for_budget" not in column_names:
        return

    op.drop_column("project_files", "counts_for_budget")
