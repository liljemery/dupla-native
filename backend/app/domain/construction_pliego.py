"""Partidas de pliego de obra (construction_pliego) — validación alineada con frontend."""

from __future__ import annotations

from typing import Any, Optional

CONSTRUCTION_PLIEGO_KEY = "construction_pliego"

# Mismos id_item que `frontend/src/constants/constructionPliegoStructure.ts`
EXPECTED_ITEM_IDS: tuple[str, ...] = (
    "1.1",
    "1.2",
    "1.3",
    "1.4",
    "1.5",
    "2.1",
    "2.2",
    "2.3",
    "2.4",
    "2.5",
    "2.6",
    "3.1",
    "3.2",
    "3.3",
    "3.4",
    "3.5",
    "4.1",
    "4.2",
    "4.3",
    "4.4",
    "5.1",
    "5.2",
    "5.3",
    "5.4",
    "5.5",
    "5.6",
    "6.1",
    "6.2",
    "6.3",
    "6.4",
    "6.5",
    "7.1",
    "7.2",
    "7.3",
    "7.4",
    "8.1",
    "8.2",
    "8.3",
)


def _parse_num(s: Any) -> Optional[float]:
    if s is None:
        return None
    t = str(s).strip().replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _row_complete(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if not str(row.get("unidad") or "").strip():
        return False
    q = _parse_num(row.get("cantidad"))
    u = _parse_num(row.get("unitario"))
    if q is None or q <= 0:
        return False
    if u is None or u < 0:
        return False
    return True


def construction_pliego_block(spec: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(spec, dict):
        return {}
    raw = spec.get(CONSTRUCTION_PLIEGO_KEY)
    return raw if isinstance(raw, dict) else {}


def construction_pliego_is_active(spec: dict[str, Any] | None) -> bool:
    b = construction_pliego_block(spec)
    if not b:
        return False
    return int(b.get("schema_version") or 0) == 1


def construction_lines_complete(spec: dict[str, Any] | None) -> bool:
    if not construction_pliego_is_active(spec):
        return False
    lines = construction_pliego_block(spec).get("lines")
    if not isinstance(lines, dict):
        return False
    for item_id in EXPECTED_ITEM_IDS:
        if not _row_complete(lines.get(item_id)):
            return False
    return True
