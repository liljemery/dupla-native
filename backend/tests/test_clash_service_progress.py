from app.services.clash_service import (
    extract_extraction_progress,
    format_extraction_progress_message,
)


def test_extract_extraction_progress_returns_dict() -> None:
    payload = {"status": "started", "progress": {"processed": 2, "total": 10, "phase": "extraction"}}
    assert extract_extraction_progress(payload) == payload["progress"]


def test_extract_extraction_progress_missing() -> None:
    assert extract_extraction_progress({"status": "started"}) is None
    assert extract_extraction_progress(None) is None


def test_format_extraction_progress_message_extraction_phase() -> None:
    msg = format_extraction_progress_message({"processed": 3, "total": 12, "phase": "extraction"})
    assert msg == "Extrayendo planos 3/12…"


def test_format_extraction_progress_message_clash_phase() -> None:
    msg = format_extraction_progress_message({"processed": 12, "total": 12, "phase": "clash"})
    assert msg == "Detectando clashes (12/12 planos extraídos)…"


def test_format_extraction_progress_message_empty() -> None:
    assert format_extraction_progress_message(None) is None
    assert format_extraction_progress_message({"processed": 0, "total": 0}) is None
