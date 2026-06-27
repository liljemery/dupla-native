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
    3.5 ESTIMATED                    analog APU / historical family estimate
                                     when catalogs have no direct price.
    4. PENDING                       nothing found anywhere and estimation
                                     cannot be produced.

Both sources are Dominican pesos (DOP), so there is no currency mixing.
Every resolution carries its provenance for traceability.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Mapping

from .relational import RelationalPricingStore
from .crosswalk import CrosswalkMatcher

logger = logging.getLogger("dupla.pricing.resolver")


@dataclass
class PriceResolution:
    unit_price: float | None
    currency: str
    source: str               # relational_apu | excluded | construcosto | estimated | pending
    apu_code: str | None = None
    rule_id: str | None = None
    matched_description: str | None = None
    score: float | None = None
    estimated: bool = False
    estimate_basis: str | None = None
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
            "estimated": self.estimated,
            "estimate_basis": self.estimate_basis,
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


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", str(text or ""))
        if unicodedata.category(ch) != "Mn"
    )


def _norm_text(text: Any) -> str:
    s = _strip_accents(str(text or "")).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_STOP_TOKENS = {
    "de", "del", "en", "la", "el", "los", "las", "con", "para", "por",
    "y", "o", "al", "un", "una", "m", "m2", "m3", "ml", "ud", "kg",
    "unidad", "unidades", "partida", "presupuesto",
}


def _tokens(text: Any) -> set[str]:
    return {
        tok for tok in _norm_text(text).split()
        if len(tok) > 1 and tok not in _STOP_TOKENS and not tok.isdigit()
    }


def _unit_family(unit: str | None) -> str | None:
    u = (
        str(unit or "")
        .lower()
        .strip()
        .replace(" ", "")
        .replace("²", "2")
        .replace("³", "3")
        .replace("â²", "2")
        .replace("â³", "3")
        .replace("Â²", "2")
        .replace("Â³", "3")
    )
    if u in {"m2", "m^2", "sqm", "mt2"}:
        return "area"
    if u in {"m3", "m^3", "cbm", "mt3"}:
        return "volume"
    if u in {"ml", "lm", "m.lineal", "metrolineal", "m"}:
        return "length"
    if u in {"ud", "un", "unit", "u", "und", "pz", "pza", "ea", "cj", "jgo", "juego", "par"}:
        return "count"
    if u in {"kg", "kgs", "kilogramo", "kilogramos"}:
        return "mass"
    return None


def _unit_family_compatible(takeoff_unit: str, candidate_unit: str | None) -> bool:
    fam_t = _unit_family(takeoff_unit)
    fam_c = _unit_family(candidate_unit)
    if fam_t is None or fam_c is None:
        return True
    return fam_t == fam_c


