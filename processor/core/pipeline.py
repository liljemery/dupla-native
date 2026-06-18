"""
Pipeline helpers for the active APS/JSON-first architecture.
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from agents.classifier_agent import match_takeoffs_to_bc3
from agents.quantifier_agent import quantify_inventory
from budget.composer import compose_budget
from core.inventory_builder import build_level_inventory
from core.quality_engine import evaluate_semantic_quality
from core.schemas import (
    BudgetCandidate,
    LevelInventory,
    ProjectContext,
    QuantityTakeoff,
    QuantityTrace,
    level_inventory_from_dict,
)
def infer_source_discipline(takeoff: QuantityTakeoff, context: ProjectContext | None) -> str:
    if context and context.metadata:
        return str(context.metadata.get("discipline_id") or "architectural")
    return "architectural"
from core.semantic_adapter import adapt_semantic_to_inventory
from core.semantic_enrichment import enrich_semantics
from core.stage_cache import _STATS
from knowledge.bc3_embeddings import load_or_build_embeddings
from knowledge.pres_expansion import synthetic_takeoffs_from_pres
from knowledge.training_data import extract_training_pairs
from pricing.schemas import PricingStore
from pricing.excel_price_loader import load_or_cache_constructor_pricing
try:
    from pricing.construcosto_loader import load_construcosto_snapshot
except ImportError:
    def load_construcosto_snapshot() -> Any:
        class DummySnapshot:
            count = 0
        return DummySnapshot()
from processors.bc3_parser import parse_bc3
from processors.json_processor import process_autodesk_json
from rules_engine import RulesEngine, default_rules_engine

logger = logging.getLogger("dupla.pipeline")


def _runner_discipline_canonical(context: ProjectContext | None) -> str | None:
    """Disciplina de corrida (arquitectonica|estructural|electrica|sanitaria) desde metadata, o None."""
    if context is None or not context.metadata:
        return None
    if not str(context.metadata.get("discipline_id") or "").strip():
        return None
    probe = QuantityTakeoff(
        item_key="__discipline_probe__",
        item_type="wall_net_area",
        unit="m2",
        quantity=0.0,
        formula="",
        trace=QuantityTrace(),
    )
    return infer_source_discipline(probe, context)


def _stamp_takeoffs_source_discipline(
    takeoffs: Iterable[QuantityTakeoff],
    label: str | None,
) -> None:
    if not label:
        return
    for takeoff in takeoffs:
        takeoff.trace.metadata["source_discipline"] = label


def merge_pres_template_takeoffs(
    levels: list[LevelInventory],
    takeoffs: list[QuantityTakeoff],
    training_pairs: list[Any] | None,
    *,
    pres_template_takeoffs: bool = False,
    max_per_level: int = 250,
    fallback_unmatched: bool = True,
) -> list[QuantityTakeoff]:
    if not pres_template_takeoffs or not training_pairs:
        return takeoffs
    extra = synthetic_takeoffs_from_pres(
        levels,
        training_pairs,
        max_per_level=max_per_level,
        fallback_unmatched=fallback_unmatched,
    )
    seen = {t.item_key for t in takeoffs}
    merged = list(takeoffs)
    for item in extra:
        if item.item_key not in seen:
            merged.append(item)
            seen.add(item.item_key)
    return merged


async def _match_or_generate(
    expanded_takeoffs: list[QuantityTakeoff],
    bc3_catalog: dict[str, Any],
    *,
    embedding_index: Any | None = None,
    training_pairs: list[Any] | None = None,
    project_discipline_id: str | None = None,
) -> tuple[dict[str, list[BudgetCandidate]], dict[str, Any]]:
    """
    Try PartidaGenerator (GPT-4o generates project-specific partidas), fall back to
    legacy match_takeoffs_to_bc3 on any failure.

    Returns (candidates_dict, bc3_catalog_to_use). On the generator path the catalog
    is an extended copy with synthetic partida codes so _guard_budget_candidate passes.
    On the fallback path the original bc3_catalog is returned unchanged.
    """
    import os as _os  # local import — avoids shadowing the module-level namespace

    api_keys = (_os.getenv("DUPLA_OPENAI_KEYS") or "").strip()
    api_key = (_os.getenv("OPENAI_API_KEY") or "").strip()
    if api_keys or api_key:
        try:
            from agents.partida_generator import PartidaGenerator
            from agents.partida_adapter import adapt_generated_to_legacy_format

            generator = PartidaGenerator()
            generated = await generator.generate(
                expanded_takeoffs,
                training_pairs=training_pairs,
                bc3_catalog=bc3_catalog,
            )
            if not generated:
                raise ValueError("PartidaGenerator returned empty result — using BC3 fallback")

            candidates, extended_catalog = adapt_generated_to_legacy_format(
                generated, expanded_takeoffs, bc3_catalog
            )
            logger.info("PartidaGenerator path: %d partidas generated", len(generated))
            return candidates, extended_catalog

        except Exception:
            logger.warning(
                "PartidaGenerator failed — falling back to BC3 matching", exc_info=True
            )
    else:
        logger.info("No OPENAI_API_KEY — skipping PartidaGenerator, using BC3 matching")

    candidates = await match_takeoffs_to_bc3(
        expanded_takeoffs,
        bc3_catalog,
        embedding_index=embedding_index,
        training_pairs=training_pairs,
        project_discipline_id=project_discipline_id,
    )
    return candidates, bc3_catalog


def _load_construcosto_if_available() -> Any:
    try:
        snapshot = load_construcosto_snapshot()
        if snapshot.count > 0:
            logger.info("ConstruCosto snapshot: %d entries loaded", snapshot.count)
            return snapshot
    except Exception:
        logger.debug("ConstruCosto snapshot not available", exc_info=True)
    return None


def _load_default_pricing_store(context: ProjectContext | None) -> PricingStore | None:
    """Load the constructor PricingStore for APU-based budget pricing.

    Looks for an explicit ``metadata['pricing_excel']`` path, else the bundled
    ``data/Lista de precios-analisis-MO.xlsx``. Returns None when unavailable so
    the budget falls back to BC3 / ConstruCosto pricing.
    """
    metadata = context.metadata if context is not None else {}
    if metadata.get("pricing_excel_disabled"):
        return None

    explicit_path = str(metadata.get("pricing_excel") or "").strip()
    default_path = Path(__file__).resolve().parent.parent / "data" / "Lista de precios-analisis-MO.xlsx"
    pricing_path = Path(explicit_path) if explicit_path else default_path
    if not pricing_path.exists():
        logger.info("No constructor pricing Excel at %s — APU pricing disabled", pricing_path)
        return None

    project_id = context.project_id if context and context.project_id else "default_project"
    try:
        store = load_or_cache_constructor_pricing(pricing_path, project_id=project_id)
        logger.info(
            "Constructor PricingStore loaded from %s (materials=%d, labor=%d, apus=%d)",
            pricing_path, len(store.materials), len(store.labor), len(store.apus),
        )
        return store
    except Exception:
        logger.warning("Failed to load constructor pricing from %s", pricing_path, exc_info=True)
        return None


_PRICE_RESOLVER_CACHE: dict[Any, Any] = {}


def _build_price_resolver(construcosto_snapshot: Any | None) -> Any | None:
    """Build (and cache) the PriceResolver: crosswalk -> relational APU ->
    ConstruCosto fallback. Returns None to fall back to the legacy APUMatcher
    path. Disable with DUPLA_USE_PRICE_RESOLVER=0."""
    import os

    if (os.getenv("DUPLA_USE_PRICE_RESOLVER") or "1").strip().lower() in {"0", "false", "no", "off"}:
        return None
    try:
        from core import paths

        src = paths.pricing_excel_path()
        if src is None:
            return None
        key = (str(src), src.stat().st_mtime)
        cached = _PRICE_RESOLVER_CACHE.get(key)
        if cached is not None:
            return cached
        from pricing.resolver import build_default_resolver

        resolver = build_default_resolver()
        _PRICE_RESOLVER_CACHE.clear()
        _PRICE_RESOLVER_CACHE[key] = resolver
        logger.info(
            "PriceResolver wired: %d APUs, %d resources, construcosto=%d entries",
            len(resolver.relational.apus),
            len(resolver.relational.resources),
            resolver.construcosto.count if resolver.construcosto else 0,
        )
        return resolver
    except Exception:
        logger.warning("PriceResolver unavailable; using legacy pricing path", exc_info=True)
        return None


def build_final_budget(
    context: ProjectContext,
    takeoffs: Iterable[QuantityTakeoff],
    candidates_by_takeoff: dict[str, list[BudgetCandidate]],
    *,
    bc3_catalog: dict[str, Any] | None = None,
    construcosto_snapshot: Any | None = None,
    pricing_store: PricingStore | None = None,
    apu_matcher: Any | None = None,
) -> dict[str, Any]:
    takeoff_list = list(takeoffs)
    lines = []

    # Constructor pricing: load the default PricingStore when the caller did
    # not supply one (looks for data/Lista de precios-analisis-MO.xlsx).
    if pricing_store is None:
        pricing_store = _load_default_pricing_store(context)

    for takeoff in takeoff_list:
        candidates = candidates_by_takeoff.get(takeoff.item_key, [])
        lines.append(
            {
                "takeoff": takeoff.to_dict(),
                "candidates": [candidate.to_dict() for candidate in candidates],
            }
        )

    # Lazy-build the APUMatcher from the PricingStore so compose_budget can
    # price lines against constructor APUs before falling back to BC3.
    if apu_matcher is None and pricing_store is not None:
        try:
            from pricing.apu_matcher import APUMatcher

            apu_matcher = APUMatcher(pricing_store, construcosto_snapshot=construcosto_snapshot)
            logger.info(
                "Constructor APUMatcher built (materials=%d, labor=%d, apus=%d)",
                len(pricing_store.materials), len(pricing_store.labor), len(pricing_store.apus),
            )
        except Exception:
            logger.warning("Failed to build APUMatcher; continuing without it", exc_info=True)
            apu_matcher = None

    price_resolver = _build_price_resolver(construcosto_snapshot)
    composed = compose_budget(
        context, takeoff_list, candidates_by_takeoff,
        bc3_catalog=bc3_catalog,
        construcosto_snapshot=construcosto_snapshot,
        apu_matcher=apu_matcher,
        price_resolver=price_resolver,
    )
    composed["budget_lines"] = lines
    composed["takeoffs"] = [takeoff.to_dict() for takeoff in takeoff_list]
    composed["candidates_by_takeoff"] = {
        key: [candidate.to_dict() for candidate in value]
        for key, value in candidates_by_takeoff.items()
    }
    return composed


async def build_budget_from_inventory(
    context: ProjectContext,
    levels: list[LevelInventory],
    bc3_catalog: dict[str, Any],
    rules_engine: RulesEngine | None = None,
    *,
    embedding_index: Any | None = None,
    training_pairs: list[Any] | None = None,
    pricing_store: PricingStore | None = None,
    apu_matcher: Any | None = None,
) -> dict[str, Any]:
    engine = rules_engine or default_rules_engine()
    project_discipline = _runner_discipline_canonical(context)
    base_takeoffs = quantify_inventory(levels, runner_source_discipline=project_discipline)
    expanded_takeoffs = engine.apply(base_takeoffs)
    expanded_takeoffs = merge_pres_template_takeoffs(
        levels,
        expanded_takeoffs,
        training_pairs,
        pres_template_takeoffs=bool(context.metadata.get("pres_template_takeoffs", False)),
        max_per_level=int(context.metadata.get("pres_max_per_level", 250)),
        fallback_unmatched=bool(context.metadata.get("pres_fallback_unmatched", True)),
    )
    _assert_unique_takeoff_keys(expanded_takeoffs)
    _stamp_takeoffs_source_discipline(expanded_takeoffs, project_discipline)
    candidates, bc3_catalog_for_budget = await _match_or_generate(
        expanded_takeoffs,
        bc3_catalog,
        embedding_index=embedding_index,
        training_pairs=training_pairs,
        project_discipline_id=project_discipline,
    )
    snapshot = _load_construcosto_if_available()
    return build_final_budget(
        context, expanded_takeoffs, candidates,
        bc3_catalog=bc3_catalog_for_budget,
        construcosto_snapshot=snapshot,
        pricing_store=pricing_store,
        apu_matcher=apu_matcher,
    )


def build_expanded_takeoffs_from_inventory(
    levels: list[LevelInventory],
    rules_engine: RulesEngine | None = None,
    *,
    runner_source_discipline: str | None = None,
) -> tuple[list[QuantityTakeoff], list[QuantityTakeoff]]:
    """
    Quantify inventory deterministically, then expand base takeoffs through the
    configured rule engine.
    """
    engine = rules_engine or default_rules_engine()
    base_takeoffs = quantify_inventory(levels, runner_source_discipline=runner_source_discipline)
    expanded_takeoffs = engine.apply(base_takeoffs)
    return base_takeoffs, expanded_takeoffs


def _coerce_vision_payloads(
    vision_payloads: Iterable[LevelInventory | Mapping[str, Any]] | LevelInventory | Mapping[str, Any] | None,
) -> list[LevelInventory | Mapping[str, Any]]:
    if vision_payloads is None:
        return []
    if isinstance(vision_payloads, LevelInventory):
        return [vision_payloads]
    if isinstance(vision_payloads, Mapping):
        return [vision_payloads]
    return list(vision_payloads)


_LEVEL_LABEL_PATTERN = re.compile(
    r"^(n[+\-]?\d|nivel|level|piso|planta|sotano|techo|cubierta|azotea|mezzanine|pb\b|s\d|n\d)",
    re.IGNORECASE,
)


def _is_acceptable_level_label(text: str) -> bool:
    if not text or len(text) > 40:
        return False
    return _LEVEL_LABEL_PATTERN.match(text) is not None


def _extract_level_markers(cad_facts: dict[str, Any]) -> list[str]:
    """Pull unique, label-like level names from inventory_hints.level_markers.

    Mirrors the filter applied in agents.vision_agent._resolve_vision_level_name:
    rejects free-form CAD annotations that get accidentally captured as markers
    (e.g. "El nivel de desplante sera de 0.80m..."). Without this filter the
    CAD-only fallback used to spawn one fake level per annotation, producing N×
    duplicate takeoffs and tripping _assert_unique_takeoff_keys.
    """
    markers = cad_facts.get("inventory_hints", {}).get("level_markers", [])
    seen: set[str] = set()
    unique: list[str] = []
    for marker in markers:
        text = str(marker.get("content", "") if isinstance(marker, Mapping) else marker).strip()
        if not _is_acceptable_level_label(text):
            continue
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _unique_strings(*groups: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for item in group:
            value = str(item or "").strip()
            if value and value not in seen:
                seen.add(value)
                merged.append(value)
    return merged


def _norm_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _round_key(value: Any, digits: int = 3) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _slug_key(parts: Iterable[Any], *, fallback: str) -> str:
    raw = "-".join(str(part) for part in parts if part is not None and str(part) != "")
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return slug or fallback


def _source_refs_for_entity(entity: Any) -> list[str]:
    refs = list(getattr(entity, "source_refs", []) or [])
    source_image = getattr(entity, "source_image", None)
    if source_image:
        refs.append(f"vision:{source_image}")
    return _unique_strings(refs)


def _entity_page_key(entity: Any) -> str:
    refs = _source_refs_for_entity(entity)
    for ref in refs:
        if ref.startswith("vision:"):
            parts = ref.split(":")
            if len(parts) >= 2 and parts[1]:
                return parts[1]
    source_image = getattr(entity, "source_image", None)
    if source_image:
        return str(source_image)
    return str(getattr(entity, "level_id", None) or "__global__")


def _entity_inputs(entity: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    inputs = getattr(entity, "inputs", {}) or {}
    if not isinstance(inputs, dict):
        inputs = {}
    raw = inputs.get("raw") if isinstance(inputs.get("raw"), dict) else {}
    return inputs, raw


def _entity_label(entity: Any, *input_keys: str) -> str:
    inputs, raw = _entity_inputs(entity)
    for key in input_keys:
        value = inputs.get(key) or raw.get(key)
        if str(value or "").strip():
            return _norm_key(value)
    for attr_name in ("type_hint", "fixture_type", "element_type", "id"):
        value = getattr(entity, attr_name, None)
        if str(value or "").strip():
            return _norm_key(value)
    return ""


def _first_not_none(values: Iterable[Any]) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _all_refs(entities: Iterable[Any]) -> list[str]:
    return _unique_strings(*(_source_refs_for_entity(entity) for entity in entities))


def _merge_entity_strings(entities: Iterable[Any], attr_name: str) -> list[str]:
    return _unique_strings(*(getattr(entity, attr_name, []) or [] for entity in entities))


def _merge_entity_inputs(entities: Iterable[Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    raw_values: list[dict[str, Any]] = []
    for entity in entities:
        inputs, raw = _entity_inputs(entity)
        for key, value in inputs.items():
            if key == "raw" and isinstance(value, dict):
                raw_values.append(value)
            elif key not in merged and value is not None:
                merged[key] = value
        if raw:
            raw_values.append(raw)
    if raw_values:
        raw_merged: dict[str, Any] = {}
        for raw in raw_values:
            for key, value in raw.items():
                if key not in raw_merged and value is not None:
                    raw_merged[key] = value
        if raw_merged:
            merged["raw"] = raw_merged
    return merged


def _wall_typology(wall: Any) -> str:
    inputs, raw = _entity_inputs(wall)
    return _norm_key(
        inputs.get("wall_typology")
        or raw.get("wall_typology")
        or raw.get("tipo")
        or raw.get("type_label")
        or getattr(wall, "wall_system", None)
        or getattr(wall, "id", None)
    )


def _wall_material(wall: Any) -> str:
    inputs, raw = _entity_inputs(wall)
    return _norm_key(
        getattr(wall, "material_hint", None)
        or inputs.get("material")
        or inputs.get("material_hint")
        or raw.get("original_material_code")
        or raw.get("material")
    )


def _wall_group_key(wall: Any) -> tuple[str, str, float | None]:
    return (_wall_typology(wall), _wall_material(wall), _round_key(getattr(wall, "thickness_m", None)))


def _dedupe_vision_walls(walls: list[Any], *, level_id: str) -> list[dict[str, Any]]:
    """Bucket vision walls by SLUG of the typology key (not raw tuple) so that
    distinct typology tuples whose slug collides do not produce two payloads
    with the same `vision-wall-<slug>` id.
    """
    groups: dict[str, list[Any]] = defaultdict(list)
    slug_key: dict[str, tuple[str, str, float | None]] = {}
    for wall in walls:
        key = _wall_group_key(wall)
        slug = _slug_key(key, fallback="unknown")
        groups[slug].append(wall)
        slug_key.setdefault(slug, key)

    merged: list[dict[str, Any]] = []
    for slug, group in groups.items():
        key = slug_key[slug]
        page_entities: dict[str, dict[str, Any]] = defaultdict(dict)
        for index, wall in enumerate(group):
            page = _entity_page_key(wall)
            entity_id = str(getattr(wall, "id", None) or f"wall-{index}")
            current = page_entities[page].get(entity_id)
            if current is None:
                page_entities[page][entity_id] = wall
                continue
            current_measure = float(getattr(current, "length_m", 0) or getattr(current, "area_m2", 0) or 0)
            next_measure = float(getattr(wall, "length_m", 0) or getattr(wall, "area_m2", 0) or 0)
            if next_measure > current_measure:
                page_entities[page][entity_id] = wall

        page_totals: dict[str, dict[str, float]] = {}
        page_representatives: dict[str, Any] = {}
        for page, entities_by_id in page_entities.items():
            entities = list(entities_by_id.values())
            page_totals[page] = {
                "length_m": sum(float(getattr(item, "length_m", 0) or 0) for item in entities),
                "area_m2": sum(float(getattr(item, "area_m2", 0) or 0) for item in entities),
            }
            page_representatives[page] = max(
                entities,
                key=lambda item: float(getattr(item, "length_m", 0) or getattr(item, "area_m2", 0) or 0),
            )

        best_page = max(
            page_totals,
            key=lambda page: (page_totals[page]["length_m"], page_totals[page]["area_m2"]),
        )
        representative = page_representatives[best_page]
        payload = representative.to_dict()
        payload.update(
            {
                "id": f"vision-wall-{slug}",
                "level_id": level_id,
                "source": "vision",
                "source_refs": _all_refs(group),
                "source_layers": _merge_entity_strings(group, "source_layers"),
                "assumptions": _unique_strings(
                    _merge_entity_strings(group, "assumptions"),
                    [
                        (
                            "Deduplicated repeated wall typology across vision pages; "
                            "kept the maximum per-page quantity to avoid cross-sheet double counting."
                        )
                    ]
                    if len(page_entities) > 1
                    else [],
                ),
                "conflict_notes": _merge_entity_strings(group, "conflict_notes"),
                "evidence": _merge_entity_strings(group, "evidence"),
                "inputs": _merge_entity_inputs(group),
                "length_m": page_totals[best_page]["length_m"] or getattr(representative, "length_m", None),
                "area_m2": page_totals[best_page]["area_m2"] or getattr(representative, "area_m2", None),
                "height_m": _first_not_none(getattr(wall, "height_m", None) for wall in group),
                "thickness_m": _first_not_none(getattr(wall, "thickness_m", None) for wall in group),
                "material_hint": _first_not_none(getattr(wall, "material_hint", None) for wall in group),
                "wall_system": _first_not_none(getattr(wall, "wall_system", None) for wall in group),
                "openings_count": max(int(getattr(wall, "openings_count", 0) or 0) for wall in group),
            }
        )
        payload["inputs"].setdefault("wall_typology", key[0] or payload["id"])
        merged.append(payload)
    return merged


def _dedupe_count_entities(
    entities: list[Any],
    *,
    key_fn: Any,
    id_prefix: str,
    level_id: str,
) -> list[dict[str, Any]]:
    """Group vision entities and produce one payload per logical group.

    Group by the SLUG of `key_fn(entity)` — not by the raw tuple — so that
    different tuples whose slug collides (e.g. ('v.1','beam') vs ('v 1','beam')
    both produce 'v-1-beam') still land in the same group instead of emitting
    two payloads with the same id and tripping `_assert_unique_takeoff_keys`.
    """
    groups: dict[str, list[Any]] = defaultdict(list)
    for entity in entities:
        slug = _slug_key(key_fn(entity), fallback="unknown")
        groups[slug].append(entity)

    merged: list[dict[str, Any]] = []
    for slug, group in groups.items():
        representative = max(group, key=lambda entity: int(getattr(entity, "count", 1) or 1))
        payload = representative.to_dict()
        payload.update(
            {
                "id": f"{id_prefix}-{slug}",
                "level_id": level_id,
                "source": "vision",
                "source_refs": _all_refs(group),
                "assumptions": _merge_entity_strings(group, "assumptions"),
                "conflict_notes": _merge_entity_strings(group, "conflict_notes"),
                "evidence": _merge_entity_strings(group, "evidence"),
                "inputs": _merge_entity_inputs(group),
                "count": max(int(getattr(entity, "count", 1) or 1) for entity in group),
            }
        )
        if hasattr(representative, "source_layers"):
            payload["source_layers"] = _merge_entity_strings(group, "source_layers")
        merged.append(payload)
    return merged


def _merged_level_name(cad_facts: dict[str, Any], levels: list[LevelInventory]) -> str:
    markers = _extract_level_markers(cad_facts)
    if len(markers) == 1:
        return markers[0]
    for level in levels:
        name = str(level.level_name or "").strip()
        if name and not re.search(r"(?:^|[_-])page[_-]?\d+|pdf[_-]?\d+", name, flags=re.IGNORECASE):
            return name
    return "level_01"


def _merge_vision_levels(
    cad_facts: dict[str, Any],
    levels: list[LevelInventory],
) -> LevelInventory:
    level_name = _merged_level_name(cad_facts, levels)
    level_id = "level_01"
    floor_areas = [float(level.floor_area_m2) for level in levels if level.floor_area_m2 is not None]
    ceiling_areas = [float(level.ceiling_area_m2) for level in levels if level.ceiling_area_m2 is not None]

    all_doors = [door for level in levels for door in level.doors]
    all_windows = [window for level in levels for window in level.windows]
    all_openings = [opening for level in levels for opening in level.openings]
    all_fixtures = [fixture for level in levels for fixture in level.fixtures]
    all_structural = [element for level in levels for element in level.structural_elements]
    all_wet_areas = [item for level in levels for item in level.wet_areas]
    all_kitchens = [item for level in levels for item in level.kitchens]
    all_stairs = [item for level in levels for item in level.stairs]

    payload = {
        "level_id": level_id,
        "level_name": level_name,
        "source": "vision",
        "source_image": None,
        "source_refs": _unique_strings(
            *(level.source_refs or [f"vision:{level.source_image}"] if level.source_image else level.source_refs for level in levels)
        ),
        "assumptions": _unique_strings(*(level.assumptions for level in levels)),
        "conflict_notes": _unique_strings(*(level.conflict_notes for level in levels)),
        "space_types": _unique_strings(*(level.space_types for level in levels)),
        "system_notes": _unique_strings(*(level.system_notes for level in levels)),
        "structural_notes": _unique_strings(*(level.structural_notes for level in levels)),
        "notes": _unique_strings(*(level.notes for level in levels)),
        "cad_hints": {},
        "inputs": {
            "merged_vision_pages": len(levels),
            "source_level_ids": [level.level_id for level in levels],
        },
        "floor_area_m2": max(floor_areas) if floor_areas else None,
        "ceiling_area_m2": max(ceiling_areas) if ceiling_areas else None,
        "walls": _dedupe_vision_walls(
            [wall for level in levels for wall in level.walls],
            level_id=level_id,
        ),
        "openings": _dedupe_count_entities(
            all_openings,
            key_fn=lambda opening: (
                _norm_key(getattr(opening, "opening_type", None)),
                _round_key(getattr(opening, "width_m", None)),
                _round_key(getattr(opening, "height_m", None)),
                _norm_key(getattr(opening, "wall_id", None)),
            ),
            id_prefix="vision-opening",
            level_id=level_id,
        ),
        "doors": _dedupe_count_entities(
            all_doors,
            key_fn=lambda door: (
                _norm_key(getattr(door, "id", None)),
                _entity_label(door, "door_label", "label"),
                _round_key(getattr(door, "width_m", None)),
                _round_key(getattr(door, "height_m", None)),
            ),
            id_prefix="vision-door",
            level_id=level_id,
        ),
        "windows": _dedupe_count_entities(
            all_windows,
            key_fn=lambda window: (
                _norm_key(getattr(window, "id", None)),
                _entity_label(window, "window_label", "label"),
                _round_key(getattr(window, "width_m", None)),
                _round_key(getattr(window, "height_m", None)),
            ),
            id_prefix="vision-window",
            level_id=level_id,
        ),
        "wet_areas": _dedupe_count_entities(
            all_wet_areas,
            key_fn=lambda wet_area: (
                _norm_key(getattr(wet_area, "kind", None)),
                _round_key(getattr(wet_area, "estimated_area_m2", None)),
            ),
            id_prefix="vision-wet-area",
            level_id=level_id,
        ),
        "kitchens": _dedupe_count_entities(
            all_kitchens,
            key_fn=lambda kitchen: (_round_key(getattr(kitchen, "estimated_area_m2", None)),),
            id_prefix="vision-kitchen",
            level_id=level_id,
        ),
        "stairs": _dedupe_count_entities(
            all_stairs,
            key_fn=lambda stair: (
                _round_key(getattr(stair, "width_m", None)),
                _round_key(getattr(stair, "elevation_change_m", None)),
            ),
            id_prefix="vision-stair",
            level_id=level_id,
        ),
        "fixtures": _dedupe_count_entities(
            all_fixtures,
            key_fn=lambda fixture: (
                _entity_label(fixture, "fixture_label", "label"),
                _norm_key(getattr(fixture, "fixture_type", None)),
                _norm_key(getattr(fixture, "location_hint", None)),
            ),
            id_prefix="vision-fixture",
            level_id=level_id,
        ),
        "structural_elements": _dedupe_count_entities(
            all_structural,
            key_fn=lambda element: (
                _entity_label(element, "structural_label", "notation", "label"),
                _norm_key(getattr(element, "element_type", None)),
            ),
            id_prefix="vision-structural",
            level_id=level_id,
        ),
    }
    return level_inventory_from_dict(payload, default_source="vision")


def _assert_hybrid_level_invariant(levels: list[LevelInventory], cad_facts: dict[str, Any]) -> None:
    markers = _extract_level_markers(cad_facts)
    if len(levels) > 1 and not markers:
        raise RuntimeError(
            "Hybrid inventory invariant violated: build_hybrid_inventory returned "
            f"{len(levels)} levels without CAD level markers. Vision pages must not become fake levels."
        )


def _assert_unique_takeoff_keys(takeoffs: Iterable[QuantityTakeoff]) -> None:
    counts = Counter(takeoff.item_key for takeoff in takeoffs)
    offenders = counts.most_common(5)
    offenders = [(key, count) for key, count in offenders if count > 1]
    if offenders:
        formatted = ", ".join(f"{key} x{count}" for key, count in offenders)
        raise RuntimeError(
            "Duplicate takeoff item_key detected before budget generation. "
            f"Top offenders: {formatted}"
        )


def _log_duplicate_takeoff_diagnostics(
    hybrid_inventory: list[LevelInventory],
    base_takeoffs: Iterable[QuantityTakeoff],
    expanded_takeoffs: Iterable[QuantityTakeoff],
    *,
    stage: str,
) -> None:
    """Log Counter-based duplicate snapshots around the failing assertion.

    Captures level_ids in hybrid_inventory plus the top duplicate item_keys at
    each pipeline stage (base, expanded, post-PRES). The signal here is what
    points at the actual source of duplication — relax nothing on its basis.
    """
    base_counts = Counter(t.item_key for t in base_takeoffs)
    expanded_counts = Counter(t.item_key for t in expanded_takeoffs)
    base_dups = [(k, c) for k, c in base_counts.most_common(5) if c > 1]
    expanded_dups = [(k, c) for k, c in expanded_counts.most_common(5) if c > 1]
    logger.info(
        "[probe %s] hybrid_levels=%d ids=%s base_dups=%d expanded_dups=%d",
        stage,
        len(hybrid_inventory),
        [level.level_id for level in hybrid_inventory],
        len(base_dups),
        len(expanded_dups),
    )
    if base_dups:
        logger.warning("[probe %s] base duplicates: %s", stage, base_dups)
    if expanded_dups:
        logger.warning("[probe %s] expanded duplicates: %s", stage, expanded_dups)


def _build_cad_only_levels(cad_facts: dict[str, Any]) -> list[LevelInventory]:
    """Always return exactly one LevelInventory.

    CAD facts are the merged drawing and cannot be split per level without
    per-level vision evidence: the CAD pipeline reports global aggregates
    (total length of every wall layer, total column count, …) not per-floor
    breakdowns. Spawning one level per marker therefore duplicated CAD-derived
    takeoffs N times and crashed _assert_unique_takeoff_keys.

    Naming: when _extract_level_markers returns exactly one label-like marker,
    we adopt it; otherwise default to "level_01".
    """
    markers = _extract_level_markers(cad_facts)
    if len(markers) == 1:
        level_name = markers[0]
    else:
        level_name = "level_01"
    levels = [
        build_level_inventory(cad_facts, None, level_id="level_01", level_name=level_name)
    ]
    _assert_hybrid_level_invariant(levels, cad_facts)
    return levels


def build_hybrid_inventory(
    cad_facts: dict[str, Any],
    vision_payloads: Iterable[LevelInventory | Mapping[str, Any]] | LevelInventory | Mapping[str, Any] | None,
) -> list[LevelInventory]:
    """
    Build merged hybrid inventories from normalized CAD facts and vision payloads.

    Each vision payload is normalized to a `LevelInventory`, then merged with the
    CAD-derived inventory via `build_level_inventory(...)`.
    Falls back to CAD-only when vision payloads are absent or ALL contain errors.
    """
    coerced_payloads = _coerce_vision_payloads(vision_payloads)
    if not coerced_payloads:
        logger.info("No vision payloads — building CAD-only inventory")
        return _build_cad_only_levels(cad_facts)

    error_count = 0
    vision_levels: list[LevelInventory] = []
    for index, payload in enumerate(coerced_payloads, start=1):
        if isinstance(payload, LevelInventory):
            vision_level = payload
        elif isinstance(payload, Mapping) and "error" in payload:
            error_count += 1
            logger.warning(
                "Vision payload %d contains error, skipping: %s",
                index, payload.get("error"),
            )
            continue
        else:
            payload_dict = dict(payload)
            payload_dict.setdefault("level_id", f"level_{index:02d}")
            payload_dict.setdefault("level_name", payload_dict["level_id"])
            vision_level = level_inventory_from_dict(payload_dict, default_source="vision")

        vision_levels.append(vision_level)

    if not vision_levels and cad_facts:
        logger.warning(
            "All %d vision payloads failed — falling back to CAD-only inventory",
            error_count,
        )
        return _build_cad_only_levels(cad_facts)

    if not vision_levels:
        logger.warning("All %d vision payloads failed and CAD facts are empty", error_count)
        return []

    merged_vision_level = _merge_vision_levels(cad_facts, vision_levels)
    hybrid_levels = [
        build_level_inventory(
            cad_facts,
            merged_vision_level,
            level_id=merged_vision_level.level_id,
            level_name=merged_vision_level.level_name,
        )
    ]
    _assert_hybrid_level_invariant(hybrid_levels, cad_facts)

    logger.info(
        "Hybrid inventory built: %d level(s) from %d vision payload(s), %d errors skipped",
        len(hybrid_levels),
        len(vision_levels),
        error_count,
    )
    return hybrid_levels


def build_takeoffs_from_sources(
    cad_facts: dict[str, Any],
    vision_payloads: Iterable[LevelInventory | Mapping[str, Any]] | LevelInventory | Mapping[str, Any] | None,
) -> tuple[list[LevelInventory], list[QuantityTakeoff]]:
    """
    Official hybrid Stage 2/3 path:
        normalized CAD facts + vision inventory -> hybrid inventory -> quantity takeoffs
    """
    hybrid_inventory = build_hybrid_inventory(cad_facts, vision_payloads)
    takeoffs = quantify_inventory(hybrid_inventory)
    _assert_unique_takeoff_keys(takeoffs)
    return hybrid_inventory, takeoffs


def build_expanded_takeoffs_from_sources(
    cad_facts: dict[str, Any],
    vision_payloads: Iterable[LevelInventory | Mapping[str, Any]] | LevelInventory | Mapping[str, Any] | None,
    rules_engine: RulesEngine | None = None,
) -> tuple[list[LevelInventory], list[QuantityTakeoff], list[QuantityTakeoff]]:
    hybrid_inventory = build_hybrid_inventory(cad_facts, vision_payloads)
    base_takeoffs, expanded_takeoffs = build_expanded_takeoffs_from_inventory(
        hybrid_inventory,
        rules_engine=rules_engine,
    )
    _assert_unique_takeoff_keys(expanded_takeoffs)
    return hybrid_inventory, base_takeoffs, expanded_takeoffs


async def build_budget_from_sources(
    context: ProjectContext,
    cad_facts: dict[str, Any],
    vision_payloads: Iterable[LevelInventory | Mapping[str, Any]] | LevelInventory | Mapping[str, Any] | None,
    bc3_catalog: dict[str, Any],
    rules_engine: RulesEngine | None = None,
    *,
    embedding_index: Any | None = None,
    training_pairs: list[Any] | None = None,
    pricing_store: PricingStore | None = None,
    apu_matcher: Any | None = None,
) -> dict[str, Any]:
    logger.info("build_budget_from_sources: starting hybrid inventory + takeoffs")
    build_hybrid_t0 = time.monotonic()
    hybrid_inventory = build_hybrid_inventory(cad_facts, vision_payloads)

    # --- Semantic layer + quality ---
    semantic_building_dict: dict[str, Any] | None = None
    quality_report_obj = None
    disc_id = (context.metadata or {}).get("discipline_id", "")
    enable_semantic = bool((context.metadata or {}).get("enable_semantic_layer", False))

    if enable_semantic and disc_id:
        logger.info("[semantic] Enriching %s semantics (%d levels)...", disc_id, len(hybrid_inventory))
        sem_building = enrich_semantics(
            project_id=context.project_id,
            project_name=context.project_name,
            discipline=disc_id,
            levels=hybrid_inventory,
        )
        semantic_building_dict = sem_building.to_dict()
        logger.info(
            "[semantic] Building: %d elements, avg confidence %.3f",
            len(sem_building.elements),
            sem_building.confidence_score,
        )

        quality_report_obj = evaluate_semantic_quality(sem_building)
        logger.info(
            "[quality] OK=%d WARNING=%d BLOCKED=%d",
            quality_report_obj.ok_count,
            quality_report_obj.warning_count,
            quality_report_obj.blocked_count,
        )

        if quality_report_obj.blocked_count > 0:
            hybrid_inventory = adapt_semantic_to_inventory(
                sem_building, quality_report_obj, hybrid_inventory,
            )
            logger.info(
                "[semantic] Adapted inventory: %d BLOCKED entities filtered out",
                quality_report_obj.blocked_count,
            )

    project_discipline = _runner_discipline_canonical(context)
    base_takeoffs, expanded_takeoffs = build_expanded_takeoffs_from_inventory(
        hybrid_inventory,
        rules_engine=rules_engine,
        runner_source_discipline=project_discipline,
    )
    logger.info(
        "Takeoffs: %d base -> %d expanded (rules applied)",
        len(base_takeoffs), len(expanded_takeoffs),
    )
    _log_duplicate_takeoff_diagnostics(
        hybrid_inventory, base_takeoffs, expanded_takeoffs, stage="pre-PRES",
    )
    _STATS.bump("build_hybrid_exp", seconds_saved_estimate=time.monotonic() - build_hybrid_t0)

    expanded_takeoffs = merge_pres_template_takeoffs(
        hybrid_inventory,
        expanded_takeoffs,
        training_pairs,
        pres_template_takeoffs=bool(context.metadata.get("pres_template_takeoffs", False)),
        max_per_level=int(context.metadata.get("pres_max_per_level", 250)),
        fallback_unmatched=bool(context.metadata.get("pres_fallback_unmatched", True)),
    )
    logger.info("After PRES merge: %d takeoffs", len(expanded_takeoffs))
    _log_duplicate_takeoff_diagnostics(
        hybrid_inventory, base_takeoffs, expanded_takeoffs, stage="post-PRES",
    )

    _assert_unique_takeoff_keys(expanded_takeoffs)
    _stamp_takeoffs_source_discipline(expanded_takeoffs, project_discipline)

    logger.info("Resolving candidates for %d takeoffs", len(expanded_takeoffs))
    candidates, bc3_catalog_for_budget = await _match_or_generate(
        expanded_takeoffs,
        bc3_catalog,
        embedding_index=embedding_index,
        training_pairs=training_pairs,
        project_discipline_id=project_discipline,
    )
    logger.info("Candidates resolved for %d takeoff keys", len(candidates))

    snapshot = _load_construcosto_if_available()
    budget = build_final_budget(
        context, expanded_takeoffs, candidates,
        bc3_catalog=bc3_catalog_for_budget,
        construcosto_snapshot=snapshot,
        pricing_store=pricing_store,
        apu_matcher=apu_matcher,
    )
    budget["hybrid_inventory"] = [level.to_dict() for level in hybrid_inventory]
    budget["base_takeoffs"] = [takeoff.to_dict() for takeoff in base_takeoffs]
    if semantic_building_dict is not None:
        budget["semantic_building"] = semantic_building_dict
    if quality_report_obj is not None:
        budget["quality_report"] = quality_report_obj.to_dict()

    logger.info(
        "Budget built: %d chapters, %d lines, %d rows",
        len(budget.get("chapters", [])),
        len(budget.get("lines", [])),
        len(budget.get("rows", [])),
    )
    return budget


def bootstrap_pipeline_inputs(context: ProjectContext) -> dict[str, Any]:
    """
    Load the reusable non-LLM inputs for the active pipeline.

    Vision/image analysis is intentionally kept outside this helper so it can be
    run independently or mocked in tests.
    """
    cad_facts = process_autodesk_json(context.source_json_path) if context.source_json_path else {}
    logger.info("CAD facts loaded: %d keys", len(cad_facts))

    bc3_catalog = parse_bc3(context.bc3_path) if context.bc3_path else {}
    logger.info("BC3 catalog: %d items", len(bc3_catalog.get("items", [])))

    embeddings = None
    if bc3_catalog.get("items"):
        try:
            embeddings = load_or_build_embeddings(bc3_catalog)
            logger.info("Embeddings built: %d vectors", len(getattr(embeddings, "metadata", [])))
        except Exception:
            logger.warning("Failed to build BC3 embeddings, continuing without them", exc_info=True)
            embeddings = None

    xlsx_path = context.metadata.get("xlsx_path") if context.metadata else None
    if not xlsx_path:
        default_xlsx = Path(__file__).resolve().parent.parent / "data" / "PRES.xlsx"
        if default_xlsx.exists():
            xlsx_path = str(default_xlsx)
    training_pairs: list[Any] = []
    if xlsx_path:
        try:
            training_pairs = extract_training_pairs(xlsx_path)
            logger.info("Training pairs loaded: %d from %s", len(training_pairs), xlsx_path)
        except Exception:
            logger.warning("Failed to load training pairs from %s", xlsx_path, exc_info=True)
            training_pairs = []

    construcosto = _load_construcosto_if_available()

    return {
        "project_context": context.to_dict(),
        "cad_facts": cad_facts,
        "bc3_catalog": bc3_catalog,
        "bc3_embeddings": embeddings,
        "training_pairs": training_pairs,
        "construcosto_snapshot": construcosto,
    }
