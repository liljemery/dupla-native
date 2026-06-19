"""Discipline resolution helpers (import-safe for unit tests)."""
from __future__ import annotations

import os
import unicodedata

_STANDARD_DISCIPLINES = ("arquitectura", "estructura", "sanitario", "electrico")
_ALL_DISCIPLINE_ALIASES = {"all", "todas", "todos", "todo", "*"}


def env_bool(name: str, default: bool = False) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_discipline_token(value: str | None) -> str:
    text = (value or "").strip().lower()
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def resolve_auto_continue_disciplines(
    *,
    discipline_id: str | None,
    suggested_discipline: str,
) -> tuple[list[str], str] | None:
    """After base extraction, continue into budget unless extraction-only is requested."""
    if env_bool("DUPLA_EXTRACTION_ONLY", False):
        return None
    allow_multi = env_bool("DUPLA_ALLOW_MULTI_DISCIPLINE", False)
    raw = normalize_discipline_token(discipline_id)
    if allow_multi and (not raw or raw in _ALL_DISCIPLINE_ALIASES):
        return list(_STANDARD_DISCIPLINES), "auto_continue_all"
    return [suggested_discipline], "auto_continue_inferred"


if __name__ == "__main__":
    assert resolve_auto_continue_disciplines(discipline_id=None, suggested_discipline="estructura") == (
        ["estructura"],
        "auto_continue_inferred",
    )
    print("pipeline_discipline self-check ok")
