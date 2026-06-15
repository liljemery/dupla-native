"""Tabla archivos base de precios por proyecto (importación / IA).

Revision ID: 029_project_price_database_files
Revises: 028_bootstrap_checklist_backfill
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "029_project_price_database_files"
down_revision: Union[str, None] = "028_bootstrap_checklist_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_price_database_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("original_name", sa.String(512), nullable=False),
        sa.Column("mime", sa.String(255), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("price_category", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_project_price_db_files_project_id",
        "project_price_database_files",
        ["project_id"],
    )
    op.create_index(
        "ix_project_price_db_files_project_category_active",
        "project_price_database_files",
        ["project_id", "price_category", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_price_db_files_project_category_active", table_name="project_price_database_files")
    op.drop_index("ix_project_price_db_files_project_id", table_name="project_price_database_files")
    op.drop_table("project_price_database_files")
