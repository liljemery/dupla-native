from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def test_price_resolver_estimates_unpriced_takeoff_from_same_unit_family():
    from pricing.crosswalk import CrosswalkMatcher
    from pricing.relational import APUHeader, RelationalPricingStore
    from pricing.resolver import PriceResolver

    store = RelationalPricingStore(
        apus={
            "20.01": APUHeader(
                codigo_apu="20.01",
                descripcion="Puerta interior de madera",
                unidad="ud",
                capitulo="Arquitectura carpinteria",
                total_declarado=12500.0,
            )
        },
        metadata={"currency": "DOP"},
    )
    resolver = PriceResolver(
        store,
        CrosswalkMatcher([
            {"id": "door_gap", "item_type": "door_count", "target": "UNMATCHED"},
        ]),
    )

    res = resolver.resolve(
        "door_count",
        {"takeoff_description": "Puerta madera interior"},
        unit="ud",
    )

    assert res.source == "estimated"
    assert res.estimated is True
    assert res.unit_price == 12500.0
    assert "analog_apu:20.01" in (res.estimate_basis or "")


def test_price_resolver_rejects_crosswalk_unit_family_mismatch():
    from pricing.crosswalk import CrosswalkMatcher
    from pricing.relational import APUHeader, RelationalPricingStore
    from pricing.resolver import PriceResolver

    store = RelationalPricingStore(
        apus={
            "6.01": APUHeader(
                codigo_apu="6.01",
                descripcion="Hormigon columnas",
                unidad="m3",
                capitulo="Estructura",
                total_declarado=1000.0,
            )
        },
        metadata={"currency": "DOP"},
    )
    resolver = PriceResolver(
        store,
        CrosswalkMatcher([
            {"id": "bad_rebar", "item_type": "column_reinforcement_kg", "target": "6.01"},
        ]),
    )

    res = resolver.resolve("column_reinforcement_kg", {}, unit="kg")

    assert res.source == "pending"
    assert res.unit_price is None


def test_composer_marks_estimated_price_as_preliminary():
    from budget.composer import compose_budget_rows
    from core.schemas import ProjectContext, QuantityTakeoff, QuantityTrace
    from pricing.resolver import PriceResolution

    class FakeResolver:
        def resolve(self, item_type, inputs, *, unit="", description=None):
            return PriceResolution(
                unit_price=100.0,
                currency="DOP",
                source="estimated",
                estimated=True,
                estimate_basis="analog_apu:X1",
            )

    takeoff = QuantityTakeoff(
        item_key="x1",
        item_type="excavation_volume",
        unit="m3",
        quantity=2.0,
        formula="area * depth",
        inputs={"takeoff_description": "Excavacion manual"},
        trace=QuantityTrace(),
    )

    _, lines, rows = compose_budget_rows(
        ProjectContext(project_id="P1", project_name="Test"),
        [takeoff],
        {},
        price_resolver=FakeResolver(),
    )

    assert lines[0].unit_price == 100.0
    assert lines[0].metadata["price_estimated"] is True
    assert lines[0].metadata["requiere_revision"] is True
    assert lines[0].metadata["budget_status"] == "PRELIMINAR"
    line_rows = [row for row in rows if row.row_type == "line"]
    assert line_rows[0].metadata["budget_status"] == "PRELIMINAR"


def test_structural_formwork_type_and_masonry_suppression():
    from agents.quantifier_agent import _structural_formwork_payload
    from core.schemas import StructuralElement

    beam = StructuralElement(
        id="B1",
        element_type="beam",
        material_hint="concrete",
        length_m=4.0,
        section_width_m=0.30,
        section_height_m=0.50,
    )
    qty, _formula, inputs, _assumptions = _structural_formwork_payload(
        beam,
        4.0,
        {"length_m": 4.0},
    )
    assert qty is not None
    assert inputs["formwork_type"] == "formaleta"

    block_wall_like = StructuralElement(
        id="M1",
        element_type="beam",
        material_hint="masonry",
        length_m=4.0,
        section_width_m=0.30,
        section_height_m=0.50,
    )
    qty, formula, inputs, assumptions = _structural_formwork_payload(
        block_wall_like,
        4.0,
        {"length_m": 4.0},
    )
    assert (qty, formula, inputs, assumptions) == (None, None, {}, [])


def test_layer_mapping_keyword_fallback_classifies_structural_layers():
    from config.layer_mapping import classify_layer
    from config.models import DisciplineCode

    assert classify_layer("COLUMNAS") == DisciplineCode.S
    assert classify_layer("GEBSA_VIGAS") == DisciplineCode.S
    assert classify_layer("muros") == DisciplineCode.S
