from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.workflow_phase import WorkflowPhase, normalize_workflow_phase
from app.models.architecture_revision import ArchitectureRevision
from app.models.user import UserRole

MANAGEMENT_APPROVAL_ENTERED_AT_KEY = "management_approval_entered_at"


def parse_management_approval_entered_at(meta: dict[str, object] | None) -> datetime | None:
    if not isinstance(meta, dict):
        return None
    raw = meta.get(MANAGEMENT_APPROVAL_ENTERED_AT_KEY)
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def stamp_management_approval_entered(meta: dict[str, object]) -> dict[str, object]:
    out = dict(meta)
    out[MANAGEMENT_APPROVAL_ENTERED_AT_KEY] = datetime.now(timezone.utc).isoformat()
    return out


def clear_management_approval_entered(meta: dict[str, object]) -> dict[str, object]:
    out = dict(meta)
    out.pop(MANAGEMENT_APPROVAL_ENTERED_AT_KEY, None)
    return out


def management_approval_entered_at_for_guard(
    meta: dict[str, object] | None,
    phase: WorkflowPhase,
) -> datetime | None:
    parsed = parse_management_approval_entered_at(meta)
    if parsed is not None:
        return parsed
    # ponytail: legacy projects in gerencia phase before this key existed — any GERENCIA revision counts
    if phase in (
        WorkflowPhase.MANAGEMENT_APPROVAL,
        WorkflowPhase.BUDGET_APPROVED,
        WorkflowPhase.COMPLETE,
    ):
        return datetime.min.replace(tzinfo=timezone.utc)
    return None


async def has_gerencia_revision_since(
    session: AsyncSession,
    project_id: UUID,
    since: datetime,
) -> bool:
    row = (
        await session.execute(
            select(ArchitectureRevision.id)
            .where(
                ArchitectureRevision.project_id == project_id,
                ArchitectureRevision.revision_role == UserRole.GERENCIA.value,
                ArchitectureRevision.created_at >= since,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def project_has_gerencia_review_for_current_phase(
    session: AsyncSession,
    project_id: UUID,
    meta: dict[str, object] | None,
    workflow_phase: str,
) -> bool:
    phase = normalize_workflow_phase(workflow_phase)
    since = management_approval_entered_at_for_guard(meta, phase)
    if since is None:
        return False
    return await has_gerencia_revision_since(session, project_id, since)


if __name__ == "__main__":
    assert parse_management_approval_entered_at({"management_approval_entered_at": "2026-01-01T12:00:00+00:00"})
    assert parse_management_approval_entered_at({}) is None
