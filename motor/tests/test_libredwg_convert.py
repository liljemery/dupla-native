"""LibreDWG convert helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from coordination.extraction.libredwg_convert import (
    classify_dwg2dxf_error,
    convert_dwg_to_dxf_resilient,
    display_name_from_storage,
    invalidate_cached_dxf,
    libredwg_version,
)


def test_classify_read_error() -> None:
    assert classify_dwg2dxf_error("READ ERROR 0x940", returncode=1) == "READ_ERROR"


def test_classify_write_error() -> None:
    assert classify_dwg2dxf_error("File not overwritten, use -y.", returncode=1) == "WRITE_ERROR"


def test_display_name_strips_uuid_prefix() -> None:
    name = "b66d7455-81c4-485c-903d-272597de91fa_Las Nasas.dwg"
    assert display_name_from_storage(name) == "Las Nasas.dwg"


def test_libredwg_version_env_override(monkeypatch) -> None:
    monkeypatch.setenv("LIBREDWG_VERSION", "0.13.4.8317")
    libredwg_version.cache_clear()
    assert libredwg_version() == "0.13.4.8317"
    libredwg_version.cache_clear()


def test_invalidate_cached_dxf_removes_file(tmp_path: Path) -> None:
    from coordination.extraction.cad_cache import file_cache_key, save_cached_json

    dwg = tmp_path / "plan.dwg"
    dwg.write_bytes(b"AC1032\x00")
    out_dir = tmp_path / ".dxf_cache"
    out_dir.mkdir()
    dxf = out_dir / f"{file_cache_key(dwg)}.dxf"
    dxf.write_text("broken", encoding="utf-8")
    save_cached_json(tmp_path, key=file_cache_key(dwg), suffix="dxf_path", payload={"path": str(dxf)})
    invalidate_cached_dxf(dwg, cache_root=tmp_path, output_dir=out_dir)
    assert not dxf.is_file()


def test_convert_dwg_to_dxf_resilient_falls_back_to_minimal(tmp_path: Path, monkeypatch) -> None:
    from coordination.extraction import libredwg_convert as mod

    dwg = tmp_path / "plan.dwg"
    dwg.write_bytes(b"AC1032\x00")
    out_dir = tmp_path / ".dxf_cache"

    def fake_run(dwg_path: Path, dxf_path: Path, **kwargs: object) -> None:
        del dwg_path, kwargs
        dxf_path.parent.mkdir(parents=True, exist_ok=True)
        dxf_path.write_text("stub", encoding="utf-8")

    def fake_probe(path: Path) -> bool:
        return ".minimal" in path.name

    monkeypatch.setattr(mod, "_run_dwg2dxf", fake_run)
    monkeypatch.setattr("coordination.extraction.dxf_geometry.probe_dxf_readable", fake_probe)
    monkeypatch.setenv("LIBREDWG_VERSION", "0.13.4-test")
    mod.libredwg_version.cache_clear()

    dxf_path, tag = convert_dwg_to_dxf_resilient(dwg, output_dir=out_dir)
    mod.libredwg_version.cache_clear()

    assert ".minimal" in dxf_path.name
    assert tag == "libredwg_0.13.4-test_minimal"
