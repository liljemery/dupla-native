"""Revision: clash job export metadata (folder, fingerprint, run_sequence)

Revises: 031_project_clash_jobs
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "032_clash_job_export_metadata"
down_revision = "031_project_clash_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_clash_jobs", sa.Column("folder_id", UUID(as_uuid=True), nullable=True))
    op.add_column("project_clash_jobs", sa.Column("folder_name", sa.String(255), nullable=True))
    op.add_column("project_clash_jobs", sa.Column("cad_fingerprint", sa.String(64), nullable=True))
    op.add_column("project_clash_jobs", sa.Column("run_sequence", sa.Integer(), nullable=True))
    op.add_column(
        "project_clash_jobs",
        sa.Column("triggered_by_user_id", UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_clash_jobs", "triggered_by_user_id")
    op.drop_column("project_clash_jobs", "run_sequence")
    op.drop_column("project_clash_jobs", "cad_fingerprint")
    op.drop_column("project_clash_jobs", "folder_name")
    op.drop_column("project_clash_jobs", "folder_id")
