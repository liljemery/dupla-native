from __future__ import annotations

import math
import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))

from agents.quantifier_agent import quantify_inventory
from core.schemas import LevelInventory, StructuralElement


def _level_with(elements: list[StructuralElement], **inputs) -> LevelInventory:
    return LevelInventory(
        level_id="level_01",
        level_name="Nivel 1",
        source="hybrid",
        structural_elements=elements,
        inputs=inputs,
    )


def test_circular_column_volume_uses_pi_r2():
    column = StructuralElement(
        id="C-circ-1",
        level_id="level_01",
        source="vision",
        element_type="column",
        count=1,
        length_m=3.0,
        material_hint="concrete",
        section_width_m=0.40,
        section_height_m=0.40,
        inputs={"raw": {"section_diameter_m": 0.40}, "cross_section_shape": "circular"},
    )
    level = _level_with([column])
    takeoffs = quantify_inventory([level])

    volume = next(t for t in takeoffs if t.item_type == "column_concrete_volume")
    expected = 3.0 * math.pi * (0.40 / 2.0) ** 2
    assert abs(volume.quantity - expected) < 1e-6
    assert "pi" in volume.formula


def test_rectangular_column_volume_uses_b_h():
    column = StructuralElement(
        id="C-rect-1",
        level_id="level_01",
        source="vision",
        element_type="column",
        count=1,
        length_m=3.0,
        material_hint="concrete",
        section_width_m=0.30,
        section_height_m=0.50,
    )
    level = _level_with([column])
    takeoffs = quantify_inventory([level])

    volume = next(t for t in takeoffs if t.item_type == "column_concrete_volume")
    assert abs(volume.quantity - (3.0 * 0.30 * 0.50)) < 1e-9


def test_excavation_simple_area_times_depth():
    level = _level_with(
        [],
        excavations=[
            {
                "id": "exc-001",
                "area_m2": 152.40,
                "depth_m": 1.0,
                "source_refs": ["json:V-SITE-CUT"],
            }
        ],
    )
    takeoffs = quantify_inventory([level])
    excav = next(t for t in takeoffs if t.item_type == "excavation_volume")
    assert excav.quantity == 152.40
    assert "area_m2 * depth_m" in excav.formula


def test_excavation_prismoidal_with_three_profiles():
    level = _level_with(
        [],
        excavations=[
            {
                "id": "exc-prismoidal",
                "profiles": [
                    {"chainage_m": 0.0, "area_m2": 4.0},
                    {"chainage_m": 5.0, "area_m2": 6.0},
                    {"chainage_m": 10.0, "area_m2": 8.0},
                ],
            }
        ],
    )
    takeoffs = quantify_inventory([level])
    excav = next(t for t in takeoffs if t.item_type == "excavation_volume")
    expected = (4.0 + 8.0 + 4 * 6.0) * 10.0 / 6.0
    assert abs(excav.quantity - expected) < 1e-6
    assert "prismoidal" in excav.inputs["excavation_method"]


def test_takeoff_with_structural_defaults_marks_requiere_revision():
    column = StructuralElement(
        id="C-defaults",
        level_id="level_01",
        source="vision",
        element_type="column",
        count=1,
        material_hint="concrete",
    )
    level = _level_with([column])
    takeoffs = quantify_inventory([level])
    volumes = [t for t in takeoffs if t.item_type == "column_concrete_volume"]
    assert volumes, "expected at least one column_concrete_volume takeoff"
    assert any(t.requiere_revision for t in volumes)
    assert all(t.confidence < 1.0 for t in volumes)


def test_explicit_dimensions_keep_full_confidence():
    column = StructuralElement(
        id="C-explicit",
        level_id="level_01",
        source="vision",
        element_type="column",
        count=1,
        length_m=3.0,
        material_hint="concrete",
        section_width_m=0.30,
        section_height_m=0.50,
    )
    level = _level_with([column])
    takeoffs = quantify_inventory([level])
    volume = next(t for t in takeoffs if t.item_type == "column_concrete_volume")
    assert volume.requiere_revision is False
    assert volume.confidence > 0.85
