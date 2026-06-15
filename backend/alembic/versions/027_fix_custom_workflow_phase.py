"""Corregir projects.workflow_phase CUSTOM_AUTOMATION según sort_index del paso.

Revision ID: 027_fix_custom_phase
Revises: 026_legacy_step_behavior
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "027_fix_custom_phase"
down_revision: Union[str, None] = "026_legacy_step_behavior"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PHASES: tuple[str, ...] = (
    "BOOTSTRAPPING",
    "AWAITING_FILES",
    "ARCHITECTURE_REVIEW",
    "SPECIFICATIONS",
    "BUDGETING_PIPELINE",
    "MANAGEMENT_APPROVAL",
    "BUDGET_APPROVED",
    "COMPLETE",
)


def upgrade() -> None:
    conn = op.get_bind()
    for idx, ph in enumerate(_PHASES):
        conn.execute(
            sa.text(
                """
                UPDATE projects AS p
                SET workflow_phase = :ph
                FROM workflow_template_steps AS s
                WHERE p.current_workflow_step_id = s.id
                  AND p.workflow_phase IN ('CUSTOM_AUTOMATION', 'custom_automation')
                  AND s.sort_index = :idx
                """
            ),
            {"ph": ph, "idx": idx},
        )
    conn.execute(
        sa.text(
            """
            UPDATE projects AS p
            SET workflow_phase = 'COMPLETE'
            FROM workflow_template_steps AS s
            WHERE p.current_workflow_step_id = s.id
              AND p.workflow_phase IN ('CUSTOM_AUTOMATION', 'custom_automation')
              AND s.sort_index >= :min_idx
            """
        ),
        {"min_idx": len(_PHASES)},
    )


def downgrade() -> None:
    pass
