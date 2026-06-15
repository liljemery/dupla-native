"""
OCR vs geometric reconciliation.

When a measurement is available from two sources — a geometric value derived
from CAD/JSON entities and an OCR value read from a plan annotation — the OCR
value is authoritative when it disagrees with geometry, but the geometric
value is kept as secondary evidence.

Spec rule (paraphrased from Dupla semantic layer brief):

    Si una cota, sección, nivel, espesor o dimensión impresa en el plano por
    OCR contradice el JSON geométrico, usa la cota OCR como autoridad
    principal. Conserva el dato geométrico como evidencia secundaria.

This module is a pure function — it does not call any model or perform IO.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_DEFAULT_TOLERANCE_PCT = 0.03  # 3% — typical CAD rounding noise

_OCR_OVERRIDE_BONUS = 0.05
_OCR_AGREEMENT_BONUS = 0.10
_GEOM_ONLY_PENALTY = -0.20
_OCR_ONLY_PENALTY = -0.10
_REVIEW_THRESHOLD = 0.65


@dataclass
class ReconciliationResult:
    """Outcome of comparing geometric and OCR measurements."""

    value: float | None
    source: str
    formula_note: str
    confidence_delta: float
    requiere_revision: bool
    assumption: str | None = None
    override_note: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def reconcile(
    *,
    geometric_value: float | None,
    ocr_value: float | None,
    label: str,
    unit: str = "m",
    tolerance_pct: float = _DEFAULT_TOLERANCE_PCT,
) -> ReconciliationResult:
    """Reconcile two measurements of the same physical quantity.

    Rules:
        - Both None: return None, requiere_revision=True.
        - Geometric only: use it, small penalty, mark for review.
        - OCR only: use it, mark for review (single source).
        - Both, within tolerance: use OCR (or geometric — they agree),
          confidence bonus.
        - Both, outside tolerance: use OCR as authoritative,
          add override note and assumption, mild confidence bonus
          (decision is documented).
    """
    geom = _coerce_number(geometric_value)
    ocr = _coerce_number(ocr_value)

    if geom is None and ocr is None:
        return ReconciliationResult(
            value=None,
            source="missing",
            formula_note="No geometric or OCR measurement available.",
            confidence_delta=-0.30,
            requiere_revision=True,
            assumption=f"{label}: ningún dato disponible. Requiere medición manual.",
            metadata={"label": label, "unit": unit},
        )

    if geom is None:
        return ReconciliationResult(
            value=ocr,
            source="ocr_only",
            formula_note=f"{label} = OCR ({ocr:.4f} {unit}); geometric data missing.",
            confidence_delta=_OCR_ONLY_PENALTY,
            requiere_revision=True,
            assumption=f"{label}: solo dato OCR disponible — sin verificación geométrica.",
            metadata={"label": label, "unit": unit, "ocr_value": ocr},
        )

    if ocr is None:
        return ReconciliationResult(
            value=geom,
            source="geometric_only",
            formula_note=f"{label} = geometric ({geom:.4f} {unit}); OCR data missing.",
            confidence_delta=_GEOM_ONLY_PENALTY,
            requiere_revision=True,
            assumption=f"{label}: solo dato geométrico disponible — sin cota OCR para confirmar.",
            metadata={"label": label, "unit": unit, "geometric_value": geom},
        )

    diff = abs(geom - ocr)
    base = max(abs(ocr), 1e-9)
    pct_diff = diff / base

    if pct_diff <= tolerance_pct:
        return ReconciliationResult(
            value=ocr,
            source="ocr_confirmed",
            formula_note=(
                f"{label} = {ocr:.4f} {unit} (OCR confirma geometría dentro de "
                f"{tolerance_pct * 100:.1f}% de tolerancia)."
            ),
            confidence_delta=_OCR_AGREEMENT_BONUS,
            requiere_revision=False,
            assumption=None,
            metadata={
                "label": label,
                "unit": unit,
                "ocr_value": ocr,
                "geometric_value": geom,
                "pct_diff": pct_diff,
            },
        )

    override_note = (
        f"{label}: cota OCR ({ocr:.4f} {unit}) sustituye valor geométrico "
        f"({geom:.4f} {unit}); diferencia {pct_diff * 100:.1f}% supera tolerancia "
        f"de {tolerance_pct * 100:.1f}%."
    )
    return ReconciliationResult(
        value=ocr,
        source="ocr_override",
        formula_note=(
            f"{label} = {ocr:.4f} {unit} (OCR autoritativo sobre geometría)."
        ),
        confidence_delta=_OCR_OVERRIDE_BONUS,
        requiere_revision=pct_diff > 0.10,
        assumption=override_note,
        override_note=override_note,
        metadata={
            "label": label,
            "unit": unit,
            "ocr_value": ocr,
            "geometric_value": geom,
            "pct_diff": pct_diff,
            "tolerance_pct": tolerance_pct,
        },
    )


def apply_to_confidence(base_confidence: float, delta: float) -> float:
    """Clamp confidence + delta into [0.0, 1.0]."""
    return max(0.0, min(1.0, base_confidence + delta))


def needs_review_at(confidence: float, threshold: float = _REVIEW_THRESHOLD) -> bool:
    """Returns True when confidence falls below revision threshold."""
    return confidence < threshold


def _coerce_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f
