"""Plantilla por defecto: nombre estándar, pasos con stable_key desde título y CUSTOM_AUTOMATION."""

from __future__ import annotations

import re
import uuid
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021_dupla_std_template"
down_revision: str | None = "020_workflow_template_icon_key"
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


def _legacy_step_id(old_stable_key: str) -> uuid.UUID:
    return uuid.uuid5(_legacy_template_id(), f"step:{old_stable_key}")


def _title_to_stable_key(title: str, idx: int) -> str:
    t = title.strip()
    if not t:
        return f"paso_{idx + 1}"
    return re.sub(r"\s+", "_", t)


def upgrade() -> None:
    tid = _legacy_template_id()
    op.execute(
        sa.text(
            """
            UPDATE workflow_templates
            SET name = :name,
                description = :description
            WHERE id = :tid
            """
        ).bindparams(
            name="Flujo estándar Dupla",
            description="Plantilla por defecto con los pasos del proceso operativo.",
            tid=tid,
        )
    )

    conn = op.get_bind()
    used: set[str] = set()
    for idx, (old_sk, title) in enumerate(_LEGACY_PHASE_TITLE):
        base = _title_to_stable_key(title, idx)
        candidate = base
        n = 2
        while candidate in used:
            candidate = f"{base}_{n}"
            n += 1
        used.add(candidate)
        sid = _legacy_step_id(old_sk)
        conn.execute(
            sa.text(
                """
                UPDATE workflow_template_steps
                SET stable_key = :nsk,
                    behavior_kind = 'CUSTOM_AUTOMATION',
                    title = :title
                WHERE id = :sid AND workflow_template_id = :tid
                """
            ),
            {"nsk": candidate, "title": title.strip(), "sid": sid, "tid": tid},
        )


def downgrade() -> None:
    tid = _legacy_template_id()
    op.execute(
        sa.text(
            """
            UPDATE workflow_templates
            SET name = :name,
                description = :description
            WHERE id = :tid
            """
        ).bindparams(
            name="Dupla legado",
            description="Flujo lineal ISO histórico migrado automáticamente.",
            tid=tid,
        )
    )

    conn = op.get_bind()
    for old_sk, title in _LEGACY_PHASE_TITLE:
        sid = _legacy_step_id(old_sk)
        conn.execute(
            sa.text(
                """
                UPDATE workflow_template_steps
                SET stable_key = :osk,
                    behavior_kind = :osk,
                    title = :title
                WHERE id = :sid AND workflow_template_id = :tid
                """
            ),
            {"osk": old_sk, "title": title, "sid": sid, "tid": tid},
        )
