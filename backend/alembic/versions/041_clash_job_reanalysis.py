"""Add reanalysis fields to project_clash_jobs and project_control_points table

Revision ID: 041_clash_job_reanalysis
Revises: 041_file_ingest_snapshot
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "041_clash_job_reanalysis"
down_revision = "041_file_ingest_snapshot"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table_name)}


def _tables() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def _ensure_clash_workflow_schema() -> None:
    """Idempotent: DBs that took the old main branch skipped 033–035 clash workflow."""
    job_cols = _columns("project_clash_jobs")
    if "output_dir" not in job_cols:
        op.add_column("project_clash_jobs", sa.Column("output_dir", sa.Text(), nullable=True))

    if "project_clash_items" not in _tables():
        op.create_table(
            "project_clash_items",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "job_id",
                UUID(as_uuid=True),
                sa.ForeignKey("project_clash_jobs.id", ondelete="CASCADE"),
                nullable=False,
            ),
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

    item_indexes = _index_names("project_clash_items")
    if "ix_project_clash_items_job_id" not in item_indexes:
        op.create_index("ix_project_clash_items_job_id", "project_clash_items", ["job_id"])
    if "ix_project_clash_items_clash_code" not in item_indexes:
        op.create_index("ix_project_clash_items_clash_code", "project_clash_items", ["clash_code"])

    if "project_clash_events" not in _tables():
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

    event_indexes = _index_names("project_clash_events")
    if "ix_project_clash_events_clash_item_id" not in event_indexes:
        op.create_index(
            "ix_project_clash_events_clash_item_id",
            "project_clash_events",
            ["clash_item_id"],
        )

    if "project_clash_corrections" not in _tables():
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

    corr_indexes = _index_names("project_clash_corrections")
    if "ix_project_clash_corrections_clash_item_id" not in corr_indexes:
        op.create_index(
            "ix_project_clash_corrections_clash_item_id",
            "project_clash_corrections",
            ["clash_item_id"],
        )
    if "ix_project_clash_corrections_job_id" not in corr_indexes:
        op.create_index(
            "ix_project_clash_corrections_job_id",
            "project_clash_corrections",
            ["job_id"],
        )

    event_cols = _columns("project_clash_events")
    if "correction_id" not in event_cols:
        op.add_column(
            "project_clash_events",
            sa.Column("correction_id", UUID(as_uuid=True), nullable=True),
        )

    job_cols = _columns("project_clash_jobs")
    if "export_revisions" not in job_cols:
        op.add_column(
            "project_clash_jobs",
            sa.Column("export_revisions", JSONB(), nullable=False, server_default="{}"),
        )


def upgrade() -> None:
    _ensure_clash_workflow_schema()

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
