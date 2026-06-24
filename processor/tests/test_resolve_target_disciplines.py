"""Discipline resolution for budget pipeline."""

from tasks import _resolve_target_disciplines


def test_todas_runs_all_standard_disciplines() -> None:
    disciplines, mode = _resolve_target_disciplines("todas", ["ES 01.dwg"])
    assert mode == "all_explicit"
    assert set(disciplines) == {"arquitectura", "estructura", "sanitario", "electrico"}


def test_single_discipline_unchanged() -> None:
    disciplines, mode = _resolve_target_disciplines("estructura", ["ES 01.dwg"])
    assert mode == "explicit"
    assert disciplines == ["estructura"]
