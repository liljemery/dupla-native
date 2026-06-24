"""Tests for budget CAD attachment helpers."""

from __future__ import annotations

import sys
from pathlib import Path

from app.domain.budget_cad_attachments import auxiliary_dxf_candidates, unusable_dwg_names


def _motor_root() -> Path | None:
    candidates = (
        Path("/motor"),
        Path(__file__).resolve().parents[2] / "motor",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _file_cache_key(path: Path) -> str:
    root = _motor_root()
    if root is not None:
        root_text = str(root)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)
        from coordination.extraction.cad_cache import file_cache_key

        return file_cache_key(path)
    raise RuntimeError("motor package not available for cache key")


class _FakeFile:
    def __init__(
        self,
        *,
        original_name: str,
        storage_key: str,
        snapshot: dict | None = None,
    ) -> None:
        self.original_name = original_name
        self.storage_key = storage_key
        self.file_ingest_snapshot = snapshot


def test_auxiliary_dxf_from_gate_cache(tmp_path: Path) -> None:
    dwg = tmp_path / "Cimientos.dwg"
    dwg.write_bytes(b"AC1032\x00\x00\x00\x00\x00\x00\x03\xc0")
    cache_dir = tmp_path / ".dxf_cache"
    cache_dir.mkdir()
    dxf = cache_dir / f"{_file_cache_key(dwg)}.dxf"
    dxf.write_text(
        "0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n",
        encoding="utf-8",
    )
    found = auxiliary_dxf_candidates(dwg, tmp_path)
    assert dxf in found


def test_unusable_dwg_without_dxf(tmp_path: Path) -> None:
    dwg = tmp_path / "fail.dwg"
    dwg.write_bytes(b"AC1032\x00")
    pf = _FakeFile(
        original_name="fail.dwg",
        storage_key=str(dwg),
        snapshot={
            "cad_conversion_status": "requires_dxf_export",
            "cad_conversion_error_code": "READ_ERROR",
        },
    )
    assert unusable_dwg_names([pf], tmp_path) == ["fail.dwg"]


def test_unusable_dwg_skipped_when_dxf_in_budget(tmp_path: Path) -> None:
    dwg = tmp_path / "ok.dwg"
    dwg.write_bytes(b"AC1032\x00")
    dxf = tmp_path / "ok.dxf"
    dxf.write_text("0\nEOF\n", encoding="utf-8")
    dwg_pf = _FakeFile(
        original_name="ok.dwg",
        storage_key=str(dwg),
        snapshot={"cad_conversion_status": "requires_dxf_export"},
    )
    dxf_pf = _FakeFile(original_name="ok.dxf", storage_key=str(dxf))
    assert unusable_dwg_names([dwg_pf, dxf_pf], tmp_path) == []
