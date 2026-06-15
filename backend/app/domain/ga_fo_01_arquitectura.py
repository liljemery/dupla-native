from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

GA_FO_SPEC_KEY = "ga_fo_01_arquitectura"
_IDS_PATH = Path(__file__).with_name("ga_fo_01_expected_item_ids.json")
_EXPECTED_ITEM_IDS: frozenset[str] = frozenset(
    json.loads(_IDS_PATH.read_text(encoding="utf-8")),
)


def expected_ga_fo_item_ids() -> frozenset[str]:
    return _EXPECTED_ITEM_IDS


def _item_states_dict(ga: dict[str, Any]) -> dict[str, Any]:
    raw = ga.get("item_states")
    return raw if isinstance(raw, dict) else {}


def ga_fo_item_states_terminal_complete(item_states: dict[str, Any] | None) -> bool:
    """True si cada ítem del catálogo GA-FO-01 está en COMPLETO o NO_APLICA."""
    if not item_states:
        return False
    for item_id in _EXPECTED_ITEM_IDS:
        row = item_states.get(item_id)
        if not isinstance(row, dict):
            return False
        estado = row.get("estado")
        if estado not in ("COMPLETO", "NO_APLICA"):
            return False
    return True


def ga_fo_block_ready_for_approval(spec: dict[str, Any] | None) -> bool:
    if not isinstance(spec, dict):
        return False
    ga = spec.get(GA_FO_SPEC_KEY)
    if not isinstance(ga, dict) or ga.get("schema_version") != 1:
        return False
    return ga_fo_item_states_terminal_complete(_item_states_dict(ga))


def ga_fo_block_approved(spec: dict[str, Any] | None) -> bool:
    if not isinstance(spec, dict):
        return False
    ga = spec.get(GA_FO_SPEC_KEY)
    if not isinstance(ga, dict):
        return False
    return bool(ga.get("approved"))


def apply_ga_fo_approval(ga: dict[str, Any], approver_user_uuid: UUID) -> None:
    ga["approved"] = True
    ga["approved_at"] = datetime.now(timezone.utc).isoformat()
    ga["approved_by_user_uuid"] = str(approver_user_uuid)


def clear_ga_fo_approval(ga: dict[str, Any]) -> None:
    ga["approved"] = False
    ga["approved_at"] = None
    ga["approved_by_user_uuid"] = None
