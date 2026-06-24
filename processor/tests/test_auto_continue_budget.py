"""Auto-continue from base extraction into budget."""

import pytest

from pipeline_discipline import resolve_auto_continue_disciplines


@pytest.fixture(autouse=True)
def _clear_extraction_only_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUPLA_EXTRACTION_ONLY", raising=False)
    monkeypatch.delenv("DUPLA_ALLOW_MULTI_DISCIPLINE", raising=False)


def test_auto_continue_infers_single_discipline_by_default() -> None:
    result = resolve_auto_continue_disciplines(
        discipline_id=None,
        suggested_discipline="estructura",
    )
    assert result == (["estructura"], "auto_continue_inferred")


def test_auto_continue_all_for_todas_without_multi_env() -> None:
    result = resolve_auto_continue_disciplines(
        discipline_id="todas",
        suggested_discipline="arquitectura",
    )
    assert result is not None
    disciplines, mode = result
    assert mode == "auto_continue_all"
    assert set(disciplines) == {"arquitectura", "estructura", "sanitario", "electrico"}


def test_auto_continue_all_when_multi_enabled_and_todas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUPLA_ALLOW_MULTI_DISCIPLINE", "1")
    result = resolve_auto_continue_disciplines(
        discipline_id="todas",
        suggested_discipline="arquitectura",
    )
    assert result is not None
    disciplines, mode = result
    assert mode == "auto_continue_all"
    assert set(disciplines) == {"arquitectura", "estructura", "sanitario", "electrico"}


def test_extraction_only_env_disables_auto_continue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUPLA_EXTRACTION_ONLY", "1")
    assert (
        resolve_auto_continue_disciplines(
            discipline_id=None,
            suggested_discipline="arquitectura",
        )
        is None
    )
