from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))

from budget.waste_policy import apply_waste, categorize, waste_fraction_for


def test_concrete_volume_gets_three_percent():
    assert waste_fraction_for("beam_concrete_volume") == 0.03
    assert waste_fraction_for("column_concrete_volume") == 0.03
    assert waste_fraction_for("slab_concrete_volume") == 0.03


def test_reinforcement_gets_five_percent():
    assert waste_fraction_for("beam_reinforcement_kg") == 0.05
    assert waste_fraction_for("column_reinforcement_kg") == 0.05


def test_formwork_gets_ten_percent():
    assert waste_fraction_for("beam_formwork_area_hint") == 0.10


def test_wall_finishes_get_seven_percent():
    assert waste_fraction_for("wall_finish_plaster") == 0.07
    assert waste_fraction_for("wall_finish_tile") == 0.07


def test_doors_and_windows_get_zero_waste():
    assert waste_fraction_for("door_count") == 0.0
    assert waste_fraction_for("window_count") == 0.0


def test_excavation_gets_ten_percent_for_overcut():
    assert waste_fraction_for("excavation_volume") == 0.10


def test_unknown_item_type_returns_zero():
    assert waste_fraction_for("imaginary_item") == 0.0
    assert waste_fraction_for("") == 0.0


def test_overrides_take_precedence():
    overrides = {"beam_concrete_volume": 0.08}
    assert waste_fraction_for("beam_concrete_volume", overrides=overrides) == 0.08


def test_apply_waste_returns_quantity_with_waste_and_note():
    qty, fraction, note = apply_waste(100.0, "beam_concrete_volume")
    assert fraction == 0.03
    assert qty == 103.0
    assert "merma" in note


def test_apply_waste_passthrough_when_fraction_zero():
    qty, fraction, note = apply_waste(50.0, "door_count")
    assert qty == 50.0
    assert fraction == 0.0
    assert note == ""


def test_categorize_returns_lookup_table():
    cats = categorize(["beam_concrete_volume", "door_count", "unknown"])
    assert cats == {"beam_concrete_volume": 0.03, "door_count": 0.0, "unknown": 0.0}


def test_fraction_is_clamped_to_safe_range():
    assert waste_fraction_for("beam_concrete_volume", overrides={"beam_concrete_volume": 5.0}) == 0.5
    assert waste_fraction_for("beam_concrete_volume", overrides={"beam_concrete_volume": -1.0}) == 0.0
