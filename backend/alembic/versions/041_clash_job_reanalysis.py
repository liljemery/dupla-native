"""Add reanalysis fields to project_clash_jobs and project_control_points table

Revision ID: 041_clash_job_reanalysis
Revises: 040_aps_viewer_calibration
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "041_clash_job_reanalysis"
down_revision = "040_aps_viewer_calibration"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table_name)}


def _tables() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def upgrade() -> None:
    cols = _columns("project_clash_jobs")
    if "is_reanalysis" not in cols:
        op.add_column(
            "project_clash_jobs",
            sa.Column("is_reanalysis", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "reanalysis_item_uuid" not in cols:
        op.add_column(
            "project_clash_jobs",
            sa.Column(
                "reanalysis_item_uuid",
                UUID(as_uuid=True),
                sa.ForeignKey("project_clash_items.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    if "project_control_points" not in _tables():
        op.create_table(
            "project_control_points",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "project_id",
                UUID(as_uuid=True),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("discipline", sa.String(64), nullable=False),
            sa.Column("reference", sa.String(64), nullable=False, server_default="ARQ"),
            sa.Column("points", JSONB, nullable=False, server_default="[]"),
            sa.Column("created_by", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "discipline", name="uq_control_points_project_discipline"),
        )


def downgrade() -> None:
    if "project_control_points" in _tables():
        op.drop_table("project_control_points")

    cols = _columns("project_clash_jobs")
    if "reanalysis_item_uuid" in cols:
        op.drop_column("project_clash_jobs", "reanalysis_item_uuid")
    if "is_reanalysis" in cols:
        op.drop_column("project_clash_jobs", "is_reanalysis")
