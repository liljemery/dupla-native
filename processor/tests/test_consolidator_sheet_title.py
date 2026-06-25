"""Excel sheet title sanitization for budget consolidator."""

from budget.consolidator import _excel_sheet_title, _unique_sheet_title


def test_excel_sheet_title_strips_invalid_chars() -> None:
    title = _excel_sheet_title("SANITARIO / PLOMERÍA")
    assert "/" not in title
    assert "PLOMER" in title


def test_unique_sheet_title_avoids_collisions() -> None:
    used: set[str] = set()
    first = _unique_sheet_title("A/B", used)
    second = _unique_sheet_title("A-B", used)
    assert first != second
    assert "/" not in first
    assert "/" not in second
