"""Tests for P2.8 scale calibrator."""

from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def test_calibrate_mm_bucket():
    from core.scale_calibrator import calibrate_from_dimensions

    dims = [{"measurement": 3500.0, "text": "3.50"}]
    cal = calibrate_from_dimensions(dims)
    assert cal.scale_factor == 1000.0
    assert cal.samples == 1


def test_dimension_chain_valid():
    from core.scale_calibrator import validate_dimension_chains

    dims = [{"text": "3.50+2.00=5.50"}]
    chains = validate_dimension_chains(dims)
    assert len(chains) == 1
    assert chains[0]["ok"] is True


def test_dimension_chain_invalid():
    from core.scale_calibrator import validate_dimension_chains

    dims = [{"text": "3.50+2.00=6.00"}]
    chains = validate_dimension_chains(dims)
    assert chains[0]["ok"] is False


def test_apply_scale_calibration_agreement():
    from core.scale_calibrator import apply_scale_calibration

    cad = {
        "cad_facts": {
            "dimensions": [
                {"measurement": 3.5, "text": "3.50"},
                {"measurement": 2.0, "text": "2.00"},
            ],
            "texts": [],
        }
    }
    stats = apply_scale_calibration(cad)
    assert stats["applied"] is True
    assert stats["cota_agreement_ratio"] == 1.0
