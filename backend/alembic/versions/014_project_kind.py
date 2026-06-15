"""project_kind on projects

Revision ID: 014_project_kind
Revises: 013_task_card_comments
Create Date: 2026-04-18

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "014_project_kind"
down_revision = "013_task_card_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("project_kind", sa.String(length=32), nullable=False, server_default="RESIDENTIAL"),
    )
    op.alter_column("projects", "project_kind", server_default=None)


def downgrade() -> None:
    op.drop_column("projects", "project_kind")
