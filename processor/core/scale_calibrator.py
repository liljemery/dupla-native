"""
(P2.8) Scale calibrator — cotas OCR/CAD + validación de cadenas.

Refines the unit scale (mm -> m) by comparing geometric dimension measurements
from Model Derivative with the numeric text printed on each cota. Also checks
simple dimension chains where multiple cotas should sum to a total.

Pure geometry/text — no LLM calls.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("dupla.scale_calibrator")

_NUMERIC_UNIT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:m|mt|mts|metros?|mm|cm)?",
    re.IGNORECASE,
)
_CHAIN_SUM_RE = re.compile(
    r"(\d+(?:[.,]\d+)?(?:\s*[+\-]\s*\d+(?:[.,]\d+)?)+)\s*=\s*(\d+(?:[.,]\d+)?)",
)


def _num(v: Any) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def _parse_dimension_text(text: str) -> float | None:
    if not text:
        return None
    cleaned = text.replace(",", ".")
    m = _NUMERIC_UNIT_RE.search(cleaned)
    if not m:
        return None
    val = _num(m.group(1))
    if val is None or val <= 0:
        return None
    low = cleaned.lower()
    if "mm" in low and val > 50:
        return val / 1000.0
    if "cm" in low and val > 5:
        return val / 100.0
    # Bare number: assume metres if small, mm if large
    if val > 500:
        return val / 1000.0
    if val > 50:
        return val / 100.0
    return val


def _infer_scale_bucket(measured: float, printed_m: float) -> float | None:
    if measured <= 0 or printed_m <= 0:
        return None
    ratio = measured / printed_m
    if 800 < ratio < 1200:
        return 1000.0
    if 80 < ratio < 120:
        return 100.0
    if 8 < ratio < 12:
        return 10.0
    if 0.8 < ratio < 1.2:
        return 1.0
    return None


@dataclass
class ScaleCalibration:
    scale_factor: float = 1.0
    confidence: float = 0.0
    samples: int = 0
    source: str = "none"
    chain_checks: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scale_factor": self.scale_factor,
            "confidence": round(self.confidence, 3),
            "samples": self.samples,
            "source": self.source,
            "chain_checks": self.chain_checks,
            "warnings": self.warnings,
        }


def calibrate_from_dimensions(
    dimensions: list[dict[str, Any]],
    *,
    texts: list[dict[str, Any]] | None = None,
) -> ScaleCalibration:
    """Estimate scale factor from dimension measurement vs printed text."""
    buckets: list[float] = []
    for dim in dimensions:
        meas = _num(dim.get("measurement"))
        text_val = _parse_dimension_text(str(dim.get("text") or ""))
        if meas is None or text_val is None:
            continue
        bucket = _infer_scale_bucket(meas, text_val)
        if bucket is not None:
            buckets.append(bucket)

    # Fallback: parse standalone numeric texts that look like cotas (e.g. "3.50")
    for txt in texts or []:
        content = str(txt.get("content") or txt.get("text") or "")
        if not content or len(content) > 20:
            continue
        val = _parse_dimension_text(content)
        if val is not None and 0.1 < val < 100:
            # Without geometric pairing we cannot infer bucket; skip
            pass

    if not buckets:
        return ScaleCalibration(source="none")

    counter = Counter(buckets)
    scale, count = counter.most_common(1)[0]
    confidence = count / len(buckets)
    return ScaleCalibration(
        scale_factor=scale,
        confidence=confidence,
        samples=len(buckets),
        source="dimension_ocr",
    )


def validate_dimension_chains(
    dimensions: list[dict[str, Any]],
    *,
    tolerance_pct: float = 0.05,
) -> list[dict[str, Any]]:
    """Validate A+B+...=TOTAL patterns found in dimension overlay text."""
    results: list[dict[str, Any]] = []
    for dim in dimensions:
        text = str(dim.get("text") or "")
        m = _CHAIN_SUM_RE.search(text.replace(",", "."))
        if not m:
            continue
        parts_str, total_str = m.group(1), m.group(2)
        parts = [_num(p.strip()) for p in re.split(r"[+\-]", parts_str)]
        parts = [p for p in parts if p is not None]
        total = _num(total_str)
        if not parts or total is None:
            continue
        computed = sum(parts)
        delta = abs(computed - total)
        ok = delta <= max(tolerance_pct * total, 0.01)
        results.append({
            "text": text[:80],
            "parts": parts,
            "total": total,
            "computed": round(computed, 4),
            "ok": ok,
            "delta_m": round(delta, 4),
        })
    return results


def apply_scale_calibration(cad_facts: dict[str, Any]) -> dict[str, Any]:
    """Validate cotas vs geometry and dimension chains; report only (no re-scale).

    json_processor already converts mm->m via _infer_global_scale. This step
    confirms cotas agree with geometry and flags broken chains.
    """
    cf = cad_facts.setdefault("cad_facts", {})
    dimensions = cf.get("dimensions") or []
    texts = cf.get("texts") or []

    cal = calibrate_from_dimensions(dimensions, texts=texts)
    cal.chain_checks = validate_dimension_chains(dimensions)
    bad_chains = [c for c in cal.chain_checks if not c.get("ok")]

    # Agreement check: for already-scaled dims, meas ~ text in metres
    agreements = 0
    checked = 0
    for dim in dimensions:
        meas = _num(dim.get("measurement"))
        text_val = _parse_dimension_text(str(dim.get("text") or ""))
        if meas is None or text_val is None:
            continue
        checked += 1
        if abs(meas - text_val) / max(text_val, 0.01) <= 0.05:
            agreements += 1

    agreement_ratio = agreements / checked if checked else 0.0
    if bad_chains:
        cal.warnings.append(f"{len(bad_chains)} cadenas de cotas inconsistentes")
    if checked and agreement_ratio < 0.5:
        cal.warnings.append(
            f"solo {agreements}/{checked} cotas coinciden con geometria (escala dudosa)"
        )

    stats = {
        "applied": True,
        "mode": "validate",
        "cota_agreement_ratio": round(agreement_ratio, 3),
        "cota_pairs_checked": checked,
        **cal.to_dict(),
    }
    cad_facts["scale_calibration"] = stats
    if checked:
        logger.info(
            "Scale calibrator: agreement=%.0f%% pairs=%d chains=%d bad=%d",
            agreement_ratio * 100,
            checked,
            len(cal.chain_checks),
            len(bad_chains),
        )
    return stats
