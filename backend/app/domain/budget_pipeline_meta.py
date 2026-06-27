from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.project import Project
from app.models.project_budget_job import ProjectBudgetJob


def budget_pipeline_defaults() -> dict[str, Any]:
    return {
        "subcontracts_done": False,
        "volumetry_done": False,
        "cost_analysis_done": False,
        "budget_marked_complete": False,
        "control_review_done": False,
        "management_review_done": False,
        "client_approved_version_label": None,
        "volumetry": {},
        "cost_analysis": {},
        "budget_versions": [],
    }


def get_budget_pipeline(meta: dict[str, Any]) -> dict[str, Any]:
    raw = meta.get("budget_pipeline")
    base = budget_pipeline_defaults()
    if not isinstance(raw, dict):
        return dict(base)
    merged = dict(base)
    merged.update(raw)
    return merged


def set_budget_pipeline(meta: dict[str, Any], bp: dict[str, Any]) -> None:
    meta["budget_pipeline"] = bp


def budget_result_qualifies_for_volumetry(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    rows = result.get("rows") or []
    if not rows:
        return False
    mode = (result.get("output") or {}).get("mode") or (result.get("extraction") or {}).get("mode")
    return mode != "base_extraction"


async def project_has_volumetry_qualifying_job(session: AsyncSession, project_id: UUID) -> bool:
    result = await session.execute(
        select(ProjectBudgetJob)
        .where(
            ProjectBudgetJob.project_id == project_id,
            ProjectBudgetJob.status == "completed",
        )
        .order_by(ProjectBudgetJob.created_at.desc())
    )
    for job in result.scalars():
        if budget_result_qualifies_for_volumetry(job.result if isinstance(job.result, dict) else None):
            return True
    return False


async def sync_volumetry_from_completed_job(session: AsyncSession, job: ProjectBudgetJob) -> None:
    if job.status != "completed":
        return
    if not budget_result_qualifies_for_volumetry(job.result if isinstance(job.result, dict) else None):
        return
    project = await session.get(Project, job.project_id)
    if project is None:
        return
    meta = dict(project.workflow_meta or {})
    bp = get_budget_pipeline(meta)
    if bp.get("volumetry_done"):
        return
    bp["volumetry_done"] = True
    bp["volumetry_synced_at"] = datetime.now(timezone.utc).isoformat()
    set_budget_pipeline(meta, bp)
    project.workflow_meta = meta
    flag_modified(project, "workflow_meta")
    await session.flush()
