"""Upload gate never rejects DWG originals."""

from __future__ import annotations

from pathlib import Path

from app.domain.cad_upload_gate import validate_cad_upload


def test_dxf_upload_ok_native() -> None:
    result = validate_cad_upload(Path("/tmp/plano.dxf"))
    assert result["ok"] is True
    assert result["cad_conversion_status"] == "native_dxf"


def test_pdf_upload_no_cad_status() -> None:
    result = validate_cad_upload(Path("/tmp/doc.pdf"))
    assert result["ok"] is True
    assert result.get("cad_conversion_status") is None
