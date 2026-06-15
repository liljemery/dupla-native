"""project file folders and file metadata

Revision ID: 015_project_file_folders
Revises: 014_project_kind
"""

from __future__ import annotations

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "015_project_file_folders"
down_revision: Optional[str] = "014_project_kind"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.create_table(
        "project_file_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_id"], ["project_file_folders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_file_folders_project_id", "project_file_folders", ["project_id"])
    op.create_index("ix_project_file_folders_parent_id", "project_file_folders", ["parent_id"])

    op.execute(
        """
        CREATE UNIQUE INDEX uq_project_file_folders_root_name
        ON project_file_folders (project_id, name)
        WHERE parent_id IS NULL;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_project_file_folders_nested_name
        ON project_file_folders (project_id, parent_id, name)
        WHERE parent_id IS NOT NULL;
        """
    )

    op.add_column(
        "project_files",
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("project_files", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("project_files", sa.Column("discipline", sa.String(length=32), nullable=True))
    op.add_column(
        "project_files",
        sa.Column("ingest_status", sa.String(length=20), nullable=False, server_default="PUBLISHED"),
    )
    op.alter_column("project_files", "ingest_status", server_default=None)
    op.create_foreign_key(
        "fk_project_files_folder_id",
        "project_files",
        "project_file_folders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_project_files_folder_id", "project_files", ["folder_id"])

    op.execute(
        "UPDATE project_files SET ingest_status = 'PUBLISHED' WHERE ingest_status IS NULL OR ingest_status = ''"
    )


def downgrade() -> None:
    op.drop_index("ix_project_files_folder_id", table_name="project_files")
    op.drop_constraint("fk_project_files_folder_id", "project_files", type_="foreignkey")
    op.drop_column("project_files", "ingest_status")
    op.drop_column("project_files", "discipline")
    op.drop_column("project_files", "description")
    op.drop_column("project_files", "folder_id")

    op.execute("DROP INDEX IF EXISTS uq_project_file_folders_nested_name")
    op.execute("DROP INDEX IF EXISTS uq_project_file_folders_root_name")
    op.drop_index("ix_project_file_folders_parent_id", table_name="project_file_folders")
    op.drop_index("ix_project_file_folders_project_id", table_name="project_file_folders")
    op.drop_table("project_file_folders")
