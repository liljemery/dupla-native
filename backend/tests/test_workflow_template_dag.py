import pytest
from fastapi import HTTPException

from app.schemas.workflow_template import WorkflowTemplateStepInput
from app.services.workflow_template_service import _detect_cycle_stable_keys


def test_cycle_detected() -> None:
    with pytest.raises(HTTPException) as e:
        _detect_cycle_stable_keys(
            [
                WorkflowTemplateStepInput(
                    stable_key="a",
                    title="A",
                    behavior_kind="BOOTSTRAPPING",
                    blocked_by_stable_key="b",
                ),
                WorkflowTemplateStepInput(
                    stable_key="b",
                    title="B",
                    behavior_kind="BOOTSTRAPPING",
                    blocked_by_stable_key="a",
                ),
            ]
        )
    assert e.value.status_code == 422


def test_linear_ok() -> None:
    _detect_cycle_stable_keys(
        [
            WorkflowTemplateStepInput(
                stable_key="a",
                title="A",
                behavior_kind="BOOTSTRAPPING",
                blocked_by_stable_key=None,
            ),
            WorkflowTemplateStepInput(
                stable_key="b",
                title="B",
                behavior_kind="AWAITING_FILES",
                blocked_by_stable_key="a",
            ),
        ]
    )
