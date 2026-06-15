"""Restaurar behavior_kind de dominio en pasos de la plantilla legado.

La migración 021 puso todos los pasos en CUSTOM_AUTOMATION para stable_key legibles;
eso rompe transiciones por target_phase y la denormalización de workflow_phase en
upload_file / guards.

Revision ID must stay ≤32 chars (alembic_version.version_num).

Revision ID: 026_legacy_step_behavior
Revises: 025_architecture_revision_role
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "026_legacy_step_behavior"
down_revision: Union[str, None] = "025_architecture_revision_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_PHASE_KEYS: list[tuple[str, str]] = [
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
    tid = _legacy_template_id()
    conn = op.get_bind()
    for behavior_kind, _title in _LEGACY_PHASE_KEYS:
        sid = _legacy_step_id(behavior_kind)
        conn.execute(
            sa.text(
                """
                UPDATE workflow_template_steps
                SET behavior_kind = :bk
                WHERE id = :sid AND workflow_template_id = :tid
                """
            ),
            {"bk": behavior_kind, "sid": sid, "tid": tid},
        )

    conn.execute(
        sa.text(
            """
            UPDATE projects AS p
            SET workflow_phase = s.behavior_kind
            FROM workflow_template_steps AS s
            WHERE p.current_workflow_step_id = s.id
              AND s.workflow_template_id = :tid
            """
        ),
        {"tid": tid},
    )


def downgrade() -> None:
    tid = _legacy_template_id()
    conn = op.get_bind()
    custom = "CUSTOM_AUTOMATION"
    for behavior_kind, _title in _LEGACY_PHASE_KEYS:
        sid = _legacy_step_id(behavior_kind)
        conn.execute(
            sa.text(
                """
                UPDATE workflow_template_steps
                SET behavior_kind = :custom
                WHERE id = :sid AND workflow_template_id = :tid
                """
            ),
            {"custom": custom, "sid": sid, "tid": tid},
        )
