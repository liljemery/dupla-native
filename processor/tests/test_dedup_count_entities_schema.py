from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def _construct_from_filtered_payload(model_cls, payload: dict):
    field_names = {field_def.name for field_def in fields(model_cls)}
    return model_cls(**{key: value for key, value in payload.items() if key in field_names})


def test_dedupe_count_entities_does_not_add_source_layers_to_wet_areas():
    from core.pipeline import _dedupe_count_entities
    from core.schemas import WetArea

    wet_areas = [
        WetArea(id="wet-1", kind="full_bathroom", count=1, source_refs=["vision:p1"]),
        WetArea(id="wet-2", kind="full_bathroom", count=2, source_refs=["vision:p2"]),
    ]

    merged = _dedupe_count_entities(
        wet_areas,
        key_fn=lambda item: (item.kind,),
        id_prefix="vision-wet-area",
        level_id="level_01",
    )

    assert len(merged) == 1
    assert "source_layers" not in merged[0]
    assert _construct_from_filtered_payload(WetArea, merged[0]).count == 2

    from core.schemas import level_inventory_from_dict

    dirty_payload = dict(merged[0])
    dirty_payload["source_layers"] = ["legacy-extra-field"]
    level = level_inventory_from_dict(
        {
            "level_id": "level_01",
            "level_name": "Level 01",
            "wet_areas": [dirty_payload],
        },
        default_source="vision",
    )
    assert level.wet_areas[0].kind == "full_bathroom"


def test_dedupe_count_entities_constructs_door_and_window_payloads():
    from core.pipeline import _dedupe_count_entities
    from core.schemas import Door, Window

    doors = [
        Door(id="D1", count=1, width_m=0.9, height_m=2.1, source_layers=["A-DOOR"]),
        Door(id="D1", count=3, width_m=0.9, height_m=2.1, source_layers=["A-DOOR"]),
    ]
    windows = [
        Window(id="W1", count=1, width_m=1.2, height_m=1.0, source_layers=["A-WIN"]),
        Window(id="W1", count=2, width_m=1.2, height_m=1.0, source_layers=["A-WIN"]),
    ]

    merged_doors = _dedupe_count_entities(
        doors,
        key_fn=lambda item: (item.id, item.width_m, item.height_m),
        id_prefix="vision-door",
        level_id="level_01",
    )
    merged_windows = _dedupe_count_entities(
        windows,
        key_fn=lambda item: (item.id, item.width_m, item.height_m),
        id_prefix="vision-window",
        level_id="level_01",
    )

    assert _construct_from_filtered_payload(Door, merged_doors[0]).count == 3
    assert _construct_from_filtered_payload(Window, merged_windows[0]).count == 2


def test_dedupe_count_entities_collapses_slug_colliding_keys():
    """Regression: two distinct group keys can _slug_key to the same string
    (e.g. ('v.1','beam') and ('v 1','beam') both → 'v-1-beam'). The dedup
    must collapse those into a single payload, not emit two payloads with the
    same id and trip `_assert_unique_takeoff_keys`.
    """
    from core.pipeline import _dedupe_count_entities
    from core.schemas import StructuralElement

    elements = [
        StructuralElement(
            id="vision-struct-page1",
            element_type="beam",
            count=4,
            inputs={"structural_label": "V.1"},
            source_refs=["vision:p1"],
        ),
        StructuralElement(
            id="vision-struct-page2",
            element_type="beam",
            count=6,
            inputs={"structural_label": "V 1"},
            source_refs=["vision:p2"],
        ),
        StructuralElement(
            id="vision-struct-page3",
            element_type="beam",
            count=3,
            inputs={"structural_label": "V-1"},
            source_refs=["vision:p3"],
        ),
    ]

    from core.pipeline import _entity_label, _norm_key

    merged = _dedupe_count_entities(
        elements,
        key_fn=lambda element: (
            _entity_label(element, "structural_label", "notation", "label"),
            _norm_key(getattr(element, "element_type", None)),
        ),
        id_prefix="vision-structural",
        level_id="level_01",
    )

    ids = [payload["id"] for payload in merged]
    assert len(ids) == len(set(ids)), (
        f"slug-colliding keys must collapse to one id; got: {ids}"
    )
    assert len(merged) == 1, (
        f"three slug-colliding entries must merge into one payload; got: {merged}"
    )
    assert merged[0]["count"] == 6, "merged count must be MAX, not sum"


def test_dedupe_count_entities_preserves_source_layers_for_wall_like_entities():
    from core.pipeline import _dedupe_count_entities
    from core.schemas import Wall

    walls = [
        Wall(
            id="B6-1",
            source_layers=["A-WALL"],
            source_refs=["vision:p1:wall_1"],
            inputs={"wall_typology": "B6"},
            length_m=10.0,
            thickness_m=0.15,
            material_hint="masonry",
        ),
        Wall(
            id="B6-2",
            source_layers=["A-WALL-2"],
            source_refs=["vision:p2:wall_1"],
            inputs={"wall_typology": "B6"},
            length_m=10.0,
            thickness_m=0.15,
            material_hint="masonry",
        ),
    ]

    merged = _dedupe_count_entities(
        walls,
        key_fn=lambda item: (item.inputs.get("wall_typology"), item.thickness_m),
        id_prefix="vision-wall",
        level_id="level_01",
    )

    assert len(merged) == 1
    assert merged[0]["source_layers"] == ["A-WALL", "A-WALL-2"]
