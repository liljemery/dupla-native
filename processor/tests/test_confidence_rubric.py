from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))

from core.confidence_rubric import score, score_vision_entity


def test_default_score_is_base_when_no_signals():
    result = score()
    assert 0.45 <= result.score <= 0.55
    assert result.requiere_revision is True  # base alone is below threshold


def test_ocr_confirmed_pushes_score_above_threshold():
    result = score(ocr_confirmed=True, dimensions_complete=True, labeled_entity=True)
    assert result.score > 0.65
    assert result.requiere_revision is False


def test_defaults_used_and_geom_only_force_review():
    result = score(defaults_used=True, geom_only=True)
    assert result.requiere_revision is True


def test_score_clamps_to_unit_interval():
    saturated = score(
        ocr_confirmed=True,
        labeled_entity=True,
        dimensions_complete=True,
    )
    assert saturated.score <= 1.0
    floored = score(
        geom_only=True,
        defaults_used=True,
        unit_ambiguous=True,
        assumption_count=10,
    )
    assert floored.score >= 0.0


def test_vision_entity_labeled_structural_with_section_scores_high():
    entity = {
        "id": "C1",
        "type": "column",
        "label": "C1",
        "unit": "m3",
        "section_width_m": 0.40,
        "section_height_m": 0.40,
        "length_m": 3.0,
    }
    result = score_vision_entity(entity)
    assert result.score > 0.65


def test_vision_entity_with_missing_detail_sheets_marks_defaults():
    entity = {
        "id": "C1",
        "type": "column",
        "section_width_m": 0.40,
        "section_height_m": 0.40,
        "length_m": 3.0,
        "missing_detail_sheets": True,
    }
    result = score_vision_entity(entity)
    assert any(label == "defaults_used" for label, _ in result.contributions)
