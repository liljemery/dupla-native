"""workspaces and workspace_members

Revision ID: 036_workspaces
Revises: 035_user_is_team_leader
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "036_workspaces"
down_revision = "035_user_is_team_leader"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "c0000001-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "workspace_members",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )
    op.add_column(
        "users",
        sa.Column("active_workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_active_workspace_id",
        "users",
        "workspaces",
        ["active_workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO workspaces (id, name, created_at, updated_at) "
            "VALUES (:id, NULL, NOW(), NOW())"
        ),
        {"id": DEFAULT_WORKSPACE_ID},
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_active_workspace_id", "users", type_="foreignkey")
    op.drop_column("users", "active_workspace_id")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
