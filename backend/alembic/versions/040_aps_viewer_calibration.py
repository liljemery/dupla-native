"""APS viewer URN persistence and coordinate calibration

Revision ID: 040_aps_viewer_calibration
Revises: 039_file_counts_for_budget
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "040_aps_viewer_calibration"
down_revision = "039_file_counts_for_budget"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    cols = _columns("project_files")
    additions = [
        ("aps_bucket_key", sa.Column("aps_bucket_key", sa.String(length=128), nullable=True)),
        ("aps_object_key", sa.Column("aps_object_key", sa.String(length=1024), nullable=True)),
        ("aps_object_id", sa.Column("aps_object_id", sa.String(length=1200), nullable=True)),
        ("aps_urn", sa.Column("aps_urn", sa.Text(), nullable=True)),
        ("aps_derivative_status", sa.Column("aps_derivative_status", sa.String(length=64), nullable=True)),
        ("aps_viewable_guid", sa.Column("aps_viewable_guid", sa.String(length=255), nullable=True)),
        ("aps_last_translated_at", sa.Column("aps_last_translated_at", sa.DateTime(timezone=True), nullable=True)),
        ("aps_manifest_json", sa.Column("aps_manifest_json", JSONB, nullable=True)),
    ]
    for name, column in additions:
        if name not in cols:
            op.add_column("project_files", column)

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "project_viewer_coordinate_settings" not in inspector.get_table_names():
        op.create_table(
            "project_viewer_coordinate_settings",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "project_id",
                UUID(as_uuid=True),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("coordinate_space", sa.String(length=16), nullable=False, server_default="world"),
            sa.Column("scale", sa.Float(), nullable=False, server_default="1.0"),
            sa.Column("offset_x", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("offset_y", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("offset_z", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("invert_y", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("rotation_degrees", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("unit_factor", sa.Float(), nullable=False, server_default="1.0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.UniqueConstraint("project_id", name="uq_project_viewer_coordinate_settings_project_id"),
        )
        op.create_index(
            "ix_project_viewer_coordinate_settings_project_id",
            "project_viewer_coordinate_settings",
            ["project_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "project_viewer_coordinate_settings" in inspector.get_table_names():
        op.drop_index(
            "ix_project_viewer_coordinate_settings_project_id",
            table_name="project_viewer_coordinate_settings",
        )
        op.drop_table("project_viewer_coordinate_settings")

    cols = _columns("project_files")
    for name in [
        "aps_manifest_json",
        "aps_last_translated_at",
        "aps_viewable_guid",
        "aps_derivative_status",
        "aps_urn",
        "aps_object_id",
        "aps_object_key",
        "aps_bucket_key",
    ]:
        if name in cols:
            op.drop_column("project_files", name)
