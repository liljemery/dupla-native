"""
P0.2 — Price resolver with explicit fallback chain.

Resolution order for a takeoff (first hit wins):

    1. CROSSWALK -> RELATIONAL APU   (processor/data: precios_relacional / the
       curated constructor workbook). Deterministic, all-inclusive unit price.
    2. EXCLUDE                       crosswalk says the cost is already bundled
                                     in another APU -> price 0 (no double count).
    3. CONSTRUCOSTO fallback         ONLY when the relational catalog has no price
                                     (UNMATCHED / no rule): fuzzy lookup in
                                     processor/data/construcosto/*.csv (RD$ Punta
                                     Cana). Fills MEP / carpentry the curated file
                                     lacks.
    4. PENDING                       nothing found anywhere.

Both sources are Dominican pesos (DOP), so there is no currency mixing.
Every resolution carries its provenance for traceability.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from .relational import RelationalPricingStore
from .crosswalk import CrosswalkMatcher

logger = logging.getLogger("dupla.pricing.resolver")


@dataclass
class PriceResolution:
    unit_price: float | None
    currency: str
    source: str               # relational_apu | excluded | construcosto | pending
    apu_code: str | None = None
    rule_id: str | None = None
    matched_description: str | None = None
    score: float | None = None
    traceability: dict[str, Any] = field(default_factory=dict)

    @property
    def priced(self) -> bool:
        return self.unit_price is not None and self.unit_price > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_price": self.unit_price,
            "currency": self.currency,
            "source": self.source,
            "apu_code": self.apu_code,
            "rule_id": self.rule_id,
            "matched_description": self.matched_description,
            "score": self.score,
            "traceability": dict(self.traceability),
        }


def _humanize_item_type(item_type: str) -> str:
    return item_type.replace("_", " ")


def _takeoff_text(item_type: str, inputs: Mapping[str, Any]) -> str:
    """Best textual description of a takeoff, for the ConstruCosto fuzzy lookup."""
    for key in ("takeoff_description", "fixture_label", "structural_label",
                "door_label", "window_label", "type_label"):
        val = str(inputs.get(key) or "").strip()
        if val:
            return val
    parts: list[str] = []
    for key in ("fixture_type", "element_type", "type_hint", "kind", "material_hint", "discipline"):
        val = str(inputs.get(key) or "").strip()
        if val and val.lower() not in {"other", "unknown", "none"}:
            parts.append(val.replace("_", " "))
    parts.append(_humanize_item_type(item_type))
    return " ".join(dict.fromkeys(parts))  # de-duped, order-preserving


class PriceResolver:
    def __init__(
        self,
        relational: RelationalPricingStore,
        crosswalk: CrosswalkMatcher,
        *,
        construcosto_snapshot: Any | None = None,
        construcosto_min_score: float = 0.45,
        currency: str | None = None,
    ):
        self.relational = relational
        self.crosswalk = crosswalk
        self.construcosto = construcosto_snapshot
        self.construcosto_min_score = construcosto_min_score
        self.currency = currency or relational.metadata.get("currency") or "DOP"
        # P0.3 reprecio: when on, fully-linked APUs are repriced from
        # components x resource prices (so updating a resource reprices the
        # budget); partially-linked APUs keep the curated stated total.
        self.reprice_from_components = (
            (os.getenv("DUPLA_REPRICE_FROM_COMPONENTS") or "").strip().lower()
            in {"1", "true", "yes", "on"}
        )

    def resolve(
        self,
        item_type: str,
        inputs: Mapping[str, Any] | None = None,
        *,
        unit: str = "",
        description: str | None = None,
    ) -> PriceResolution:
        inputs = inputs or {}

        # 1) crosswalk -> relational APU
        cw = self.crosswalk.match(item_type, inputs)
        if cw.kind == "apu":
            apu = self.relational.apus.get(cw.target or "")
            if apu is not None and apu.total_declarado:
                unit_price = float(apu.total_declarado)
                priced_by = "stated_total"
                if self.reprice_from_components and apu.repriceable:
                    recomputed = self.relational.reprice(apu.codigo_apu)
                    if recomputed > 0:
                        unit_price = recomputed
                        priced_by = "reprice_components"
                return PriceResolution(
                    unit_price=unit_price,
                    currency=self.currency,
                    source="relational_apu",
                    apu_code=apu.codigo_apu,
                    rule_id=cw.rule_id,
                    matched_description=apu.descripcion,
                    traceability={
                        "strategy": "crosswalk->relational",
                        "apu_unit": apu.unidad,
                        "priced_by": priced_by,
                        "repriceable": apu.repriceable,
                    },
                )
            # crosswalk pointed at an APU we cannot price -> fall through to construcosto
            logger.debug("Crosswalk APU %s not priceable in relational store; falling back", cw.target)

        # 2) excluded -> intentionally not charged (bundled in another APU)
        if cw.kind == "exclude":
            return PriceResolution(
                unit_price=0.0, currency=self.currency, source="excluded",
                rule_id=cw.rule_id,
                traceability={"strategy": "crosswalk_exclude", "reason": "bundled_in_apu"},
            )

        # 3) ConstruCosto fallback — ONLY because the relational catalog had no price
        if self.construcosto is not None:
            try:
                from .construcosto_loader import find_best_price
                query = description or _takeoff_text(item_type, inputs)
                match = find_best_price(
                    self.construcosto, query, unit, min_score=self.construcosto_min_score,
                )
            except Exception:
                logger.warning("ConstruCosto lookup failed for %s", item_type, exc_info=True)
                match = None
            if match is not None and match.unit_price and match.unit_price > 0:
                return PriceResolution(
                    unit_price=float(match.unit_price),
                    currency=self.currency,
                    source="construcosto",
                    matched_description=match.entry.description,
                    score=round(float(match.score), 3),
                    traceability={
                        "strategy": "construcosto_fallback",
                        "construcosto_code": match.entry.code,
                        "construcosto_source": match.entry.source,
                        "query": query,
                    },
                )

        # 4) nothing
        return PriceResolution(
            unit_price=None, currency=self.currency, source="pending",
            rule_id=cw.rule_id,
            traceability={"strategy": "none", "crosswalk_kind": cw.kind},
        )


def build_default_resolver(
    *,
    excel_path: Any | None = None,
    construcosto_dir: Any | None = None,
    currency: str | None = None,
) -> PriceResolver:
    """Wire relational + crosswalk + construcosto from the bundled data files."""
    from core import paths
    from .relational import build_from_excel
    from .crosswalk import default_matcher

    src = excel_path or paths.pricing_excel_path()
    relational = build_from_excel(src, currency=currency)
    crosswalk = default_matcher(valid_apu_codes=set(relational.apus.keys()))

    construcosto = None
    try:
        from .construcosto_loader import load_construcosto_snapshot
        snap = load_construcosto_snapshot(construcosto_dir)
        if snap.count > 0:
            construcosto = snap
    except Exception:
        logger.warning("ConstruCosto snapshot unavailable", exc_info=True)

    return PriceResolver(relational, crosswalk, construcosto_snapshot=construcosto, currency=currency)
