"""Integration tests for resilient DWG→DXF normalization."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from coordination.extraction.local_cad_pipeline import normalize_to_dxf


def test_normalize_to_dxf_uses_resilient_converter_for_dwg(tmp_path: Path) -> None:
    dwg = tmp_path / "plan.dwg"
    dwg.write_bytes(b"AC1032\x00")
    dxf = tmp_path / "out.dxf"
    dxf.write_text("stub", encoding="utf-8")

    with patch(
        "coordination.extraction.local_cad_pipeline.convert_dwg_to_dxf_resilient",
        return_value=(dxf, "libredwg_test_full"),
    ) as resilient:
        out_path, tag = normalize_to_dxf(dwg)

    resilient.assert_called_once()
    assert out_path == dxf
    assert tag == "libredwg_test_full"
