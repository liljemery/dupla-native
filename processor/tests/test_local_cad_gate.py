"""LibreDWG gate helpers."""

from coordination.extraction.libredwg_convert import dwg2dxf_available, is_binary_dwg


def test_dwg2dxf_availability_is_bool() -> None:
    assert isinstance(dwg2dxf_available(), bool)


def test_is_binary_dwg_rejects_dxf(tmp_path) -> None:
    dxf = tmp_path / "plain.dxf"
    dxf.write_text("0\nSECTION\n", encoding="ascii")
    assert is_binary_dwg(dxf) is False
