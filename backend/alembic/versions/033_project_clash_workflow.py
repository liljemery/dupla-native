"""Revision: live clash workflow items and events

Revises: 032_clash_job_export_metadata
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "033_project_clash_workflow"
down_revision = "032_clash_job_export_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_clash_jobs", sa.Column("output_dir", sa.Text(), nullable=True))

    op.create_table(
        "project_clash_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("project_clash_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clash_code", sa.String(64), nullable=False),
        sa.Column("priority", sa.String(8), nullable=False, server_default="P3"),
        sa.Column("severity", sa.String(16), nullable=False, server_default="low"),
        sa.Column("report_confidence", sa.String(16), nullable=False, server_default="low"),
        sa.Column("status", sa.String(32), nullable=False, server_default="detected"),
        sa.Column("reviewer_decision", sa.String(64), nullable=True),
        sa.Column("dwg_a", sa.String(512), nullable=True),
        sa.Column("dwg_b", sa.String(512), nullable=True),
        sa.Column("level_id", sa.String(128), nullable=True),
        sa.Column("discipline_a", sa.String(64), nullable=True),
        sa.Column("discipline_b", sa.String(64), nullable=True),
        sa.Column("layer_a", sa.String(128), nullable=True),
        sa.Column("layer_b", sa.String(128), nullable=True),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column("action_owner", sa.String(128), nullable=True),
        sa.Column("assigned_to", sa.String(128), nullable=True),
        sa.Column("centroid_x_mm", sa.Float(), nullable=True),
        sa.Column("centroid_y_mm", sa.Float(), nullable=True),
        sa.Column("bounds_minx_mm", sa.Float(), nullable=True),
        sa.Column("bounds_miny_mm", sa.Float(), nullable=True),
        sa.Column("bounds_maxx_mm", sa.Float(), nullable=True),
        sa.Column("bounds_maxy_mm", sa.Float(), nullable=True),
        sa.Column("area_mm2", sa.Float(), nullable=True),
        sa.Column("overlap_depth_mm", sa.Float(), nullable=True),
        sa.Column("member_count", sa.Integer(), nullable=True),
        sa.Column("alignment_dx_mm", sa.Float(), nullable=True),
        sa.Column("alignment_dy_mm", sa.Float(), nullable=True),
        sa.Column("raw_json", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "clash_code", name="uq_clash_job_code"),
    )
    op.create_index("ix_project_clash_items_job_id", "project_clash_items", ["job_id"])
    op.create_index("ix_project_clash_items_clash_code", "project_clash_items", ["clash_code"])

    op.create_table(
        "project_clash_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clash_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("project_clash_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("actor_role", sa.String(64), nullable=True),
        sa.Column("previous_status", sa.String(32), nullable=True),
        sa.Column("new_status", sa.String(32), nullable=True),
        sa.Column("decision", sa.String(64), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("related_run_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_clash_events_clash_item_id", "project_clash_events", ["clash_item_id"])


def downgrade() -> None:
    op.drop_index("ix_project_clash_events_clash_item_id", table_name="project_clash_events")
    op.drop_table("project_clash_events")
    op.drop_index("ix_project_clash_items_clash_code", table_name="project_clash_items")
    op.drop_index("ix_project_clash_items_job_id", table_name="project_clash_items")
    op.drop_table("project_clash_items")
    op.drop_column("project_clash_jobs", "output_dir")
