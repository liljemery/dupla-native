from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def _make_takeoff(item_type: str, unit: str, description: str = ""):
    from core.schemas import QuantityTakeoff, QuantityTrace

    inputs: dict = {}
    if description:
        inputs["takeoff_description"] = description
    return QuantityTakeoff(
        item_key=f"{item_type}-test",
        item_type=item_type,
        unit=unit,
        quantity=1.0,
        formula="",
        inputs=inputs,
        trace=QuantityTrace(),
    )


def _make_candidate(summary: str, source: str = "partida_generator"):
    from core.schemas import BudgetCandidate

    return BudgetCandidate(
        takeoff_key="dummy",
        bc3_code="01.001",
        summary=summary,
        unit="m2",
        score=1.0,
        rationale="",
        source=source,
    )


# --- Fix A: LLM summary preferred over CAD-derived takeoff_description --------

def test_build_summary_prefers_llm_over_generic_cad_label():
    from budget.chapter_rules import build_budget_summary

    takeoff = _make_takeoff(
        "wall_net_area",
        "m2",
        description="Muro de capa CAD 'a-wall'",
    )
    candidate = _make_candidate(
        "Muro de bloque de 6\" en fachada exterior nivel 1 — acabado pañete y pintura",
    )
    summary = build_budget_summary(takeoff, candidate)
    assert "capa CAD" not in summary
    assert "bloque" in summary or "fachada" in summary


def test_build_summary_keeps_specific_when_no_llm_candidate():
    from budget.chapter_rules import build_budget_summary

    takeoff = _make_takeoff(
        "wall_net_area",
        "m2",
        description="Muro tipo M-1, bloque 6\", espesor 15 cm, nivel 1",
    )
    summary = build_budget_summary(takeoff, None)
    assert "M-1" in summary


def test_build_summary_skips_llm_when_llm_also_generic():
    from budget.chapter_rules import build_budget_summary

    takeoff = _make_takeoff(
        "wall_net_area",
        "m2",
        description="Muro tipo M-1 bloque 8\" espesor 20cm",
    )
    candidate = _make_candidate("Muro de capa CAD 'json-wall-muros'")
    summary = build_budget_summary(takeoff, candidate)
    assert "M-1" in summary  # falls back to good takeoff_description


# --- Fix B: unit-family guard rejects cross-family price matches --------------

def test_unit_family_compatible_accepts_same_family():
    from budget.composer import _unit_family_compatible

    assert _unit_family_compatible("m3", "m3")
    assert _unit_family_compatible("m2", "m²")
    assert _unit_family_compatible("kg", "kgs")
    assert _unit_family_compatible("ud", "unit")


def test_unit_family_compatible_rejects_cross_family():
    from budget.composer import _unit_family_compatible

    # The rebar / concrete bug: kg-priced takeoff matched to m3 catalog.
    assert not _unit_family_compatible("kg", "m3")
    assert not _unit_family_compatible("m2", "m3")
    assert not _unit_family_compatible("m", "m2")
    assert not _unit_family_compatible("ud", "kg")


def test_unit_family_compatible_passes_when_unknown():
    from budget.composer import _unit_family_compatible

    # If the catalog unit cannot be parsed, do not block the match — log only.
    assert _unit_family_compatible("m3", "lote")
    assert _unit_family_compatible("custom_unit", "m3")
    assert _unit_family_compatible("m3", "")


# --- Fix C: pseudo-layer detection -------------------------------------------

def test_pseudo_element_layer_detects_acero_textos_dim():
    from core.inventory_builder import _is_pseudo_element_layer

    assert _is_pseudo_element_layer("json-beam-acero")
    assert _is_pseudo_element_layer("json-slab-textos losas")
    assert _is_pseudo_element_layer("dim-columnas")
    assert _is_pseudo_element_layer("cota-vigas")
    assert _is_pseudo_element_layer("xref1$0$muros")
    assert _is_pseudo_element_layer("hatch muros")
    assert _is_pseudo_element_layer("detalle-perfil")
    assert _is_pseudo_element_layer("ANNOBJ", "")


def test_pseudo_element_layer_passes_real_elements():
    from core.inventory_builder import _is_pseudo_element_layer

    assert not _is_pseudo_element_layer("json-beam-vigas")
    assert not _is_pseudo_element_layer("a-wall")
    assert not _is_pseudo_element_layer("muros")
    assert not _is_pseudo_element_layer("columnas")
    assert not _is_pseudo_element_layer("estructura-columnas")


# --- Fix D: composer propagates requiere_revision + confidence to metadata ----

def test_composer_propagates_revision_flag_to_line_metadata():
    from budget.composer import compose_budget_rows
    from core.schemas import ProjectContext, QuantityTakeoff, QuantityTrace

    takeoff = QuantityTakeoff(
        item_key="excav-1",
        item_type="excavation_volume",
        unit="m3",
        quantity=10.0,
        formula="area_m2 * depth_m",
        inputs={"depth_assumed": True, "takeoff_description": "Excavación cisterna 5x2x1m"},
        trace=QuantityTrace(),
        confidence=0.55,
        requiere_revision=True,
    )
    context = ProjectContext(project_id="P1", project_name="Test")
    _, lines, _ = compose_budget_rows(context, [takeoff], {})
    assert lines, "expected at least one budget line"
    line_meta = lines[0].metadata
    assert line_meta.get("requiere_revision") is True
    assert abs(line_meta.get("confidence") - 0.55) < 1e-6
