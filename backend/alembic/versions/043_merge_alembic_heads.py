"""Revision: merge alembic heads

Revises: 035_clash_job_export_revisions, 041_file_ingest_snapshot, 042_rbac_permissions
"""
from __future__ import annotations

revision = "043_merge_alembic_heads"
down_revision = (
    "035_clash_job_export_revisions",
    "041_file_ingest_snapshot",
    "042_rbac_permissions",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
