"""Workflow templates and projects.workflow_template_id / current_workflow_step_id."""

from __future__ import annotations

import uuid
from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "019_workflow_templates"
down_revision: str | None = "018_project_doc_alignment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_PHASE_TITLE: list[tuple[str, str]] = [
    ("BOOTSTRAPPING", "Criterios de arranque"),
    ("AWAITING_FILES", "Esperando archivos CAD"),
    ("ARCHITECTURE_REVIEW", "Revisión de arquitectura"),
    ("SPECIFICATIONS", "Pliego de condiciones"),
    ("BUDGETING_PIPELINE", "Presupuesto (cotización / volumetría / costo)"),
    ("MANAGEMENT_APPROVAL", "Aprobación de gerencia"),
    ("BUDGET_APPROVED", "Presupuesto aprobado por cliente"),
    ("COMPLETE", "Completo"),
]


def _legacy_template_id() -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "dupla:workflow_template:legacy")


def _legacy_step_id(stable_key: str) -> uuid.UUID:
    return uuid.uuid5(_legacy_template_id(), f"step:{stable_key}")


def upgrade() -> None:
    op.create_table(
        "workflow_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_templates_name", "workflow_templates", ["name"])

    op.create_table(
        "workflow_template_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("stable_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("behavior_kind", sa.String(length=64), nullable=False),
        sa.Column("blocked_by_step_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requires_approval_role", sa.String(length=32), nullable=True),
        sa.Column(
            "on_enter_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["blocked_by_step_id"],
            ["workflow_template_steps.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["workflow_template_id"], ["workflow_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_template_id", "stable_key", name="uq_workflow_template_step_stable"),
    )
    op.create_index(
        "ix_workflow_template_steps_template_sort",
        "workflow_template_steps",
        ["workflow_template_id", "sort_index"],
    )

    tid = _legacy_template_id()
    op.execute(
        sa.text(
            """
            INSERT INTO workflow_templates (id, name, description, created_by_user_id, archived_at, created_at, updated_at)
            VALUES (:id, :name, :description, NULL, NULL, (now() at time zone 'utc'), (now() at time zone 'utc'))
            """
        ).bindparams(
            id=tid,
            name="Dupla legado",
            description="Flujo lineal ISO histórico migrado automáticamente.",
        )
    )

    conn = op.get_bind()
    for idx, (stable_key, title) in enumerate(_LEGACY_PHASE_TITLE):
        sid = _legacy_step_id(stable_key)
        conn.execute(
            sa.text(
                """
                INSERT INTO workflow_template_steps (
                  id, workflow_template_id, sort_index, stable_key, title, behavior_kind,
                  blocked_by_step_id, requires_approval_role, on_enter_actions, created_at, updated_at
                ) VALUES (
                  :id, :tid, :sort_idx, :stable_key, :title, :behavior_kind,
                  NULL, NULL, '[]'::jsonb, now() at time zone 'utc', now() at time zone 'utc'
                )
                """
            ),
            {
                "id": sid,
                "tid": tid,
                "sort_idx": idx,
                "stable_key": stable_key,
                "title": title,
                "behavior_kind": stable_key,
            },
        )

    op.add_column(
        "projects",
        sa.Column("workflow_template_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("current_workflow_step_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.execute(
        sa.text("UPDATE projects SET workflow_template_id = :tid WHERE workflow_template_id IS NULL").bindparams(
            tid=tid
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE projects AS p
            SET current_workflow_step_id = s.id
            FROM workflow_template_steps AS s
            WHERE s.workflow_template_id = p.workflow_template_id
              AND s.stable_key = CASE
                WHEN p.workflow_phase = 'FILES_INGESTED' THEN 'AWAITING_FILES'
                ELSE p.workflow_phase
              END
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE projects AS p
            SET current_workflow_step_id = s.id
            FROM workflow_template_steps AS s
            WHERE p.current_workflow_step_id IS NULL
              AND s.workflow_template_id = p.workflow_template_id
              AND s.stable_key = 'BOOTSTRAPPING'
            """
        )
    )

    op.alter_column("projects", "workflow_template_id", nullable=False)
    op.alter_column("projects", "current_workflow_step_id", nullable=False)

    op.create_foreign_key(
        "fk_projects_workflow_template_id",
        "projects",
        "workflow_templates",
        ["workflow_template_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_projects_current_workflow_step_id",
        "projects",
        "workflow_template_steps",
        ["current_workflow_step_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_projects_workflow_template_id", "projects", ["workflow_template_id"])


def downgrade() -> None:
    op.drop_index("ix_projects_workflow_template_id", table_name="projects")
    op.drop_constraint("fk_projects_current_workflow_step_id", "projects", type_="foreignkey")
    op.drop_constraint("fk_projects_workflow_template_id", "projects", type_="foreignkey")
    op.drop_column("projects", "current_workflow_step_id")
    op.drop_column("projects", "workflow_template_id")
    op.drop_index("ix_workflow_template_steps_template_sort", table_name="workflow_template_steps")
    op.drop_table("workflow_template_steps")
    op.drop_index("ix_workflow_templates_name", table_name="workflow_templates")
    op.drop_table("workflow_templates")
