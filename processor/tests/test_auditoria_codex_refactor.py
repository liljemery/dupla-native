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


def test_price_resolver_estimate_rejects_outlier_analog():
    """A degenerate unit family must not estimate from its runaway outlier.

    Regression: the "count"/UD family held a RD$126,934 'camara desarenadora'
    that got fuzzy-matched to doors/windows/fixtures, fabricating that price for
    dozens of unrelated lines. The estimate must fall back to the family median.
    """
    from pricing.crosswalk import CrosswalkMatcher
    from pricing.relational import APUHeader, RelationalPricingStore
    from pricing.resolver import PriceResolver

    store = RelationalPricingStore(
        apus={
            "10.14": APUHeader(
                codigo_apu="10.14",
                descripcion="Trampa de grasa",
                unidad="ud",
                capitulo="Sanitario",
                total_declarado=4000.0,
            ),
            "10.16": APUHeader(
                codigo_apu="10.16",
                descripcion="Instalacion de equipo",
                unidad="ud",
                capitulo="Arquitectura",
                total_declarado=12000.0,
            ),
            "10.15": APUHeader(
                codigo_apu="10.15",
                descripcion="Camara desarenadora 3.00x1.20x2.00mt",
                unidad="ud",
                capitulo="Sanitario",
                total_declarado=126934.49,
            ),
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
        {"takeoff_description": "Puerta arco PV camara"},
        unit="ud",
    )

    assert res.source == "estimated"
    assert res.estimated is True
    # The runaway 126,934 outlier must never become the price.
    assert res.unit_price is not None and res.unit_price < 50000.0
    assert "no es precio de catalogo" in (res.estimate_basis or "")


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


def test_rebase_budget_row_indices_across_disciplines():
    """Merging disciplines must offset subtotal/chapter array indices.

    Regression: concatenating per-discipline rows without rebasing made
    subtotals sum the wrong discipline's lines (HORMIGON RD$46M vs ~RD$2M).
    """
    from budget.composer import rebase_budget_row_indices

    # One discipline's rows: [chapter, line, line, subtotal] (local indices 0..3)
    disc = [
        {"row_type": "chapter", "metadata": {"subtotal_row_index": 3}},
        {"row_type": "line", "metadata": {}},
        {"row_type": "line", "metadata": {}},
        {"row_type": "subtotal", "metadata": {"source_row_indices": [1, 2]}},
    ]

    master: list[dict] = []
    master.extend(rebase_budget_row_indices(disc, len(master)))  # offset 0
    master.extend(rebase_budget_row_indices(disc, len(master)))  # offset 4

    # First block keeps local indices
    assert master[0]["metadata"]["subtotal_row_index"] == 3
    assert master[3]["metadata"]["source_row_indices"] == [1, 2]
    # Second block is rebased by +4 and points at its own rows, not the first
    assert master[4]["metadata"]["subtotal_row_index"] == 7
    assert master[7]["metadata"]["source_row_indices"] == [5, 6]
    # Source payload not mutated
    assert disc[3]["metadata"]["source_row_indices"] == [1, 2]


def test_dwg_structural_aggregates_excluded_from_budget(monkeypatch):
    """Nivel 1: DWG bbox-aggregate structural takeoffs must not reach the budget.

    Regression for the absurd lines (column 'area' 71,539 m2, 525 beams, 910
    slabs) produced by summing bounding-box geometry per CAD layer. They carry a
    'json-<type>-…' item_key; the typed PDF/vision lines must survive.
    """
    from budget.composer import takeoff_budget_eligibility
    from core.schemas import QuantityTakeoff, QuantityTrace

    def mk(item_key, item_type, unit="m2", qty=71539.0):
        return QuantityTakeoff(
            item_key=item_key,
            item_type=item_type,
            unit=unit,
            quantity=qty,
            formula="x",
            inputs={},
            trace=QuantityTrace(),
        )

    monkeypatch.delenv("DUPLA_BUDGET_INCLUDE_DWG_STRUCTURAL", raising=False)

    kw = dict(derived_from_keys=set(), concrete_volume_prefixes=set())

    # DWG aggregates -> excluded
    for key, itype, unit, qty in [
        ("json-column-col:area", "structural_area", "m2", 71539.0),
        ("json-beam-vigas:count", "beam_count", "unit", 525.0),
        ("json-slab-losas:count", "slab_count", "unit", 910.0),
        ("json-column-col:column_length", "column_length", "m", 2608.0),
    ]:
        ok, reason = takeoff_budget_eligibility(mk(key, itype, unit, qty), **kw)
        assert ok is False, f"{key} should be excluded"
        assert reason == "dwg_structural_aggregate"

    # PDF/vision typed lines -> survive
    pdf = mk("pdf_001_page_0003.png:column_2", "column_concrete_volume", "m3", 0.69)
    ok, _ = takeoff_budget_eligibility(pdf, **kw)
    assert ok is True

    # Opt-in flag re-enables DWG aggregates
    monkeypatch.setenv("DUPLA_BUDGET_INCLUDE_DWG_STRUCTURAL", "1")
    ok, _ = takeoff_budget_eligibility(mk("json-beam-vigas:count", "beam_count", "unit", 525.0), **kw)
    assert ok is True
