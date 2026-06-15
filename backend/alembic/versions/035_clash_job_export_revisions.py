"""Revision: per-job export revision counters

Revises: 034_project_clash_corrections
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "035_clash_job_export_revisions"
down_revision = "034_project_clash_corrections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_clash_jobs",
        sa.Column("export_revisions", JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("project_clash_jobs", "export_revisions")
