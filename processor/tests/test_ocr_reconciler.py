from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))

from core.ocr_reconciler import (
    apply_to_confidence,
    needs_review_at,
    reconcile,
)


def test_both_missing_marks_revision_and_negative_delta():
    result = reconcile(geometric_value=None, ocr_value=None, label="length_m")
    assert result.value is None
    assert result.source == "missing"
    assert result.requiere_revision is True
    assert result.confidence_delta < 0


def test_geometric_only_keeps_geom_but_flags_review():
    result = reconcile(geometric_value=12.5, ocr_value=None, label="length_m")
    assert result.value == 12.5
    assert result.source == "geometric_only"
    assert result.requiere_revision is True
    assert result.confidence_delta == -0.20


def test_ocr_only_keeps_ocr_but_flags_review():
    result = reconcile(geometric_value=None, ocr_value=12.5, label="length_m")
    assert result.value == 12.5
    assert result.source == "ocr_only"
    assert result.requiere_revision is True
    assert result.confidence_delta == -0.10


def test_ocr_agrees_within_tolerance_returns_ocr_with_bonus():
    result = reconcile(geometric_value=10.00, ocr_value=10.02, label="thickness_m")
    assert result.value == 10.02
    assert result.source == "ocr_confirmed"
    assert result.requiere_revision is False
    assert result.confidence_delta > 0


def test_ocr_overrides_geometric_when_disagrees_documents_override():
    result = reconcile(
        geometric_value=920.60,
        ocr_value=842.40,
        label="length_m",
        tolerance_pct=0.03,
    )
    assert result.value == 842.40
    assert result.source == "ocr_override"
    assert "920.6" in (result.override_note or "")
    assert "842.4" in (result.override_note or "")
    # 8.5% diff > 3% tolerance but < 10% catastrophic
    assert result.requiere_revision is False


def test_catastrophic_disagreement_forces_revision():
    result = reconcile(geometric_value=1.00, ocr_value=2.00, label="depth_m")
    assert result.value == 2.00
    assert result.source == "ocr_override"
    assert result.requiere_revision is True


def test_non_numeric_inputs_treated_as_missing():
    result = reconcile(geometric_value="abc", ocr_value=None, label="height_m")
    assert result.source == "missing"


def test_apply_to_confidence_clamps_to_unit_interval():
    assert apply_to_confidence(0.95, +0.20) == 1.0
    assert apply_to_confidence(0.05, -0.20) == 0.0
    assert apply_to_confidence(0.50, +0.10) == 0.6


def test_needs_review_threshold():
    assert needs_review_at(0.64) is True
    assert needs_review_at(0.65) is False
    assert needs_review_at(0.70) is False


def test_excavation_example_from_spec():
    # OCR: N.T.N. +0.20 / NIVEL DE DESPLANTE -0.80 => 1.00 m depth
    # JSON geometric depth: 0.50 m (CAD layer V-SITE-CUT)
    result = reconcile(geometric_value=0.50, ocr_value=1.00, label="depth_m")
    assert result.value == 1.00
    assert result.source == "ocr_override"
