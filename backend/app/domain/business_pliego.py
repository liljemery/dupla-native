from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.domain.construction_pliego import construction_lines_complete, construction_pliego_is_active
from app.domain.ga_fo_01_arquitectura import (
    ga_fo_block_approved,
    ga_fo_item_states_terminal_complete,
)

BUSINESS_PLIEGO_KEY = "business_pliego"
BUSINESS_PLIEGO_SCHEMA_VERSION = 1

# Keys aligned with product doc (Flujo_Actualizado_Pliego)
SECTION_SCOPE = "scope"
SECTION_SPECS = "technical_specifications"
SECTION_MATERIALS = "materials"
SECTION_SYSTEMS = "construction_systems"
SECTION_RESTRICTIONS = "restrictions"
SECTION_ASSUMPTIONS = "base_assumptions"
SECTION_EXCLUSIONS = "exclusions"
SECTION_DOCS = "validated_documentation"
SECTION_RISKS = "identified_risks"

BUSINESS_PLIEGO_SECTION_KEYS: tuple[str, ...] = (
    SECTION_SCOPE,
    SECTION_SPECS,
    SECTION_MATERIALS,
    SECTION_SYSTEMS,
    SECTION_RESTRICTIONS,
    SECTION_ASSUMPTIONS,
    SECTION_EXCLUSIONS,
    SECTION_DOCS,
    SECTION_RISKS,
)

MIN_SECTION_LEN = 10


def default_empty_sections() -> dict[str, str]:
    return {k: "" for k in BUSINESS_PLIEGO_SECTION_KEYS}


def get_business_pliego_block(spec: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(spec, dict):
        return {}
    raw = spec.get(BUSINESS_PLIEGO_KEY)
    return raw if isinstance(raw, dict) else {}


def sections_dict(block: dict[str, Any]) -> dict[str, str]:
    raw = block.get("sections")
    if not isinstance(raw, dict):
        return default_empty_sections()
    out: dict[str, str] = {}
    for k in BUSINESS_PLIEGO_SECTION_KEYS:
        v = raw.get(k, "")
        out[k] = v if isinstance(v, str) else str(v) if v is not None else ""
    return out


def transition_blockers_for_business_pliego(spec: dict[str, Any] | None) -> Optional[str]:
    """Return Spanish error message if pliego blocks transition to BUDGETING_PIPELINE, else None."""
    if not isinstance(spec, dict):
        return "Falta el pliego de condiciones; completa o genera el documento."
    if construction_pliego_is_active(spec):
        if not construction_lines_complete(spec):
            return (
                "Completa todas las partidas del pliego de obra: cada ítem debe tener unidad, "
                "cantidad mayor a cero y precio unitario (guardá el documento en la pestaña Pliego)."
            )
        if ga_fo_block_approved(spec):
            return None
        block = get_business_pliego_block(spec)
        if not bool(block.get("approved")):
            return "El pliego de condiciones debe estar aprobado antes de iniciar el presupuesto."
        return None

    ga = spec.get("ga_fo_01_arquitectura")
    if isinstance(ga, dict) and ga.get("schema_version") == 1:
        st = ga.get("item_states")
        st_dict = st if isinstance(st, dict) else {}
        if not ga_fo_item_states_terminal_complete(st_dict):
            return (
                "Completa el checklist GA-FO-01 (cada documento en Completo o No aplica) "
                "y guardá en la pestaña Pliego."
            )
        if not ga_fo_block_approved(spec):
            block = get_business_pliego_block(spec)
            if bool(block.get("approved")):
                return None
            return "El pliego de condiciones debe estar aprobado antes de iniciar el presupuesto."
        return None

    block = get_business_pliego_block(spec)
    if not block:
        summary = str(spec.get("summary") or "").strip()
        if len(summary) >= MIN_SECTION_LEN:
            return None
        return (
            f"Completa el pliego de condiciones: resumen mínimo {MIN_SECTION_LEN} caracteres "
            "o genera el pliego estructurado (todas las secciones y aprobación)."
        )

    sec = sections_dict(block)
    missing = [k for k in BUSINESS_PLIEGO_SECTION_KEYS if len(sec.get(k, "").strip()) < MIN_SECTION_LEN]
    if missing:
        return (
            "Completa todas las secciones del pliego de condiciones (mínimo "
            f"{MIN_SECTION_LEN} caracteres por sección). Faltan: {', '.join(missing)}"
        )
    if not bool(block.get("approved")):
        return "El pliego de condiciones debe estar aprobado antes de iniciar el presupuesto."
    return None


def pliego_sections_incomplete_message(spec: dict[str, Any] | None) -> Optional[str]:
    """Like transition blockers but only checks section lengths (not approval)."""
    if not isinstance(spec, dict):
        return "Falta el pliego de condiciones."
    if construction_pliego_is_active(spec):
        if not construction_lines_complete(spec):
            return (
                "Faltan partidas por completar (unidad, cantidad y precio unitario en cada ítem del pliego de obra)."
            )
        return None
    block = get_business_pliego_block(spec)
    if not block:
        ga = spec.get("ga_fo_01_arquitectura")
        if isinstance(ga, dict) and ga.get("schema_version") == 1:
            st = ga.get("item_states")
            st_dict = st if isinstance(st, dict) else {}
            if not ga_fo_item_states_terminal_complete(st_dict):
                return "Faltan documentos del checklist GA-FO-01 por marcar como Completo o No aplica."
            return None
        return "Genera o completa el pliego estructurado antes de aprobar."
    sec = sections_dict(block)
    missing = [k for k in BUSINESS_PLIEGO_SECTION_KEYS if len(sec.get(k, "").strip()) < MIN_SECTION_LEN]
    if missing:
        return f"Faltan secciones o son demasiado cortas: {', '.join(missing)}"
    return None


def business_pliego_sections_equal(a: dict[str, str], b: dict[str, str]) -> bool:
    for k in BUSINESS_PLIEGO_SECTION_KEYS:
        if (a.get(k) or "").strip() != (b.get(k) or "").strip():
            return False
    return True


def clear_approval_in_block(block: dict[str, Any]) -> None:
    block["approved"] = False
    block["approved_at"] = None
    block["approved_by_user_uuid"] = None


def apply_approval(
    block: dict[str, Any],
    approver_user_uuid: UUID,
) -> None:
    block["approved"] = True
    block["approved_at"] = datetime.now(timezone.utc).isoformat()
    block["approved_by_user_uuid"] = str(approver_user_uuid)


def ensure_business_pliego_structure(spec: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of spec with a normalized business_pliego block (mutates copy only)."""
    out = deepcopy(spec) if spec else {}
    block = get_business_pliego_block(out)
    if not block:
        out[BUSINESS_PLIEGO_KEY] = {
            "schema_version": BUSINESS_PLIEGO_SCHEMA_VERSION,
            "sections": default_empty_sections(),
            "approved": False,
            "approved_at": None,
            "approved_by_user_uuid": None,
            "generated_at": None,
        }
        return out
    if "sections" not in block or not isinstance(block.get("sections"), dict):
        block["sections"] = default_empty_sections()
    else:
        merged = default_empty_sections()
        merged.update(sections_dict(block))
        block["sections"] = merged
    block.setdefault("schema_version", BUSINESS_PLIEGO_SCHEMA_VERSION)
    block.setdefault("approved", False)
    block.setdefault("approved_at", None)
    block.setdefault("approved_by_user_uuid", None)
    out[BUSINESS_PLIEGO_KEY] = block
    return out
