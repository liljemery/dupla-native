from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.domain.ai_project_snapshot import (
    WORKFLOW_PHASE_ORDER,
    build_project_snapshot_markdown,
    phase_status,
    truncate_snapshot,
)
from app.domain.ai_project_snapshot_data import (
    BootstrapSummary,
    BudgetJobSummary,
    ClashSummary,
    FilesSummary,
    MemberSummary,
    PlanDeliverySummary,
    PliegoSummary,
    PriceDatabaseSummary,
    ProjectSnapshotData,
    RevisionSummary,
    compute_phase_transition_hints,
)
from app.domain.workflow_phase import WorkflowPhase
from app.models.architecture_revision import ArchitectureRevisionDecision


def _empty_data(**overrides) -> ProjectSnapshotData:
    base = ProjectSnapshotData(
        members=[],
        bootstrap=BootstrapSummary(0, 0, False, False),
        files=FilesSummary(0, 0),
        revision=None,
        pliego=PliegoSummary("sin datos", 0, 24, False, None),
        budget_pipeline={},
        subcontract_line_count=0,
        budget_job=None,
        price_database=PriceDatabaseSummary(0, None),
        clashes=ClashSummary(None, 0, 0, False),
        plan_delivery=PlanDeliverySummary(0, 0),
        technical_findings_count=0,
        pending_tasks=0,
    )
    for key, val in overrides.items():
        setattr(base, key, val)
    return base


def _project(phase: str = "BOOTSTRAPPING", **kwargs) -> MagicMock:
    p = MagicMock()
    p.name = kwargs.get("name", "Obra test")
    p.client_name = kwargs.get("client_name", "Cliente")
    p.project_kind = kwargs.get("project_kind", "CLIENT")
    p.workflow_phase = phase
    p.project_code = None
    p.location_text = None
    p.deadline = None
    p.estimated_area_sqm = None
    p.floor_levels_count = None
    p.responsible_external_name = None
    p.responsible_external_email = None
    p.current_workflow_step = None
    p.project_bootstrap_criteria = kwargs.get("project_bootstrap_criteria", [])
    p.specifications_document = kwargs.get("specifications_document", {})
    p.workflow_meta = kwargs.get("workflow_meta", {})
    return p


def test_phase_status_current_vs_past():
    assert phase_status(WorkflowPhase.BOOTSTRAPPING, WorkflowPhase.SPECIFICATIONS) == "completo"
    assert phase_status(WorkflowPhase.SPECIFICATIONS, WorkflowPhase.SPECIFICATIONS) == "en_curso"
    assert phase_status(WorkflowPhase.BUDGETING_PIPELINE, WorkflowPhase.SPECIFICATIONS) == "pendiente"


def test_phase_status_custom_automation():
    assert phase_status(WorkflowPhase.BOOTSTRAPPING, WorkflowPhase.CUSTOM_AUTOMATION) == "completo"


def test_workflow_phase_order_has_eight_linear_phases():
    assert len(WORKFLOW_PHASE_ORDER) == 8


def test_bootstrap_incomplete_blocker():
    project = _project("BOOTSTRAPPING")
    data = _empty_data(
        bootstrap=BootstrapSummary(required_done=1, required_total=3, all_required_ok=False, has_criteria=True),
    )
    hints = compute_phase_transition_hints(project, data)
    assert any("obligatorio" in h.lower() for h in hints)


def test_awaiting_files_no_files_blocker():
    project = _project("AWAITING_FILES")
    data = _empty_data(files=FilesSummary(0, 0))
    hints = compute_phase_transition_hints(project, data)
    assert any("archivo" in h.lower() for h in hints)


def test_specifications_ga_fo_blocker():
    project = _project("SPECIFICATIONS")
    data = _empty_data(
        pliego=PliegoSummary(
            mode="GA-FO-01",
            ga_fo_complete=5,
            ga_fo_total=24,
            approved=False,
            blocker_message="Completa el checklist GA-FO-01",
        ),
    )
    hints = compute_phase_transition_hints(project, data)
    assert any("GA-FO" in h for h in hints)


def test_budgeting_pipeline_partial_flags():
    project = _project("BUDGETING_PIPELINE")
    data = _empty_data(
        budget_pipeline={
            "subcontracts_done": True,
            "volumetry_done": False,
            "cost_analysis_done": False,
            "budget_marked_complete": False,
        },
    )
    hints = compute_phase_transition_hints(project, data)
    assert any("volumetría" in h.lower() for h in hints)


def test_complete_phase_hint():
    project = _project("COMPLETE")
    data = _empty_data()
    hints = compute_phase_transition_hints(project, data)
    assert any("completado" in h.lower() for h in hints)


def test_snapshot_includes_revision_and_budget_job():
    project = _project("ARCHITECTURE_REVIEW")
    data = _empty_data(
        revision=RevisionSummary(
            version=2,
            decision=ArchitectureRevisionDecision.APPROVED.value,
            decision_es="aprobada",
            created_at=datetime.now(timezone.utc),
        ),
        budget_job=BudgetJobSummary(
            status="completed",
            discipline="arquitectura",
            updated_at=datetime.now(timezone.utc),
            row_count=42,
            completed=True,
        ),
        files=FilesSummary(3, 1, {"arquitectura": 2}, ["plano.dwg"]),
    )
    md = build_project_snapshot_markdown(project, data, max_chars=8000)
    assert "versión 2" in md
    assert "aprobada" in md
    assert "Presupuesto maestro" in md
    assert "42" in md
    assert "plano.dwg" in md


def test_snapshot_respects_max_chars():
    project = _project("BOOTSTRAPPING")
    long_lines = [f"- Ítem {i}, obligatorio: pendiente" for i in range(200)]
    data = _empty_data(
        bootstrap=BootstrapSummary(
            required_done=0,
            required_total=200,
            all_required_ok=False,
            has_criteria=True,
            item_lines=long_lines,
        ),
    )
    md = build_project_snapshot_markdown(project, data, max_chars=1500)
    assert len(md) <= 1500
    assert "Qué falta para avanzar" in md


def test_truncate_snapshot_preserves_blockers():
    head = "x" * 5000
    tail = "### Qué falta para avanzar al siguiente paso\n- Falta algo."
    text = head + "\n\n" + tail
    out = truncate_snapshot(text, 600)
    assert "Qué falta para avanzar" in out
    assert "Falta algo" in out
    assert len(out) <= 600