def _chapter_hint(item_type: str, inputs: Mapping[str, Any]) -> str | None:
    explicit = str(inputs.get("chapter_hint") or inputs.get("discipline") or "").strip()
    if explicit:
        return _norm_text(explicit)
    item = item_type.lower()
    if item.startswith(("column_", "beam_", "slab_", "footing_", "structural_")):
        return "estructura concreto acero formaleta"
    if item.startswith(("wall_", "floor_", "ceiling_", "door_", "window_", "kitchen_", "stair_")):
        return "arquitectura albanileria acabados carpinteria"
    if item.startswith(("fixture_", "wet_area_", "plumbing_")):
        return "sanitario plomeria"
    if item.startswith(("electrical_", "outlet_", "switch_", "luminaire_")):
        return "electrico"
    return None


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
                if not _unit_family_compatible(unit, apu.unidad):
                    logger.info(
                        "Crosswalk APU %s rejected for %s: unit family mismatch (%r vs %r)",
                        apu.codigo_apu,
                        item_type,
                        unit,
                        apu.unidad,
                    )
                else:
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
                matched_unit = getattr(match.entry, "unit", "") or ""
                if _unit_family_compatible(unit, matched_unit):
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
                            "construcosto_unit": matched_unit,
                            "query": query,
                        },
                    )
                logger.info(
                    "ConstruCosto match rejected for %s: unit family mismatch (%r vs %r)",
                    item_type,
                    unit,
                    matched_unit,
                )

        estimate = self._estimate_price(item_type, inputs, unit=unit, description=description)
        if estimate is not None:
            estimate.rule_id = cw.rule_id
            return estimate

        # 4) nothing
        return PriceResolution(
            unit_price=None, currency=self.currency, source="pending",
            rule_id=cw.rule_id,
            traceability={"strategy": "none", "crosswalk_kind": cw.kind},
        )

    def _estimate_price(
        self,
        item_type: str,
        inputs: Mapping[str, Any] | None = None,
        *,
        unit: str = "",
        description: str | None = None,
    ) -> PriceResolution | None:
        """Estimate a missing unit price from same-family historical APUs."""
        inputs = inputs or {}
        query = description or _takeoff_text(item_type, inputs)
        query_tokens = _tokens(f"{query} {_humanize_item_type(item_type)}")
        wanted_family = _unit_family(unit)

        raw_index = (os.getenv("DUPLA_PRICE_ESTIMATION_INFLATION_INDEX") or "1.0").strip()
        try:
            inflation_index = max(float(raw_index), 0.0)
        except ValueError:
            inflation_index = 1.0

        priced_apus = [
            apu for apu in self.relational.apus.values()
            if apu.total_declarado and float(apu.total_declarado) > 0
            and _unit_family_compatible(unit, apu.unidad)
        ]
        if wanted_family is not None:
            priced_apus = [apu for apu in priced_apus if _unit_family(apu.unidad) == wanted_family]
        if not priced_apus:
            return None

        hint = _chapter_hint(item_type, inputs)
        scored: list[tuple[float, Any]] = []
        for apu in priced_apus:
            text = f"{apu.descripcion} {apu.capitulo} {apu.unidad}"
            apu_tokens = _tokens(text)
            overlap = len(query_tokens & apu_tokens)
            denominator = max(min(len(query_tokens), len(apu_tokens)), 1)
            score = overlap / denominator
            if hint and any(tok in _norm_text(text) for tok in hint.split()):
                score += 0.15
            scored.append((score, apu))

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_apu = scored[0]

        # Robust family median first: it bounds the analog so a single outlier
        # APU (e.g. a RD$126,934 "camara desarenadora" fuzzy-matched to a door)
        # can never become the estimate and inflate the budget total.
        #
        # The relational catalog alone is too sparse for some unit families
        # (the "count"/UD family is 7 heavy civil-works APUs whose median is the
        # RD$126,934 chamber). Enrich the pool with ConstruCosto complete APUs of
        # the same family so the median reflects real doors/windows/fixtures.
        family_prices: list[float] = [float(apu.total_declarado) for apu in priced_apus]
        if self.construcosto is not None:
            for entry in getattr(self.construcosto, "entries", []) or []:
                if entry.source != "analisis":
                    continue
                price = float(entry.unit_price or 0.0)
                if price <= 0:
                    continue
                entry_family = _unit_family(entry.unit)
                if wanted_family is not None:
                    if entry_family != wanted_family:
                        continue
                elif not _unit_family_compatible(unit, entry.unit):
                    continue
                family_prices.append(price)
        family_prices.sort()
        if not family_prices:
            return None
        midpoint = len(family_prices) // 2
        if len(family_prices) % 2:
            family_median = family_prices[midpoint]
        else:
            family_median = (family_prices[midpoint - 1] + family_prices[midpoint]) / 2.0

        raw_mult = (os.getenv("DUPLA_PRICE_ESTIMATION_OUTLIER_MULT") or "4.0").strip()
        try:
            outlier_mult = float(raw_mult)
        except ValueError:
            outlier_mult = 4.0
        if outlier_mult <= 0:
            outlier_mult = 4.0
        upper_bound = family_median * outlier_mult
        lower_bound = family_median / outlier_mult if family_median > 0 else 0.0

        analog_price = float(best_apu.total_declarado)
        analog_in_band = lower_bound <= analog_price <= upper_bound

        if best_score >= 0.20 and analog_in_band:
            estimated_price = round(analog_price * inflation_index, 4)
            return PriceResolution(
                unit_price=estimated_price,
                currency=self.currency,
                source="estimated",
                apu_code=best_apu.codigo_apu,
                matched_description=best_apu.descripcion,
                score=round(float(best_score), 3),
                estimated=True,
                estimate_basis=(
                    f"ESTIMADO (no es precio de catalogo); "
                    f"analog_apu:{best_apu.codigo_apu}; "
                    f"unit_family:{wanted_family or 'unknown'}; "
                    f"inflation_index:{inflation_index:g}"
                ),
                traceability={
                    "strategy": "estimated_analog_apu",
                    "query": query,
                    "analog_apu": best_apu.codigo_apu,
                    "analog_unit": best_apu.unidad,
                    "analog_chapter": best_apu.capitulo,
                    "analog_price": analog_price,
                    "family_median": family_median,
                    "inflation_index": inflation_index,
                },
            )

        # No trustworthy analog (weak match or outlier price): fall back to the
        # family median. This is the reasonable estimate the user asked for —
        # clearly flagged as NOT a catalog price, never the runaway value.
        rejected_outlier = best_score >= 0.20 and not analog_in_band
        estimate_reason = (
            "analog_rejected_outlier" if rejected_outlier else "weak_analog_score"
        )
        return PriceResolution(
            unit_price=round(family_median * inflation_index, 4),
            currency=self.currency,
            source="estimated",
            matched_description=f"Mediana historica familia {wanted_family or unit or 'unidad'}",
            score=round(float(best_score), 3),
            estimated=True,
            estimate_basis=(
                f"ESTIMADO (no es precio de catalogo); "
                f"historical_family_median:{wanted_family or 'unknown'}; "
                f"motivo:{estimate_reason}; "
                f"sample_size:{len(family_prices)}; "
                f"inflation_index:{inflation_index:g}"
            ),
            traceability={
                "strategy": "estimated_historical_family_median",
                "query": query,
                "unit_family": wanted_family,
                "sample_size": len(family_prices),
                "family_median": family_median,
                "estimate_reason": estimate_reason,
                "rejected_analog_apu": best_apu.codigo_apu if rejected_outlier else None,
                "rejected_analog_price": analog_price if rejected_outlier else None,
                "inflation_index": inflation_index,
            },
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
