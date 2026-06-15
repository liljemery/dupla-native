from pathlib import Path

from processors.bc3_parser import merge_bc3_catalogs, parse_bc3

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_minimal.bc3"


def test_parse_minimal_bc3_chapters_and_items():
    catalog = parse_bc3(str(FIXTURE))
    assert catalog["chapter_count"] == 1
    assert catalog["item_count"] == 1
    assert catalog["items"][0]["code"] == "PAR01"
    assert catalog["items"][0]["unit"] == "m2"
    assert catalog["hierarchy"]["CAP01"][0]["code"] == "PAR01"
    assert catalog["texts"]["PAR01"] == "Texto largo partida demo"


def test_merge_bc3_catalogs_preserves_items():
    catalog = parse_bc3(str(FIXTURE))
    merged = merge_bc3_catalogs(catalog, catalog)
    assert merged["item_count"] == 2
    assert len(merged["items"]) == 2
