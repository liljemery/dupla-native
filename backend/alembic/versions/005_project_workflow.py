"""project workflow, files, revisions, subcontracts, notifications, task project link

Revision ID: 005_project_workflow
Revises: 004_chat_conversations
"""

import json
from collections.abc import Sequence
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_project_workflow"
down_revision: Optional[str] = "004_chat_conversations"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.execute("ALTER TYPE chat_conversation_kind ADD VALUE 'PROJECT'")

    op.add_column(
        "projects",
        sa.Column("workflow_phase", sa.String(length=64), nullable=False, server_default="BOOTSTRAPPING"),
    )
    op.add_column(
        "projects",
        sa.Column("workflow_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.add_column(
        "projects",
        sa.Column(
            "project_bootstrap_criteria",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "specifications_document",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.alter_column("projects", "workflow_phase", server_default=None)
    op.alter_column("projects", "workflow_meta", server_default=None)
    op.alter_column("projects", "project_bootstrap_criteria", server_default=None)
    op.alter_column("projects", "specifications_document", server_default=None)

    op.create_table(
        "project_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_events_project_id", "project_events", ["project_id"])
    op.create_index("ix_project_events_created_at", "project_events", ["created_at"])

    op.create_table(
        "project_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=False),
        sa.Column("mime", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_files_project_id", "project_files", ["project_id"])

    revision_decision = postgresql.ENUM(
        "APPROVED",
        "REJECTED",
        "PARTIAL",
        name="architecture_revision_decision",
        create_type=True,
    )
    revision_decision.create(op.get_bind(), checkfirst=True)
    decision_col = postgresql.ENUM(
        "APPROVED",
        "REJECTED",
        "PARTIAL",
        name="architecture_revision_decision",
        create_type=False,
    )

    op.create_table(
        "architecture_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("decision", decision_col, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("checked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["checked_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version", name="uq_architecture_revision_project_version"),
    )
    op.create_index("ix_architecture_revisions_project_id", "architecture_revisions", ["project_id"])

    op.create_table(
        "subcontract_quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subcontract_quotes_project_id", "subcontract_quotes", ["project_id"])

    op.create_table(
        "subcontract_quote_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_label", sa.String(length=512), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=True),
        sa.Column("price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="MXN"),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["quote_id"], ["subcontract_quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subcontract_quote_lines_quote_id", "subcontract_quote_lines", ["quote_id"])

    op.create_table(
        "user_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_notifications_user_id", "user_notifications", ["user_id"])
    op.create_index("ix_user_notifications_user_unread", "user_notifications", ["user_id", "read_at"])

    op.add_column(
        "task_cards",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_task_cards_project_id",
        "task_cards",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_task_cards_project_id", "task_cards", ["project_id"])

    op.add_column(
        "chat_conversations",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_conversations_project_id",
        "chat_conversations",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_chat_conversations_project_id", "chat_conversations", ["project_id"])
    op.create_unique_constraint("uq_chat_conversations_project_id", "chat_conversations", ["project_id"])

    from app.domain.bootstrap_defaults import default_bootstrap_criteria

    crit_json = json.dumps(default_bootstrap_criteria())
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE projects SET project_bootstrap_criteria = CAST(:j AS jsonb) "
            "WHERE jsonb_array_length(COALESCE(project_bootstrap_criteria, '[]'::jsonb)) = 0"
        ),
        {"j": crit_json},
    )


def downgrade() -> None:
    op.drop_constraint("uq_chat_conversations_project_id", "chat_conversations", type_="unique")
    op.drop_index("ix_chat_conversations_project_id", table_name="chat_conversations")
    op.drop_constraint("fk_chat_conversations_project_id", "chat_conversations", type_="foreignkey")
    op.drop_column("chat_conversations", "project_id")

    op.drop_index("ix_task_cards_project_id", table_name="task_cards")
    op.drop_constraint("fk_task_cards_project_id", "task_cards", type_="foreignkey")
    op.drop_column("task_cards", "project_id")

    op.drop_index("ix_user_notifications_user_unread", table_name="user_notifications")
    op.drop_index("ix_user_notifications_user_id", table_name="user_notifications")
    op.drop_table("user_notifications")

    op.drop_index("ix_subcontract_quote_lines_quote_id", table_name="subcontract_quote_lines")
    op.drop_table("subcontract_quote_lines")

    op.drop_index("ix_subcontract_quotes_project_id", table_name="subcontract_quotes")
    op.drop_table("subcontract_quotes")

    op.drop_index("ix_architecture_revisions_project_id", table_name="architecture_revisions")
    op.drop_table("architecture_revisions")

    arch_enum = postgresql.ENUM(
        "APPROVED",
        "REJECTED",
        "PARTIAL",
        name="architecture_revision_decision",
        create_type=False,
    )
    arch_enum.drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_project_files_project_id", table_name="project_files")
    op.drop_table("project_files")

    op.drop_index("ix_project_events_created_at", table_name="project_events")
    op.drop_index("ix_project_events_project_id", table_name="project_events")
    op.drop_table("project_events")

    op.drop_column("projects", "specifications_document")
    op.drop_column("projects", "project_bootstrap_criteria")
    op.drop_column("projects", "workflow_meta")
    op.drop_column("projects", "workflow_phase")

    # Cannot remove enum value PROJECT from chat_conversation_kind in PostgreSQL easily; leave type extended.
