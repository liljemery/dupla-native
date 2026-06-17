"""
Budget composition layer for workbook-ready budget rows.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from collections import Counter
from typing import Any, Iterable, Mapping

logger = logging.getLogger("dupla.composer")

from core.schemas import (
    BudgetCandidate,
    BudgetChapter,
    BudgetLine,
    BudgetRow,
    ProjectContext,
    QuantityTakeoff,
)

from .chapter_rules import (
    ChapterSegment,
    build_budget_summary,
    chapter_path_for_takeoff,
    chapter_path_from_bc3_catalog,
    default_bc3_code_for_takeoff,
    select_strong_candidate,
)
from .waste_policy import apply_waste

def infer_source_discipline(takeoff: QuantityTakeoff, context: ProjectContext | None) -> str:
    if context and context.metadata:
        return str(context.metadata.get("discipline_id") or "architectural")
    return "architectural"
try:
    from pricing.construcosto_loader import ConstrucostoSnapshot, find_best_price
except ImportError:
    ConstrucostoSnapshot = None  # type: ignore[assignment,misc]
    find_best_price = None  # type: ignore[assignment]

DATA_START_ROW = 4

_QUANTITY_SOURCE_LABELS: dict[str, str] = {
    "plan_measurement": "Medido",
    "default_estimate": "Estimado (default)",
    "mixed_measurement": "Mezclado (plano + default)",
    "ratio_estimate": "Estimado (ratio)",
}


def _quantity_source_display(takeoff: QuantityTakeoff) -> str:
    """Human-readable quantity provenance for Excel (B2)."""
    meta = takeoff.trace.metadata
    inputs = takeoff.inputs
    raw = meta.get("quantity_source")
    if raw is None:
        raw = inputs.get("quantity_source")
    note = meta.get("quantity_source_note") or inputs.get("quantity_source_note")
    if raw is None or str(raw).strip() == "":
        if note:
            return str(note).strip()
        return ""
    key = str(raw).strip()
    label = _QUANTITY_SOURCE_LABELS.get(key, key.replace("_", " "))
    if key == "ratio_estimate" and note:
        return f"{label}: {str(note).strip()}"
    return label


def _bc3_catalog_code_set(bc3_catalog: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for item in bc3_catalog.get("items", []) or []:
        c = str(item.get("code", "") or "").strip()
        if c:
            codes.add(c)
    for key in bc3_catalog.get("concepts_by_code", {}) or {}:
        k = str(key).strip()
        if k:
            codes.add(k)
    return codes


def _normalize_unit_family(unit: str) -> str | None:
    """Coarse unit family for compatibility checks (construction quantities)."""
    u = (
        unit.lower()
        .strip()
        .replace(" ", "")
        .replace("²", "2")
        .replace("³", "3")
    )
    if u in ("m2", "m^2", "sqm", "mt2"):
        return "area"
    if u in ("m3", "m^3", "cbm", "mt3"):
        return "volume"
    if u in ("ml", "lm", "m.lineal", "metrolineal") or u == "m":
        return "length"
    if u in ("ud", "un", "unit", "u", "pz", "pza", "ea", "cj", "jgo", "juego", "par", "und"):
        return "count"
    if u in ("kg", "kgs", "kilogramo", "kilogramos"):
        return "mass"
    return None


def _catalog_unit_for_code(bc3_catalog: dict[str, Any], bc3_code: str) -> str:
    concepts = bc3_catalog.get("concepts_by_code") or {}
    row = concepts.get(bc3_code, {})
    u = str(row.get("unit", "") or "").strip()
    if u:
        return u
    for item in bc3_catalog.get("items", []) or []:
        if str(item.get("code", "")) == bc3_code:
            return str(item.get("unit", "") or "").strip()
    return ""


def _guard_budget_candidate(
    takeoff: QuantityTakeoff,
    candidate: BudgetCandidate | None,
    bc3_catalog: dict[str, Any] | None,
    context: ProjectContext | None,
) -> tuple[BudgetCandidate | None, str | None]:
    """
    Drop BC3 matches that cannot be verified against the catalog (hallucinated codes).

    Optional: ``context.metadata["budget_bc3_strict_units"]`` enforces coarse unit-family
    agreement between takeoff and catalog line.
    """
    if candidate is None or not bc3_catalog:
        return candidate, None

    codes = _bc3_catalog_code_set(bc3_catalog)
    if codes and candidate.bc3_code not in codes:
        return None, "bc3_code_missing_in_catalog"

    meta = context.metadata if context is not None else {}
    if meta.get("budget_bc3_strict_units"):
        fam_t = _normalize_unit_family(takeoff.unit)
        cat_u = _catalog_unit_for_code(bc3_catalog, candidate.bc3_code)
        fam_c = _normalize_unit_family(cat_u)
        if fam_t and fam_c and fam_t != fam_c:
            return None, "bc3_unit_family_mismatch"

    return candidate, None


def _bc3_fallback_price_label(concept: Mapping[str, Any] | None) -> str:
    """BC3 price fallback label (Problema 3B): use catalog file name when available."""
    origin = "catálogo"
    if concept is not None:
        origin = str(concept.get("bc3_origin") or "").strip() or "catálogo"
    return f"BC3 {origin} (fallback)"


def _line_bc3_origin(
    candidate: BudgetCandidate | None,
    bc3_catalog: dict[str, Any] | None,
    resolved_code: str,
) -> str:
    if candidate and getattr(candidate, "bc3_origin", None):
        o = str(candidate.bc3_origin).strip()
        if o:
            return o
    code = str((candidate.bc3_code if candidate else "") or resolved_code or "").strip()
    if not code or not bc3_catalog:
        return ""
    for it in bc3_catalog.get("items") or []:
        if str(it.get("code", "")).strip() == code:
            o = str(it.get("bc3_origin") or "").strip()
            if o:
                return o
    c = bc3_catalog.get("concepts_by_code", {}).get(code, {})
    return str(c.get("bc3_origin") or "").strip()


def _unit_family_compatible(takeoff_unit: str, candidate_unit: str | None) -> bool:
    """True when both units share the same coarse family (count/length/area/volume/mass)
    or either family cannot be determined."""
    if not candidate_unit:
        return True
    fam_t = _normalize_unit_family(takeoff_unit)
    fam_c = _normalize_unit_family(candidate_unit)
    if fam_t is None or fam_c is None:
        return True
    return fam_t == fam_c


def _extract_unit_price(
    candidate: BudgetCandidate | None,
    bc3_catalog: dict[str, Any] | None,
    *,
    fallback_bc3_code: str | None = None,
    construcosto_snapshot: Any | None = None,
    summary: str = "",
    unit: str = "",
) -> tuple[float | None, str]:
    """Resolve unit price: ConstruCosto (APU → materiales → equipos → mano de obra) then BC3; never BC3-first.

    Unit-family guard: a kg-takeoff (rebar) will not accept an m3-priced match
    (concrete) even when the summary text is fuzzy-similar — that previously
    drove the RD$3 billion rebar mispricing.
    """
    summary_s = (summary or "").strip()
    unit_s = (unit or "").strip()

    if construcosto_snapshot is not None and find_best_price is not None and summary_s:
        for sources, label in (
            (frozenset({"analisis"}), "ConstruCosto APU Punta Cana"),
            (frozenset({"materiales"}), "ConstruCosto Material Punta Cana"),
            (frozenset({"equipos"}), "ConstruCosto Equipo Punta Cana"),
            (frozenset({"mano_obra"}), "ConstruCosto Mano de obra Punta Cana"),
        ):
            match = find_best_price(
                construcosto_snapshot,
                summary_s,
                unit_s,
                allowed_sources=sources,
            )
            if match is not None and match.unit_price and match.unit_price > 0:
                matched_unit = getattr(match.entry, "unit", "") or ""
                if not _unit_family_compatible(unit_s, matched_unit):
                    logger.info(
                        "ConstruCosto (%s) match rejected for '%s' — unit family mismatch (%r vs %r)",
                        label,
                        summary_s[:60],
                        unit_s,
                        matched_unit,
                    )
                    continue
                logger.debug(
                    "ConstruCosto (%s) price for '%s': RD$%.2f (score=%.2f, matched='%s')",
                    label,
                    summary_s[:60],
                    match.unit_price,
                    match.score,
                    match.entry.description[:60],
                )
                return float(match.unit_price), label

    if candidate is not None and bc3_catalog and candidate.bc3_code:
        concept = bc3_catalog.get("concepts_by_code", {}).get(candidate.bc3_code, {})
        price = concept.get("price")
        if price and _unit_family_compatible(unit_s, str(concept.get("unit") or "")):
            try:
                p = float(price)
                if p > 0:
                    return p, _bc3_fallback_price_label(concept)
            except (TypeError, ValueError):
                pass

    if fallback_bc3_code and bc3_catalog:
        concept = bc3_catalog.get("concepts_by_code", {}).get(fallback_bc3_code, {})
        price = concept.get("price")
        if price and _unit_family_compatible(unit_s, str(concept.get("unit") or "")):
            try:
                p = float(price)
                if p > 0:
                    return p, _bc3_fallback_price_label(concept)
            except (TypeError, ValueError):
                pass

    return None, "PRECIO_PENDIENTE"


@dataclass
class _PreparedLine:
    takeoff: QuantityTakeoff
    chapter_path: list[ChapterSegment]
    summary: str
    candidate: BudgetCandidate | None
    bc3_guard_drop_reason: str | None = None


@dataclass
class _ChapterNode:
    chapter: BudgetChapter
    children: list[str] = field(default_factory=list)
    lines: list[BudgetLine] = field(default_factory=list)


def _derived_from_key(takeoff: QuantityTakeoff) -> str | None:
    value = takeoff.trace.metadata.get("derived_from")
    if value is None:
        value = takeoff.inputs.get("derived_from")
    return str(value) if value else None


def _takeoff_prefix(item_key: str) -> str:
    return item_key.rsplit(":", 1)[0] if ":" in item_key else item_key


def budget_filter_sets(takeoff_list: list[QuantityTakeoff]) -> tuple[set[str], set[str]]:
    derived_from_keys = {
        derived_from
        for takeoff in takeoff_list
        for derived_from in [_derived_from_key(takeoff)]
        if derived_from
    }
    concrete_volume_prefixes = {
        _takeoff_prefix(takeoff.item_key)
        for takeoff in takeoff_list
        if takeoff.item_type.lower().endswith("_concrete_volume")
    }
    return derived_from_keys, concrete_volume_prefixes


def _budget_inclusive_flag(context: ProjectContext | None) -> bool:
    if context is None:
        return True
    return bool(context.metadata.get("budget_inclusive", True))


def takeoff_budget_eligibility(
    takeoff: QuantityTakeoff,
    *,
    derived_from_keys: set[str],
    concrete_volume_prefixes: set[str],
    budget_inclusive: bool = True,
    allowed_item_types: set[str] | None = None,
) -> tuple[bool, str]:
    """Whether this takeoff becomes a budget line, and a short reason if not."""
    item_type = takeoff.item_type.lower()

    if takeoff.unit.lower() == "flag":
        return False, "unit_flag"

    if item_type == "pres_reference_line":
        return True, ""

    if allowed_item_types is not None and item_type not in allowed_item_types:
        return False, "discipline_filter"

    always_skip = {
        "wall_gross_area",
    }
    if not budget_inclusive:
        always_skip = always_skip | {"structural_area"}

    if item_type in always_skip:
        return False, "type_excluded"

    if takeoff.item_key in derived_from_keys and item_type != "wall_net_area":
        return False, "derived_child"

    if item_type.endswith("_volume") and not item_type.endswith("_concrete_volume"):
        if _takeoff_prefix(takeoff.item_key) in concrete_volume_prefixes:
            return False, "duplicate_non_concrete_volume"

    if item_type.startswith(("beam_", "column_", "slab_")):
        ok = any(
            token in item_type
            for token in (
                "concrete_volume", "volume", "area",
                "formwork_area_hint", "reinforcement_kg",
                "count", "length",
            )
        )
        return (True, "") if ok else (False, "structural_subtype_excluded")

    if item_type.startswith("footing_"):
        ok = any(
            token in item_type
            for token in (
                "concrete_volume", "volume", "area",
                "formwork_area_hint", "reinforcement_kg",
                "count", "length",
            )
        )
        return (True, "") if ok else (False, "footing_subtype_excluded")

    if item_type.startswith("structural_"):
        return True, ""

    if item_type in {"stair_count", "fixture_count", "kitchen_count", "kitchen_area"}:
        return True, ""

    if item_type.startswith("wall_"):
        material_hint = str(takeoff.inputs.get("material_hint") or "").lower()
        if material_hint == "masonry" and item_type in {"wall_volume", "wall_length"}:
            return False, "masonry_wall_budgeted_by_area"
        allowed = {
            "wall_net_area",
            "wall_volume",
            "wall_waterproofing",
            "wall_finish_paint",
            "wall_finish_plaster",
            "wall_finish_tile",
            "wall_length",
            "wall_area",
        }
        ok = item_type in allowed
        return (True, "") if ok else (False, "wall_subtype_excluded")

    if item_type.startswith("floor_"):
        ok = item_type in {
            "floor_area", "floor_finish", "floor_waterproofing",
            "floor_screed", "floor_finish_tile",
        }
        return (True, "") if ok else (False, "floor_subtype_excluded")

    if item_type.startswith("ceiling_"):
        ok = item_type in {
            "ceiling_area", "ceiling_finish_paint", "ceiling_finish_plaster",
        }
        return (True, "") if ok else (False, "ceiling_subtype_excluded")

    if item_type.startswith("door_"):
        return True, ""

    if item_type.startswith("window_"):
        return True, ""

    if item_type.startswith("wet_area_"):
        return True, ""

    return True, ""


def _budgetable_takeoff(
    takeoff: QuantityTakeoff,
    *,
    derived_from_keys: set[str],
    concrete_volume_prefixes: set[str],
    budget_inclusive: bool = True,
    allowed_item_types: set[str] | None = None,
) -> bool:
    ok, _reason = takeoff_budget_eligibility(
        takeoff,
        derived_from_keys=derived_from_keys,
        concrete_volume_prefixes=concrete_volume_prefixes,
        budget_inclusive=budget_inclusive,
        allowed_item_types=allowed_item_types,
    )
    return ok


def build_budget_takeoff_diagnostics(
    context: ProjectContext,
    takeoffs: Iterable[QuantityTakeoff],
    *,
    derived_from_keys: set[str],
    concrete_volume_prefixes: set[str],
) -> dict[str, Any]:
    inclusive = _budget_inclusive_flag(context)
    takeoff_list = list(takeoffs)
    budgetable = 0
    reasons: Counter[str] = Counter()
    types_excluded: Counter[str] = Counter()
    for takeoff in takeoff_list:
        ok, reason = takeoff_budget_eligibility(
            takeoff,
            derived_from_keys=derived_from_keys,
            concrete_volume_prefixes=concrete_volume_prefixes,
            budget_inclusive=inclusive,
        )
        if ok:
            budgetable += 1
        else:
            reasons[reason] += 1
            types_excluded[takeoff.item_type] += 1
    return {
        "takeoffs_total": len(takeoff_list),
        "takeoffs_budgetable": budgetable,
        "takeoffs_excluded": len(takeoff_list) - budgetable,
        "budget_inclusive": inclusive,
        "excluded_by_reason": dict(reasons),
        "excluded_top_item_types": dict(types_excluded.most_common(25)),
    }


def _sort_key(prepared: _PreparedLine) -> tuple[Any, ...]:
    return (
        tuple(segment.code for segment in prepared.chapter_path),
        prepared.summary.lower(),
        prepared.takeoff.item_key,
    )


def _ensure_chapter_path(
    chapter_nodes: dict[str, _ChapterNode],
    chapter_lookup: list[BudgetChapter],
    path: list[ChapterSegment],
) -> str:
    parent_id = "ROOT"
    titles_so_far: list[str] = []
    for level, segment in enumerate(path, start=1):
        titles_so_far.append(segment.title)
        chapter_id = f"DUP-CH-{segment.code}"
        if chapter_id not in chapter_nodes:
            chapter = BudgetChapter(
                chapter_id=chapter_id,
                code=chapter_id,
                title=segment.title,
                level=level,
                parent_id=None if parent_id == "ROOT" else parent_id,
                path=list(titles_so_far),
            )
            chapter_nodes[chapter_id] = _ChapterNode(chapter=chapter)
            chapter_lookup.append(chapter)
            if parent_id != "ROOT":
                parent = chapter_nodes[parent_id]
                if chapter_id not in parent.children:
                    parent.children.append(chapter_id)
                if chapter_id not in parent.chapter.child_ids:
                    parent.chapter.child_ids.append(chapter_id)
        parent_id = chapter_id
    return parent_id


def _sum_formula(amount_rows: list[int]) -> str:
    if not amount_rows:
        return "=0"
    refs = ",".join(f"G{row_number}" for row_number in amount_rows)
    return f"=SUM({refs})"


def _flatten_chapters(
    chapter_nodes: dict[str, _ChapterNode],
    node_id: str,
    rows: list[BudgetRow],
) -> int | None:
    node = chapter_nodes[node_id]
    node.children.sort()
    node.lines.sort(key=lambda line: (line.summary.lower(), line.code, line.takeoff_key))

    chapter_row = BudgetRow(
        row_type="chapter",
        code=node.chapter.code,
        nat="Capítulo",
        unit="",
        summary=node.chapter.title,
        chapter_id=node.chapter.chapter_id,
        parent_chapter_id=node.chapter.parent_id,
        level=node.chapter.level,
        metadata={"path": list(node.chapter.path)},
    )
    rows.append(chapter_row)
    chapter_row_index = len(rows) - 1

    subtotal_source_indices: list[int] = []

    for line in node.lines:
        row = BudgetRow(
            row_type="line",
            code=line.code,
            nat=line.nat,
            unit=line.unit,
            summary=line.summary,
            quantity=line.quantity,
            unit_price=line.unit_price,
            amount=line.amount_formula,
            chapter_id=line.chapter_id,
            parent_chapter_id=node.chapter.parent_id,
            level=node.chapter.level,
            takeoff_key=line.takeoff_key,
            source_refs=list(line.source_refs),
            assumptions=list(line.assumptions),
            metadata=dict(line.metadata),
        )
        rows.append(row)
        subtotal_source_indices.append(len(rows) - 1)

    for child_id in node.children:
        child_subtotal_index = _flatten_chapters(chapter_nodes, child_id, rows)
        if child_subtotal_index is not None:
            subtotal_source_indices.append(child_subtotal_index)

    subtotal_row = BudgetRow(
        row_type="subtotal",
        code="",
        nat="Subtotal/Cierre de capítulo",
        unit="",
        summary=f"Subtotal {node.chapter.title}",
        quantity=1,
        unit_price=None,
        amount=None,
        chapter_id=node.chapter.chapter_id,
        parent_chapter_id=node.chapter.parent_id,
        level=node.chapter.level,
        metadata={
            "path": list(node.chapter.path),
            "source_row_indices": list(subtotal_source_indices),
            "chapter_code": node.chapter.code,
        },
    )
    rows.append(subtotal_row)
    subtotal_row_index = len(rows) - 1
    chapter_row.metadata["subtotal_row_index"] = subtotal_row_index
    return subtotal_row_index


def _finalize_formulas(
    chapters: list[BudgetChapter],
    lines: list[BudgetLine],
    rows: list[BudgetRow],
) -> None:
    line_map = {line.line_id: line for line in lines}

    for index, row in enumerate(rows, start=DATA_START_ROW):
        row.excel_row = index

    for row in rows:
        if row.row_type == "line":
            row.amount = f"=ROUND(E{row.excel_row}*F{row.excel_row},2)"
            line_id = str(row.metadata.get("line_id", ""))
            if line_id in line_map:
                line_map[line_id].amount_formula = str(row.amount)
                line_map[line_id].metadata["excel_row"] = row.excel_row
            continue

        if row.row_type == "subtotal":
            source_row_indices = list(row.metadata.get("source_row_indices", []))
            source_excel_rows = [
                rows[source_index].excel_row
                for source_index in source_row_indices
                if 0 <= source_index < len(rows) and rows[source_index].excel_row is not None
            ]
            row.quantity = 1
            row.unit_price = _sum_formula(source_excel_rows)
            row.amount = f"=ROUND(E{row.excel_row}*F{row.excel_row},2)"
            row.metadata["source_excel_rows"] = source_excel_rows
            continue

        subtotal_row_index = row.metadata.get("subtotal_row_index")
        if row.row_type == "chapter" and isinstance(subtotal_row_index, int):
            subtotal_excel_row = rows[subtotal_row_index].excel_row
            row.quantity = f"=E{subtotal_excel_row}"
            row.unit_price = f"=F{subtotal_excel_row}"
            row.amount = f"=G{subtotal_excel_row}"

    for chapter in chapters:
        chapter.line_keys = sorted(set(chapter.line_keys))


def compose_budget_rows(
    context: ProjectContext,
    takeoffs: Iterable[QuantityTakeoff],
    candidates_by_takeoff: dict[str, list[BudgetCandidate]],
    *,
    bc3_catalog: dict[str, Any] | None = None,
    construcosto_snapshot: Any | None = None,
    apu_matcher: Any | None = None,
) -> tuple[list[BudgetChapter], list[BudgetLine], list[BudgetRow]]:
    takeoff_list = list(takeoffs)
    derived_from_keys, concrete_volume_prefixes = budget_filter_sets(takeoff_list)
    inclusive = _budget_inclusive_flag(context)

    raw_allowed = context.metadata.get("allowed_item_types") if context.metadata else None
    allowed_item_types: set[str] | None = set(raw_allowed) if raw_allowed else None

    prepared_lines: list[_PreparedLine] = []
    for takeoff in takeoff_list:
        if not _budgetable_takeoff(
            takeoff,
            derived_from_keys=derived_from_keys,
            concrete_volume_prefixes=concrete_volume_prefixes,
            budget_inclusive=inclusive,
            allowed_item_types=allowed_item_types,
        ):
            continue

        strong_candidate = select_strong_candidate(
            takeoff,
            candidates_by_takeoff.get(takeoff.item_key, []),
        )
        strong_candidate, guard_reason = _guard_budget_candidate(
            takeoff,
            strong_candidate,
            bc3_catalog,
            context,
        )

        meta = context.metadata or {}
        if strong_candidate is not None:
            effective_bc3 = strong_candidate.bc3_code.strip()
        else:
            fb = default_bc3_code_for_takeoff(takeoff)
            effective_bc3 = fb.strip() if fb else ""

        chapter_path = chapter_path_for_takeoff(takeoff)
        if (
            bc3_catalog
            and meta.get("use_bc3_catalog_chapters")
            and effective_bc3
        ):
            alt_path = chapter_path_from_bc3_catalog(bc3_catalog, effective_bc3)
            if alt_path:
                chapter_path = alt_path

        # --- Prepend Building Block and Level ---
        prefix_segments: list[ChapterSegment] = []
        if context.building_block:
            block_code = f"BLQ-{context.building_block.replace(' ', '_')}"
            prefix_segments.append(ChapterSegment(block_code, context.building_block))
            if context.level_id:
                level_code = f"{block_code}-LVL-{context.level_id.replace(' ', '_')}"
                prefix_segments.append(ChapterSegment(level_code, context.level_id))
        elif context.level_id:
            level_code = f"LVL-{context.level_id.replace(' ', '_')}"
            prefix_segments.append(ChapterSegment(level_code, context.level_id))

        if prefix_segments:
            base_prefix = prefix_segments[-1].code
            adjusted_path = [
                ChapterSegment(f"{base_prefix}-{seg.code}", seg.title)
                for seg in chapter_path
            ]
            chapter_path = prefix_segments + adjusted_path

        prepared_lines.append(
            _PreparedLine(
                takeoff=takeoff,
                chapter_path=chapter_path,
                summary=build_budget_summary(takeoff, strong_candidate),
                candidate=strong_candidate,
                bc3_guard_drop_reason=guard_reason,
            )
        )

    prepared_lines.sort(key=_sort_key)

    chapter_nodes: dict[str, _ChapterNode] = {
        "ROOT": _ChapterNode(
            chapter=BudgetChapter(
                chapter_id="ROOT",
                code="ROOT",
                title=context.project_name or context.project_id or "PRESUPUESTO",
                level=0,
            )
        )
    }
    chapters: list[BudgetChapter] = []
    lines: list[BudgetLine] = []
    internal_code_counter = 1

    for line_index, prepared in enumerate(prepared_lines, start=1):
        leaf_chapter_id = _ensure_chapter_path(chapter_nodes, chapters, prepared.chapter_path)
        chapter_nodes[leaf_chapter_id].chapter.line_keys.append(prepared.takeoff.item_key)

        deterministic_bc3_code: str | None = None
        if prepared.candidate is not None:
            line_code = prepared.candidate.bc3_code.strip()
        else:
            deterministic_bc3_code = default_bc3_code_for_takeoff(prepared.takeoff)
            if deterministic_bc3_code:
                line_code = deterministic_bc3_code
            else:
                line_code = f"DUP-{internal_code_counter:04d}"
                internal_code_counter += 1

        line_metadata: dict[str, Any] = {
            "item_type": prepared.takeoff.item_type,
            "level_id": prepared.takeoff.level_id,
            "line_id": f"BLINE-{line_index:04d}",
            "chapter_path": [segment.title for segment in prepared.chapter_path],
            "chapter_codes": [segment.code for segment in prepared.chapter_path],
            "source_discipline": infer_source_discipline(prepared.takeoff, context),
            "candidate_summary": prepared.candidate.summary if prepared.candidate else None,
            "candidate_rationale": prepared.candidate.rationale if prepared.candidate else None,
            "candidate_source": prepared.candidate.source if prepared.candidate else None,
            "trace_metadata": dict(prepared.takeoff.trace.metadata),
            "requiere_revision": bool(getattr(prepared.takeoff, "requiere_revision", False)),
            "confidence": float(getattr(prepared.takeoff, "confidence", 1.0)),
        }
        if prepared.bc3_guard_drop_reason:
            line_metadata["bc3_guard_drop_reason"] = prepared.bc3_guard_drop_reason

        # --- Constructor APU layer ----------------------------------------
        # When a constructor APUMatcher is available, price the line against a
        # matched APU (its code + component decomposition); fall back to
        # _extract_unit_price (BC3 / ConstruCosto) when there is no hit.
        apu_match: Any | None = None
        if apu_matcher is not None:
            try:
                apu_match = apu_matcher.match(prepared.takeoff)
            except Exception:
                logger.warning(
                    "APUMatcher.match failed for %s", prepared.takeoff.item_key, exc_info=True
                )
                apu_match = None

        resolved_price: float | None
        price_source: str
        source_type: str

        if apu_match is not None and not _unit_family_compatible(
            prepared.takeoff.unit, getattr(apu_match, "unit", "") or ""
        ):
            logger.info(
                "APU match rejected for %s — unit family mismatch (takeoff=%r apu=%r)",
                prepared.takeoff.item_key,
                prepared.takeoff.unit,
                getattr(apu_match, "unit", ""),
            )
            apu_match = None

        if apu_match is not None:
            line_code = str(apu_match.code).strip() or line_code
            deterministic_bc3_code = line_code
            resolved_price = float(apu_match.unit_price_total)
            if apu_match.source and "ConstruCosto" in apu_match.source:
                price_source = apu_match.source
                source_type = "construcosto"
            else:
                price_source = f"Constructor APU ({apu_match.code})"
                source_type = "constructor_apu"
            line_metadata["apu_code"] = apu_match.code
            line_metadata["apu_description"] = apu_match.description
            line_metadata["apu_unit"] = apu_match.unit
            line_metadata["apu_components"] = [
                {
                    "description": c.description,
                    "quantity": c.quantity,
                    "unit": c.unit,
                    "unit_price": c.unit_price,
                    "subtotal": c.subtotal,
                    "component_type": c.component_type,
                }
                for c in apu_match.components
            ]
        else:
            resolved_price, price_source = _extract_unit_price(
                prepared.candidate,
                bc3_catalog,
                fallback_bc3_code=deterministic_bc3_code,
                construcosto_snapshot=construcosto_snapshot,
                summary=prepared.summary,
                unit=prepared.takeoff.unit,
            )
            source_type = "bc3_catalog"

        line_metadata["price_source"] = price_source
        line_metadata["source_type"] = source_type
        # Currency provenance. The constructor xlsx (constructor_apu) is USD per
        # the office; BC3 / ConstruCosto fallbacks may be a different currency
        # (e.g. RD$). Flag those so a mixed-currency budget is visible instead of
        # silently summed. No automatic conversion is applied here.
        primary_currency = (os.getenv("DUPLA_PRICING_CURRENCY") or "USD").strip() or "USD"
        if source_type == "constructor_apu":
            line_metadata["price_currency"] = primary_currency
        elif resolved_price is not None:
            line_metadata["price_currency"] = "?"
            line_metadata["price_currency_uncertain"] = True
        else:
            line_metadata["price_currency"] = None
        prepared.takeoff.trace.metadata["source_type"] = source_type
        line_metadata["quantity_source_display"] = _quantity_source_display(prepared.takeoff)
        line_metadata["bc3_origin"] = _line_bc3_origin(
            prepared.candidate, bc3_catalog or {}, line_code
        )

        apply_waste_flag = bool(meta.get("apply_waste_policy", True))
        waste_overrides = meta.get("waste_policy_overrides") if isinstance(meta.get("waste_policy_overrides"), dict) else None
        quantity_neta = float(prepared.takeoff.quantity)
        if apply_waste_flag:
            line_quantity, waste_fraction, waste_note = apply_waste(
                quantity_neta,
                prepared.takeoff.item_type,
                overrides=waste_overrides,
            )
        else:
            line_quantity, waste_fraction, waste_note = quantity_neta, 0.0, ""
        if waste_fraction > 0.0:
            line_metadata["quantity_neta"] = quantity_neta
            line_metadata["waste_fraction"] = waste_fraction
            line_metadata["waste_formula_note"] = waste_note

        budget_line = BudgetLine(
            line_id=f"BLINE-{line_index:04d}",
            takeoff_key=prepared.takeoff.item_key,
            chapter_id=leaf_chapter_id,
            code=line_code,
            nat="Partida",
            unit=prepared.takeoff.unit,
            summary=prepared.summary,
            quantity=line_quantity,
            unit_price=resolved_price,
            candidate_code=(
                apu_match.code
                if apu_match is not None
                else (prepared.candidate.bc3_code if prepared.candidate else deterministic_bc3_code)
            ),
            candidate_score=prepared.candidate.score if prepared.candidate else None,
            source_refs=list(prepared.takeoff.source_refs),
            assumptions=list(prepared.takeoff.assumptions),
            metadata=line_metadata,
        )
        lines.append(budget_line)
        chapter_nodes[leaf_chapter_id].lines.append(budget_line)

    chapter_nodes["ROOT"].children = sorted(
        chapter_id
        for chapter_id, node in chapter_nodes.items()
        if chapter_id != "ROOT" and node.chapter.parent_id is None
    )

    rows: list[BudgetRow] = []
    for child_id in chapter_nodes["ROOT"].children:
        _flatten_chapters(chapter_nodes, child_id, rows)

    _finalize_formulas(chapters, lines, rows)
    return chapters, lines, rows


def compose_budget(
    context: ProjectContext,
    takeoffs: Iterable[QuantityTakeoff],
    candidates_by_takeoff: dict[str, list[BudgetCandidate]],
    *,
    bc3_catalog: dict[str, Any] | None = None,
    construcosto_snapshot: Any | None = None,
    apu_matcher: Any | None = None,
) -> dict[str, Any]:
    takeoff_list = list(takeoffs)
    derived_from_keys, concrete_volume_prefixes = budget_filter_sets(takeoff_list)
    diagnostics = build_budget_takeoff_diagnostics(
        context,
        takeoff_list,
        derived_from_keys=derived_from_keys,
        concrete_volume_prefixes=concrete_volume_prefixes,
    )
    logger.info(
        "Budget diagnostics: %d total takeoffs, %d budgetable, %d excluded",
        diagnostics["takeoffs_total"],
        diagnostics["takeoffs_budgetable"],
        diagnostics["takeoffs_excluded"],
    )
    if diagnostics["excluded_by_reason"]:
        logger.debug("Exclusion reasons: %s", diagnostics["excluded_by_reason"])

    chapters, lines, rows = compose_budget_rows(
        context, takeoff_list, candidates_by_takeoff,
        bc3_catalog=bc3_catalog,
        construcosto_snapshot=construcosto_snapshot,
        apu_matcher=apu_matcher,
    )
    apu_lines = sum(1 for line in lines if line.metadata.get("source_type") == "constructor_apu")
    logger.info(
        "Budget composed: %d chapters, %d lines (%d via constructor APU), %d rows",
        len(chapters), len(lines), apu_lines, len(rows),
    )
    primary_currency = (os.getenv("DUPLA_PRICING_CURRENCY") or "USD").strip() or "USD"
    uncertain_lines = sum(1 for line in lines if line.metadata.get("price_currency_uncertain"))
    if uncertain_lines:
        logger.warning(
            "Currency check: %d/%d priced lines came from BC3/ConstruCosto fallback "
            "(currency unverified). Constructor xlsx is treated as %s — verify before summing totals.",
            uncertain_lines, len(lines), primary_currency,
        )
    payload: dict[str, Any] = {
        "project_context": context.to_dict(),
        "chapters": [chapter.to_dict() for chapter in chapters],
        "lines": [line.to_dict() for line in lines],
        "rows": [row.to_dict() for row in rows],
        "budget_diagnostics": diagnostics,
        "currency_summary": {
            "primary_currency": primary_currency,
            "lines_total": len(lines),
            "lines_currency_uncertain": uncertain_lines,
        },
    }
    if context.metadata.get("run_budget_validation"):
        try:
            from validation.budget_validator import run_budget_validation

            payload["budget_validation"] = run_budget_validation(
                lines,
                takeoff_list,
                bc3_catalog=bc3_catalog,
                context=context,
            ).to_dict()
        except Exception:
            logger.exception("run_budget_validation failed")
    return payload
