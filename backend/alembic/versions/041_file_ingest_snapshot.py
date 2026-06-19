"""file_ingest_snapshot JSONB on project_files

Revision ID: 041_file_ingest_snapshot
Revises: 040_aps_viewer_calibration
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "041_file_ingest_snapshot"
down_revision = "040_aps_viewer_calibration"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    cols = _columns("project_files")
    if "file_ingest_snapshot" not in cols:
        op.add_column("project_files", sa.Column("file_ingest_snapshot", JSONB, nullable=True))


def downgrade() -> None:
    cols = _columns("project_files")
    if "file_ingest_snapshot" in cols:
        op.drop_column("project_files", "file_ingest_snapshot")
