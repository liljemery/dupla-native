"""add workspace_id FK columns (nullable)

Revision ID: 037_workspace_fks
Revises: 036_workspaces
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "037_workspace_fks"
down_revision = "036_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_workspace_id",
        "projects",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "workflow_templates",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_workflow_templates_workspace_id",
        "workflow_templates",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "chat_conversations",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_conversations_workspace_id",
        "chat_conversations",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "task_lists",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_task_lists_workspace_id",
        "task_lists",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_task_lists_workspace_id", "task_lists", type_="foreignkey")
    op.drop_column("task_lists", "workspace_id")
    op.drop_constraint("fk_chat_conversations_workspace_id", "chat_conversations", type_="foreignkey")
    op.drop_column("chat_conversations", "workspace_id")
    op.drop_constraint("fk_workflow_templates_workspace_id", "workflow_templates", type_="foreignkey")
    op.drop_column("workflow_templates", "workspace_id")
    op.drop_constraint("fk_projects_workspace_id", "projects", type_="foreignkey")
    op.drop_column("projects", "workspace_id")
