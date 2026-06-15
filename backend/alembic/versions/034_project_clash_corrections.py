"""Revision: clash correction uploads + reanalysis lifecycle

Revises: 033_project_clash_workflow
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "034_project_clash_corrections"
down_revision = "033_project_clash_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_clash_corrections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clash_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("project_clash_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("project_clash_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target", sa.String(16), nullable=False),
        sa.Column("revision_name", sa.String(255), nullable=False),
        sa.Column("original_dwg", sa.String(512), nullable=True),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("uploaded_by", sa.String(255), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.String(32), nullable=True),
        sa.Column("reanalysis_run_id", sa.String(128), nullable=True),
    )
    op.create_index(
        "ix_project_clash_corrections_clash_item_id",
        "project_clash_corrections",
        ["clash_item_id"],
    )
    op.create_index(
        "ix_project_clash_corrections_job_id",
        "project_clash_corrections",
        ["job_id"],
    )

    op.add_column(
        "project_clash_events",
        sa.Column("correction_id", UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_clash_events", "correction_id")
    op.drop_index(
        "ix_project_clash_corrections_job_id", table_name="project_clash_corrections"
    )
    op.drop_index(
        "ix_project_clash_corrections_clash_item_id",
        table_name="project_clash_corrections",
    )
    op.drop_table("project_clash_corrections")
