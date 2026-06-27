from __future__ import annotations

from enum import StrEnum


class WorkflowStepBehaviorKind(StrEnum):
    """Tipo de comportamiento de un paso de plantilla (dominio + automatización libre)."""

    AWAITING_FILES = "AWAITING_FILES"
    ARCHITECTURE_REVIEW = "ARCHITECTURE_REVIEW"
    SPECIFICATIONS = "SPECIFICATIONS"
    BUDGETING_PIPELINE = "BUDGETING_PIPELINE"
    MANAGEMENT_APPROVAL = "MANAGEMENT_APPROVAL"
    BUDGET_APPROVED = "BUDGET_APPROVED"
    COMPLETE = "COMPLETE"
    CUSTOM_AUTOMATION = "CUSTOM_AUTOMATION"


VALID_WORKFLOW_STEP_BEHAVIORS: frozenset[str] = frozenset([e.value for e in WorkflowStepBehaviorKind])


def is_domain_behavior(kind: str) -> bool:
    return kind != WorkflowStepBehaviorKind.CUSTOM_AUTOMATION.value

