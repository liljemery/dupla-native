"""
Verification suite for the P1 roadmap work:

    P1.6  Notas -> parametros duros          (knowledge/project_parameters.py)
    P1.4  RulesEngine 1->N derivation        (rules_engine.py + derivation_rules.yaml)
    P1.5  Cuadros como autoridad             (knowledge/schedule_authority.py)
    (b)   Cuadro de acabados binding         (knowledge/finishes_schedule.py)

These are deterministic and do NOT call OpenAI (the extractors degrade to
defaults / accept synthetic schedule dicts), so they prove the wiring + math.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def _tk(item_type: str, quantity: float, *, key: str | None = None, inputs: dict | None = None,
        unit: str = "m2", level_id: str = "L1"):
    from core.schemas import QuantityTakeoff, QuantityTrace

    return QuantityTakeoff(
        item_key=key or f"{item_type}-test",
        item_type=item_type,
        level_id=level_id,
        unit=unit,
        quantity=quantity,
        formula="",
        inputs=inputs or {},
        trace=QuantityTrace(),
    )


# ---------------------------------------------------------------------------
# P1.6 — Notas -> parametros duros
# ---------------------------------------------------------------------------

def test_project_parameters_defaults_no_key():
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("DUPLA_OPENAI_KEYS", None)
    from knowledge.project_parameters import extract_project_parameters

    p = extract_project_parameters("NIVEL 2", discipline="estructura")
    assert p.source == "defaults"
    assert p.fc_default == 280 and p.fy == 4200
    assert p.desperdicios.get("mortero") == 0.10


def test_project_parameters_discipline_override():
    from knowledge.project_parameters import load_defaults

    arq = load_defaults("arquitectura")
    assert arq["bloque_default"] == "block_6in"
    assert "desperdicios" in arq


def test_project_parameters_empty_text_is_defaults():
    from knowledge.project_parameters import extract_project_parameters

    p = extract_project_parameters("", discipline=None)
    assert p.source == "defaults"


def test_collect_notes_text_scrapes_containers():
    from knowledge.project_parameters import collect_notes_text

    cad = {
        "texts": [{"content": "f'c = 280 kg/cm2"}, {"text": "RECUBRIMIENTO 4cm"}],
        "inventory_hints": {"level_markers": [{"content": "NIVEL 1"}]},
    }
    text = collect_notes_text(cad, legend_page_map={"p1": {"floor_label": "NIVEL 2"}})
    assert "280" in text and "NIVEL 1" in text and "NIVEL 2" in text


# ---------------------------------------------------------------------------
# P1.4 — RulesEngine derivation
# ---------------------------------------------------------------------------

def test_derivation_wall_floor_ceiling():
    from rules_engine import default_rules_engine

    eng = default_rules_engine(
        discipline="arquitectura",
        project_parameters={"desperdicios": {"mortero": 0.10, "pintura": 0.05}},
    )
    base = [
        _tk("wall_net_area", 10.0, key="w1:net_area", inputs={"context_tags": ["exterior"]}),
        _tk("floor_area", 20.0, key="f1:area"),
        _tk("ceiling_area", 20.0, key="c1:area"),
    ]
    out = eng.apply(base)
    types = {t.item_type for t in out}
    assert "wall_finish_plaster" in types
    assert "wall_finish_paint" in types
    assert "wall_waterproofing" in types  # exterior context
    assert "floor_screed" in types
    assert "ceiling_finish_plaster" in types and "ceiling_finish_paint" in types
    # plaster/paint on 2 faces -> 20 from a 10 m2 wall
    plaster = next(t for t in out if t.item_type == "wall_finish_plaster")
    assert plaster.quantity == 20.0


def test_derivation_waterproofing_only_when_wet_or_exterior():
    from rules_engine import default_rules_engine

    eng = default_rules_engine(discipline="arquitectura", project_parameters={})
    base = [_tk("wall_net_area", 10.0, key="w1:net_area", inputs={"context_tags": ["interior"]})]
    out = eng.apply(base)
    assert "wall_waterproofing" not in {t.item_type for t in out}


def test_derivation_no_double_count_when_finish_exists():
    from rules_engine import default_rules_engine

    eng = default_rules_engine(discipline="arquitectura", project_parameters={})
    base = [
        _tk("wall_net_area", 10.0, key="w1:net_area"),
        _tk("wall_finish_plaster", 5.0, key="w1:plaster"),  # already measured
    ]
    out = eng.apply(base)
    plasters = [t for t in out if t.item_type == "wall_finish_plaster"]
    assert len(plasters) == 1  # not duplicated


def test_derivation_disabled_flag(monkeypatch=None):
    from rules_engine import default_rules_engine

    os.environ["DUPLA_DERIVATION_ENABLED"] = "0"
    try:
        eng = default_rules_engine(discipline="arquitectura", project_parameters={})
        base = [_tk("wall_net_area", 10.0, key="w1:net_area")]
        out = eng.apply(base)
        assert len(out) == 1
    finally:
        os.environ.pop("DUPLA_DERIVATION_ENABLED", None)


# ---------------------------------------------------------------------------
# P1.5 — Cuadros como autoridad
# ---------------------------------------------------------------------------

def test_steel_authority_replaces_ratio_with_despiece():
    from knowledge.schedule_authority import apply_structural_steel_authority

    base = [
        _tk("column_reinforcement_kg", 999.0, key="col1:rebar", unit="kg"),
        _tk("column_concrete_volume", 6.5, key="col1:conc", unit="m3"),
    ]
    schedule = {"filas": [
        {"mark": "C1", "element": "columna", "section": "0.30x0.60",
         "main_bars": "8#6", "stirrups": "#3@0.15", "count": 12, "length_m": 3.0},
    ]}
    out = apply_structural_steel_authority(base, schedule, cover_m=0.04)
    rebar = [t for t in out if t.item_type == "column_reinforcement_kg"]
    assert len(rebar) == 1
    # 8#6 x 3m x12 = 53.76 + stirrups 19.76 -> 73.52 x12 = 882.24
    assert abs(rebar[0].quantity - 882.24) < 0.5
    assert rebar[0].inputs.get("quantity_source") == "cuadro"
    # concrete volume untouched
    assert any(t.item_type == "column_concrete_volume" for t in out)


def test_steel_authority_noop_without_schedule():
    from knowledge.schedule_authority import apply_structural_steel_authority

    base = [_tk("column_reinforcement_kg", 999.0, key="c:r", unit="kg")]
    out = apply_structural_steel_authority(base, {}, cover_m=0.04)
    assert out == base


def test_opening_count_authority_fills_gap_only():
    from knowledge.schedule_authority import apply_opening_count_authority

    base = [_tk("door_count", 3, key="d1:count", unit="ud")]
    sched = {"filas": [{"mark": "P1", "kind": "puerta", "count": 10},
                       {"mark": "V1", "kind": "ventana", "count": 6}]}
    out = apply_opening_count_authority(base, sched)
    door_gap = [t for t in out if t.item_type == "door_count" and t.inputs.get("quantity_source") == "cuadro"]
    win_gap = [t for t in out if t.item_type == "window_count" and t.inputs.get("quantity_source") == "cuadro"]
    assert door_gap and door_gap[0].quantity == 7.0   # 10 - 3
    assert win_gap and win_gap[0].quantity == 6.0      # 6 - 0


def test_opening_authority_no_gap_when_detected_enough():
    from knowledge.schedule_authority import apply_opening_count_authority

    base = [_tk("door_count", 12, key="d:c", unit="ud")]
    sched = {"filas": [{"mark": "P1", "kind": "puerta", "count": 10}]}
    out = apply_opening_count_authority(base, sched)
    assert all(t.inputs.get("quantity_source") != "cuadro" for t in out)


# ---------------------------------------------------------------------------
# (b) Cuadro de acabados binding
# ---------------------------------------------------------------------------

def test_finishes_binding_matches_rooms():
    from knowledge.finishes_schedule import bind_finishes_to_rooms

    schedule = {"ambientes": [
        {"ambiente": "bano", "piso": "porcelanato", "zocalo": None, "pared": "ceramica", "cielo": "pvc"},
    ]}
    bound = bind_finishes_to_rooms(schedule, ["Bano 1", "Sala"])
    assert "Bano 1" in bound and bound["Bano 1"]["piso"] == "porcelanato"
    assert "Sala" not in bound


def test_finishes_focus_notes_keeps_table_lines():
    from knowledge.finishes_schedule import _focus_notes

    text = (
        "PROYECTO RESIDENCIAL\n"
        "INDICE DE LAMINAS\n"
        "CUADRO DE ACABADOS\n"
        "SALA porcelanato porcelanato pintura gypsum\n"
        "BANO antideslizante ceramica h=1.80 pvc\n"
    )
    focused = _focus_notes(text)
    assert "CUADRO DE ACABADOS" in focused
    assert "SALA" in focused
    assert "INDICE DE LAMINAS" not in focused
