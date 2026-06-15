from __future__ import annotations

from enum import StrEnum


class WorkflowPhase(StrEnum):
    BOOTSTRAPPING = "BOOTSTRAPPING"
    AWAITING_FILES = "AWAITING_FILES"
    ARCHITECTURE_REVIEW = "ARCHITECTURE_REVIEW"
    SPECIFICATIONS = "SPECIFICATIONS"
    BUDGETING_PIPELINE = "BUDGETING_PIPELINE"
    MANAGEMENT_APPROVAL = "MANAGEMENT_APPROVAL"
    BUDGET_APPROVED = "BUDGET_APPROVED"
    COMPLETE = "COMPLETE"
    # Paso de plantilla solo automatización (plantillas configurables).
    CUSTOM_AUTOMATION = "CUSTOM_AUTOMATION"


# Linear primary path (valid single-step transitions)
LINEAR_NEXT: dict[WorkflowPhase, WorkflowPhase] = {
    WorkflowPhase.BOOTSTRAPPING: WorkflowPhase.AWAITING_FILES,
    WorkflowPhase.AWAITING_FILES: WorkflowPhase.ARCHITECTURE_REVIEW,
    WorkflowPhase.ARCHITECTURE_REVIEW: WorkflowPhase.SPECIFICATIONS,
    WorkflowPhase.SPECIFICATIONS: WorkflowPhase.BUDGETING_PIPELINE,
    WorkflowPhase.BUDGETING_PIPELINE: WorkflowPhase.MANAGEMENT_APPROVAL,
    WorkflowPhase.MANAGEMENT_APPROVAL: WorkflowPhase.BUDGET_APPROVED,
    WorkflowPhase.BUDGET_APPROVED: WorkflowPhase.COMPLETE,
}

# Paso inverso (una fase atrás); no incluye BOOTSTRAPPING como destino implícito en el mapa de "desde"
LINEAR_PREV: dict[WorkflowPhase, WorkflowPhase] = {v: k for k, v in LINEAR_NEXT.items()}

PHASES_AFTER_BUDGET: frozenset[WorkflowPhase] = frozenset(
    {
        WorkflowPhase.MANAGEMENT_APPROVAL,
        WorkflowPhase.BUDGET_APPROVED,
        WorkflowPhase.COMPLETE,
    }
)


def upload_counts_for_budget(phase: WorkflowPhase) -> bool:
    """Archivos subidos tras la fase de presupuesto no entran al pipeline de presupuesto."""
    return phase not in PHASES_AFTER_BUDGET
