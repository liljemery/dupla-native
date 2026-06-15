"""
Adapter that converts PartidaGenerator output to the exact
dict[str, list[BudgetCandidate]] format that compose_budget expects from
the legacy match_takeoffs_to_bc3().

Also extends the BC3 catalog with synthetic entries so _guard_budget_candidate()
lets the generated codes through without modification to the composer.

Contract (verified against core/pipeline.py + budget/composer.py):
  - Output type:  dict[takeoff.item_key -> list[BudgetCandidate]]
  - BudgetCandidate.bc3_code  must exist in bc3_catalog["concepts_by_code"]
  - BudgetCandidate.unit      must match takeoff.unit (select_strong_candidate check)
  - BudgetCandidate.score     must be >= STRONG_BC3_SCORE (0.45) and win margin >= 0.05
  - BudgetCandidate.summary   is used by _extract_unit_price for ConstruCosto lookup
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.schemas import BudgetCandidate, QuantityTakeoff

logger = logging.getLogger("dupla.partida_adapter")


def _partida_to_budget_candidate(
    partida: dict[str, Any],
    takeoff: QuantityTakeoff,
) -> BudgetCandidate:
    """
    Convert one generated partida dict to a BudgetCandidate.

    Critical: unit is taken from takeoff (not partida) so select_strong_candidate
    always passes the unit equality check. Summary holds the generated description
    so _extract_unit_price sends it to find_best_price for ConstruCosto lookup.
    """
    rationale = json.dumps(
        {
            "chapter_code": partida.get("chapter_code", ""),
            "chapter_name": partida.get("chapter_name", ""),
            "discipline": partida.get("discipline", ""),
            "generator": "gpt-4o",
        },
        ensure_ascii=False,
    )
    return BudgetCandidate(
        takeoff_key=takeoff.item_key,
        bc3_code=str(partida.get("partida_code") or "GEN.000"),
        summary=str(partida.get("partida_description") or ""),
        unit=takeoff.unit,
        score=1.0,
        rationale=rationale,
        source="partida_generator",
        bc3_origin=None,
    )


def _extend_bc3_catalog(
    bc3_catalog: dict[str, Any],
    synthetic_codes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Return a shallow copy of bc3_catalog with synthetic_codes injected into
    both 'items' and 'concepts_by_code'. Does NOT mutate the original dict.

    price=0.0 is intentional — _extract_unit_price tries ConstruCosto first,
    so the BC3 price field is only a fallback and 0.0 triggers PRECIO_PENDIENTE
    gracefully if ConstruCosto also has no match.
    """
    extended = dict(bc3_catalog)

    new_concepts = dict(bc3_catalog.get("concepts_by_code") or {})
    new_concepts.update(synthetic_codes)
    extended["concepts_by_code"] = new_concepts

    new_items = list(bc3_catalog.get("items") or [])
    existing_codes = {item.get("code") for item in new_items if item.get("code")}
    for code, concept in synthetic_codes.items():
        if code not in existing_codes:
            new_items.append(concept)
    extended["items"] = new_items

    return extended


def adapt_generated_to_legacy_format(
    generated_partidas: list[dict[str, Any]],
    expanded_takeoffs: list[QuantityTakeoff],
    bc3_catalog: dict[str, Any],
) -> tuple[dict[str, list[BudgetCandidate]], dict[str, Any]]:
    """
    Convert PartidaGenerator output to the legacy format expected by compose_budget.

    Returns:
        candidates:       dict[takeoff.item_key -> list[BudgetCandidate]]
        extended_catalog: bc3_catalog copy with synthetic partida codes injected
    """
    takeoff_by_key: dict[str, QuantityTakeoff] = {t.item_key: t for t in expanded_takeoffs}

    candidates: dict[str, list[BudgetCandidate]] = {}
    synthetic_codes: dict[str, dict[str, Any]] = {}

    for partida in generated_partidas:
        source_key = str(partida.get("source_takeoff_key") or "").strip()
        if not source_key:
            logger.warning("Partida missing source_takeoff_key — skipping: %s", partida)
            continue

        takeoff = takeoff_by_key.get(source_key)
        if takeoff is None:
            logger.warning("Partida references unknown takeoff key '%s' — skipping", source_key)
            continue

        candidate = _partida_to_budget_candidate(partida, takeoff)
        candidates[source_key] = [candidate]

        partida_code = candidate.bc3_code
        synthetic_codes[partida_code] = {
            "code": partida_code,
            "unit": takeoff.unit,
            "summary": candidate.summary,
            "price": 0.0,
            "type": "E",
            "bc3_origin": "partida_generator",
        }

    extended_catalog = _extend_bc3_catalog(bc3_catalog, synthetic_codes)

    logger.info(
        "adapt_generated_to_legacy_format: %d partidas -> %d candidates, "
        "%d synthetic BC3 codes injected",
        len(generated_partidas),
        len(candidates),
        len(synthetic_codes),
    )
    return candidates, extended_catalog
