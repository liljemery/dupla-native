"""backfill workspace_id and enforce NOT NULL

Revision ID: 038_workspace_backfill
Revises: 037_workspace_fks
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "038_workspace_backfill"
down_revision = "037_workspace_fks"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "c0000001-0000-4000-8000-000000000001"


def upgrade() -> None:
    conn = op.get_bind()
    ws = DEFAULT_WORKSPACE_ID

    conn.execute(sa.text("UPDATE projects SET workspace_id = :ws WHERE workspace_id IS NULL"), {"ws": ws})
    conn.execute(
        sa.text("UPDATE workflow_templates SET workspace_id = :ws WHERE workspace_id IS NULL"),
        {"ws": ws},
    )
    conn.execute(
        sa.text("UPDATE chat_conversations SET workspace_id = :ws WHERE workspace_id IS NULL"),
        {"ws": ws},
    )
    conn.execute(sa.text("UPDATE task_lists SET workspace_id = :ws WHERE workspace_id IS NULL"), {"ws": ws})

    conn.execute(
        sa.text(
            "INSERT INTO workspace_members (workspace_id, user_id, created_at) "
            "SELECT :ws, u.id, NOW() FROM users u "
            "WHERE u.role != 'GERENCIA' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM workspace_members wm "
            "  WHERE wm.workspace_id = :ws AND wm.user_id = u.id"
            ")"
        ),
        {"ws": ws},
    )
    conn.execute(
        sa.text(
            "UPDATE users SET active_workspace_id = :ws "
            "WHERE role != 'GERENCIA' AND active_workspace_id IS NULL"
        ),
        {"ws": ws},
    )

    op.alter_column("projects", "workspace_id", nullable=False)
    op.alter_column("workflow_templates", "workspace_id", nullable=False)
    op.alter_column("chat_conversations", "workspace_id", nullable=False)
    op.alter_column("task_lists", "workspace_id", nullable=False)

    op.drop_index("ix_projects_project_code", table_name="projects")
    op.create_index(
        "uq_projects_workspace_project_code",
        "projects",
        ["workspace_id", "project_code"],
        unique=True,
        postgresql_where=sa.text("project_code IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_projects_workspace_project_code", table_name="projects")
    op.create_index("ix_projects_project_code", "projects", ["project_code"], unique=True)

    op.alter_column("task_lists", "workspace_id", nullable=True)
    op.alter_column("chat_conversations", "workspace_id", nullable=True)
    op.alter_column("workflow_templates", "workspace_id", nullable=True)
    op.alter_column("projects", "workspace_id", nullable=True)

    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM workspace_members"))
    conn.execute(
        sa.text("UPDATE users SET active_workspace_id = NULL WHERE active_workspace_id IS NOT NULL")
    )
