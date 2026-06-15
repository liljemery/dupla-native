"""Rellenar checklist de arranque vacío en proyectos que siguen en BOOTSTRAPPING.

Revision ID: 028_bootstrap_checklist_backfill
Revises: 027_fix_custom_phase
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028_bootstrap_checklist_backfill"
down_revision: Union[str, None] = "027_fix_custom_phase"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from app.domain.bootstrap_defaults import default_bootstrap_criteria

    crit_json = json.dumps(default_bootstrap_criteria())
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE projects SET project_bootstrap_criteria = CAST(:j AS jsonb) "
            "WHERE workflow_phase = 'BOOTSTRAPPING' "
            "AND (project_bootstrap_criteria IS NULL "
            "OR jsonb_array_length(COALESCE(project_bootstrap_criteria, '[]'::jsonb)) = 0)"
        ),
        {"j": crit_json},
    )


def downgrade() -> None:
    pass
