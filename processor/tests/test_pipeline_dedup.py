from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def _wall_payload(page: int, *, length_m: float = 10.0) -> dict:
    page_name = f"pdf_001_page_{page:04d}"
    return {
        "level_id": page_name,
        "level_name": page_name,
        "source": "vision",
        "source_refs": [f"vision:{page_name}"],
        "walls": [
            {
                "id": f"wall_page_{page}",
                "source": "vision",
                "source_refs": [f"vision:{page_name}:wall_01"],
                "inputs": {
                    "wall_typology": "B6",
                    "raw": {"wall_typology": "B6", "original_material_code": "block_6in"},
                },
                "length_m": length_m,
                "height_m": 2.8,
                "thickness_m": 0.15,
                "area_m2": round(length_m * 2.8, 3),
                "material_hint": "masonry",
                "wall_system": "masonry_wall",
            }
        ],
    }


def test_repeated_wall_typology_across_five_pages_collapses_to_one_wall_takeoff():
    from core.pipeline import build_hybrid_inventory, build_takeoffs_from_sources

    payloads = [_wall_payload(page) for page in range(1, 6)]

    levels = build_hybrid_inventory({}, payloads)
    assert len(levels) == 1
    assert levels[0].level_id == "level_01"
    assert len(levels[0].walls) == 1

    wall = levels[0].walls[0]
    assert wall.length_m == 10.0
    assert len(wall.source_refs) == 5

    _, takeoffs = build_takeoffs_from_sources({}, payloads)
    wall_length_takeoffs = [
        takeoff for takeoff in takeoffs if takeoff.item_type == "wall_length"
    ]
    assert len(wall_length_takeoffs) == 1
    assert wall_length_takeoffs[0].quantity == 10.0


def test_single_page_single_level_case_is_preserved():
    from core.pipeline import build_hybrid_inventory

    payload = _wall_payload(1, length_m=12.5)
    payload["doors"] = [
        {
            "id": "D1",
            "source": "vision",
            "source_refs": ["vision:pdf_001_page_0001:door_01"],
            "inputs": {"door_label": "D1"},
            "count": 2,
            "width_m": 0.9,
            "height_m": 2.1,
            "type_hint": "single",
        }
    ]

    levels = build_hybrid_inventory({}, [payload])

    assert len(levels) == 1
    assert len(levels[0].walls) == 1
    assert levels[0].walls[0].length_m == 12.5
    assert len(levels[0].doors) == 1
    assert levels[0].doors[0].count == 2
