"""Denormalización `projects.workflow_phase` alineada al paso en plantilla lineal.

La fase ISO (BOOTSTRAPPING…COMPLETE) se deriva solo del índice del paso en la
plantilla ordenada (secuencia estándar Dupla de 8 pasos), no de `behavior_kind`.
"""

from __future__ import annotations

from app.domain.workflow_phase import WorkflowPhase

CANONICAL_LINEAR_PHASE_VALUES: tuple[str, ...] = (
    WorkflowPhase.BOOTSTRAPPING.value,
    WorkflowPhase.AWAITING_FILES.value,
    WorkflowPhase.ARCHITECTURE_REVIEW.value,
    WorkflowPhase.SPECIFICATIONS.value,
    WorkflowPhase.BUDGETING_PIPELINE.value,
    WorkflowPhase.MANAGEMENT_APPROVAL.value,
    WorkflowPhase.BUDGET_APPROVED.value,
    WorkflowPhase.COMPLETE.value,
)


def workflow_phase_from_template_step_index(step_index: int) -> str:
    """Índice 0-based del paso en la plantilla ordenada → fase ISO estándar."""
    if step_index < 0:
        return WorkflowPhase.BOOTSTRAPPING.value
    if step_index >= len(CANONICAL_LINEAR_PHASE_VALUES):
        return WorkflowPhase.COMPLETE.value
    return CANONICAL_LINEAR_PHASE_VALUES[step_index]


def effective_workflow_phase_for_step(step_index: int) -> str:
    """Fase persistida en `projects.workflow_phase` (tablero/API), por índice de paso."""
    return workflow_phase_from_template_step_index(step_index)
