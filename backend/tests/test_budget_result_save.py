from app.services.budget_service import _normalize_budget_row


def test_normalize_budget_row_line_recalculates_amount():
    row = _normalize_budget_row(
        {
            "row_type": "line",
            "code": "01.01",
            "summary": "Muro",
            "quantity": 10,
            "unit_price": 1500.5,
            "unit": "m2",
        }
    )
    assert row["amount"] == 15005.0


def test_normalize_budget_row_chapter_keeps_amount():
    row = _normalize_budget_row(
        {
            "row_type": "chapter",
            "code": "01",
            "summary": "Obra gris",
            "amount": 99999.99,
        }
    )
    assert row["amount"] == 99999.99
