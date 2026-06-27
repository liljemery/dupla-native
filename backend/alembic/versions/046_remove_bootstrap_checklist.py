"""Eliminar checklist de arranque; proyectos inician en AWAITING_FILES.

Revision ID: 046_remove_bootstrap_checklist
Revises: 045_subcontract_currency_dop
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "046_remove_bootstrap_checklist"
down_revision: Union[str, None] = "045_subcontract_currency_dop"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _legacy_template_id() -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "dupla:workflow_template:legacy")


def _legacy_step_id(old_stable_key: str) -> uuid.UUID:
    return uuid.uuid5(_legacy_template_id(), f"step:{old_stable_key}")


def upgrade() -> None:
    bootstrap_step = _legacy_step_id("BOOTSTRAPPING")
    awaiting_step = _legacy_step_id("AWAITING_FILES")
    tid = _legacy_template_id()

    op.execute(
        sa.text("UPDATE projects SET workflow_phase = 'AWAITING_FILES' WHERE workflow_phase = 'BOOTSTRAPPING'")
    )
    op.execute(sa.text("UPDATE projects SET project_bootstrap_criteria = '[]'::jsonb"))
    op.execute(
        sa.text(
            f"UPDATE projects SET current_workflow_step_id = '{awaiting_step}'::uuid "
            f"WHERE current_workflow_step_id = '{bootstrap_step}'::uuid"
        )
    )

    op.execute(sa.text(f"DELETE FROM workflow_template_steps WHERE id = '{bootstrap_step}'::uuid"))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            f"SELECT id FROM workflow_template_steps WHERE workflow_template_id = '{tid}'::uuid ORDER BY sort_index"
        )
    ).fetchall()
    for idx, (step_id,) in enumerate(rows):
        conn.execute(
            sa.text(f"UPDATE workflow_template_steps SET sort_index = {idx} WHERE id = '{step_id}'::uuid")
        )

    op.alter_column("projects", "workflow_phase", server_default="AWAITING_FILES")


def downgrade() -> None:
    op.alter_column("projects", "workflow_phase", server_default="BOOTSTRAPPING")
