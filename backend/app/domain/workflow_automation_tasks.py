"""Tarjetas creadas por automatización de flujo (no bloquean avance de fase)."""

from __future__ import annotations

from typing import Any
from uuid import UUID


def automation_tasks_block(workflow_meta: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(workflow_meta, dict):
        return {}
    raw = workflow_meta.get("automation_tasks")
    return raw if isinstance(raw, dict) else {}


def append_automation_card_uuid(auto: dict[str, Any], card_uuid: UUID) -> dict[str, Any]:
    out = dict(auto)
    existing = out.get("card_uuids")
    uuids: list[str] = [str(x) for x in existing] if isinstance(existing, list) else []
    sid = str(card_uuid)
    if sid not in uuids:
        uuids.append(sid)
    out["card_uuids"] = uuids
    return out


LEGACY_AUTOMATION_TITLE_BY_FLAG: dict[str, str] = {
    "enter_architecture_review": "Revisión técnica documental (entrada a revisión de arquitectura)",
    "enter_management_approval": "Revisión de Control — presupuesto",
    "after_documentary_export": "Revisión informe documental generado",
}


def legacy_automation_titles(workflow_meta: dict[str, Any] | None) -> frozenset[str]:
    auto = automation_tasks_block(workflow_meta)
    titles: set[str] = set()
    for flag, title in LEGACY_AUTOMATION_TITLE_BY_FLAG.items():
        if auto.get(flag):
            titles.add(title)
    return frozenset(titles)


def automation_card_uuids(workflow_meta: dict[str, Any] | None) -> frozenset[UUID]:
    auto = automation_tasks_block(workflow_meta)
    found: set[UUID] = set()
    raw_list = auto.get("card_uuids")
    if isinstance(raw_list, list):
        for item in raw_list:
            try:
                found.add(UUID(str(item)))
            except ValueError:
                continue
    for key, val in auto.items():
        if not key.endswith("_card_uuid") or not val:
            continue
        try:
            found.add(UUID(str(val)))
        except ValueError:
            continue
    return frozenset(found)
