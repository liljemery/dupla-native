from main import _resolve_finished_status


def test_base_extraction_without_rows_is_completed_partial():
    result = {
        "rows": [],
        "output": {"mode": "base_extraction", "requires_rerun": True},
        "extraction": {"mode": "base_extraction"},
    }
    assert _resolve_finished_status(result) == "completed_partial"


def test_budget_with_rows_is_completed():
    result = {
        "rows": [{"code": "01.01", "summary": "Test"}],
        "output": {"mode": "budget"},
    }
    assert _resolve_finished_status(result) == "completed"
