from app.domain.budget_pipeline_meta import (
    budget_result_qualifies_for_volumetry,
    get_budget_pipeline,
    sync_volumetry_from_completed_job,
)

import pytest


def test_base_extraction_does_not_qualify_for_volumetry():
    result = {
        "rows": [],
        "output": {"mode": "base_extraction"},
        "extraction": {"mode": "base_extraction"},
    }
    assert budget_result_qualifies_for_volumetry(result) is False


def test_budget_with_rows_qualifies_for_volumetry():
    result = {
        "rows": [{"code": "01.01", "summary": "Muro", "quantity": 10}],
        "output": {"mode": "budget"},
    }
    assert budget_result_qualifies_for_volumetry(result) is True


def test_empty_budget_with_disciplines_does_not_qualify():
    result = {
        "rows": [],
        "output": {"disciplines": ["arquitectura"]},
    }
    assert budget_result_qualifies_for_volumetry(result) is False


def test_base_extraction_with_rows_still_does_not_qualify():
    result = {
        "rows": [{"code": "01.01"}],
        "output": {"mode": "base_extraction"},
    }
    assert budget_result_qualifies_for_volumetry(result) is False


@pytest.mark.asyncio
async def test_sync_volumetry_from_completed_job_integration(session):
    """DUP-005: job completed con presupuesto real marca volumetry_done en workflow_meta."""
    from sqlalchemy import select

    from app.domain.project_kind import ProjectKind
    from app.domain.workflow_phase import WorkflowPhase
    from app.models.project_budget_job import ProjectBudgetJob
    from app.models.user import User
    from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateStep
    from app.models.workspace import DEFAULT_WORKSPACE_UUID
    from app.repositories.project_repository import ProjectRepository

    master = (
        await session.execute(select(User).where(User.email == "master@dupla.demo"))
    ).scalar_one()
    tpl = (
        await session.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.workspace_id == DEFAULT_WORKSPACE_UUID)
        )
    ).scalar_one()
    step = (
        await session.execute(
            select(WorkflowTemplateStep)
            .where(WorkflowTemplateStep.workflow_template_id == tpl.id)
            .order_by(WorkflowTemplateStep.sort_index.asc())
            .limit(1)
        )
    ).scalar_one()

    repo = ProjectRepository(session)
    project = await repo.create_with_architecture(
        name="Sync volumetría integración",
        client_name=None,
        created_by=master.id,
        workspace_id=DEFAULT_WORKSPACE_UUID,
        project_kind=ProjectKind.CLIENT.value,
        workflow_phase=WorkflowPhase.BOOTSTRAPPING.value,
        workflow_template_id=tpl.id,
        current_workflow_step_id=step.id,
    )
    await session.flush()

    assert get_budget_pipeline(project.workflow_meta or {}).get("volumetry_done") is False

    job = ProjectBudgetJob(
        project_id=project.id,
        job_id="integration-test-job",
        status="completed",
        result={
            "rows": [{"code": "01.01", "summary": "Muro", "quantity": 10}],
            "output": {"mode": "budget"},
        },
    )
    session.add(job)
    await session.flush()

    await sync_volumetry_from_completed_job(session, job)
    await session.refresh(project)

    bp = get_budget_pipeline(project.workflow_meta or {})
    assert bp.get("volumetry_done") is True
    assert bp.get("volumetry_synced_at")
