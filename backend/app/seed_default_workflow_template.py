"""Asegura la plantilla legada post-021 si la tabla quedó vacía (p. ej. compose sin migraciones aplicadas)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateStep
from app.models.workspace import DEFAULT_WORKSPACE_UUID

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


async def ensure_default_workflow_template_if_missing(session: AsyncSession) -> bool:
    """
    Si no hay filas en workflow_templates, inserta la plantilla estándar y pasos
    (mismos UUID y stable_key que alembic 019 + 021).
    """
    n = await session.scalar(select(func.count()).select_from(WorkflowTemplate))
    if n is not None and n > 0:
        return False

    now = datetime.now(timezone.utc)
    tid = _legacy_template_id()
    session.add(
        WorkflowTemplate(
            id=tid,
            workspace_id=DEFAULT_WORKSPACE_UUID,
            name="Flujo estándar Dupla",
            description="Plantilla por defecto con los pasos del proceso operativo.",
            icon_key="GitBranch",
            created_by_user_id=None,
            archived_at=None,
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()

    used: set[str] = set()
    for idx, (old_sk, title) in enumerate(_LEGACY_PHASE_TITLE):
        base = _title_to_stable_key(title, idx)
        candidate = base
        n_dup = 2
        while candidate in used:
            candidate = f"{base}_{n_dup}"
            n_dup += 1
        used.add(candidate)
        sid = _legacy_step_id(old_sk)
        session.add(
            WorkflowTemplateStep(
                id=sid,
                workflow_template_id=tid,
                sort_index=idx,
                stable_key=candidate,
                title=title.strip(),
                icon_key="GitBranch",
                behavior_kind="CUSTOM_AUTOMATION",
                blocked_by_step_id=None,
                requires_approval_role=None,
                on_enter_actions=[],
                created_at=now,
                updated_at=now,
            )
        )

    return True
