"""Semantic quality: missing space must not zero-out budget."""

from core.quality_engine import evaluate_semantic_quality
from core.semantic_models import SemanticBuilding, SemanticElement


def test_missing_space_is_warning_not_blocked() -> None:
    building = SemanticBuilding(
        project_id="p1",
        project_name="Test",
        discipline="arquitectura",
        elements=[
            SemanticElement(
                element_id="e1",
                element_type="wall",
                discipline="arquitectura",
                level_id="level_01",
                space_id=None,
                confidence_score=0.45,
            )
        ],
    )
    report = evaluate_semantic_quality(building)
    assert report.blocked_count == 0
    assert report.warning_count == 1


def test_missing_level_stays_blocked() -> None:
    building = SemanticBuilding(
        project_id="p1",
        project_name="Test",
        discipline="arquitectura",
        elements=[
            SemanticElement(
                element_id="e2",
                element_type="wall",
                discipline="arquitectura",
                level_id=None,
                space_id=None,
                confidence_score=0.9,
            )
        ],
    )
    report = evaluate_semantic_quality(building)
    assert report.blocked_count == 1
