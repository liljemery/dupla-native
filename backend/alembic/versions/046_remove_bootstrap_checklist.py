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
    bootstrap_step = str(_legacy_step_id("BOOTSTRAPPING"))
    awaiting_step = str(_legacy_step_id("AWAITING_FILES"))
    tid = str(_legacy_template_id())

    op.execute(
        sa.text("UPDATE projects SET workflow_phase = 'AWAITING_FILES' WHERE workflow_phase = 'BOOTSTRAPPING'")
    )
    op.execute(sa.text("UPDATE projects SET project_bootstrap_criteria = '[]'::jsonb"))
    op.execute(
        sa.text(
            "UPDATE projects SET current_workflow_step_id = :awaiting "
            "WHERE current_workflow_step_id = :bootstrap"
        ).bindparams(awaiting=awaiting_step, bootstrap=bootstrap_step)
    )

    op.execute(sa.text("DELETE FROM workflow_template_steps WHERE id = :sid").bindparams(sid=bootstrap_step))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id FROM workflow_template_steps WHERE workflow_template_id = :tid ORDER BY sort_index"
        ).bindparams(tid=tid)
    ).fetchall()
    for idx, (step_id,) in enumerate(rows):
        conn.execute(
            sa.text("UPDATE workflow_template_steps SET sort_index = :idx WHERE id = :sid").bindparams(
                idx=idx, sid=str(step_id)
            )
        )

    op.alter_column("projects", "workflow_phase", server_default="AWAITING_FILES")


def downgrade() -> None:
    op.alter_column("projects", "workflow_phase", server_default="BOOTSTRAPPING")
