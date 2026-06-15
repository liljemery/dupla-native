"""Regression: quantify_inventory must not emit duplicate item_keys.

Wall and structural IDs are layer-based (e.g. "json-wall-muros") and repeat
verbatim across LevelInventory objects. Before this fix, multi-level inputs
would emit "json-wall-muros:length" once per level, blowing up
_assert_unique_takeoff_keys with x2 (or xN for N levels) collisions. The fix
namespaces item_keys by level_id when more than one level is present, while
preserving the legacy key shape for the common single-level case.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def _wall(level_id: str, *, wall_id: str = "json-wall-muros", length: float = 12.0):
    from core.schemas import Wall

    return Wall(
        id=wall_id,
        level_id=level_id,
        source="json",
        source_layers=["muros"],
        length_m=length,
        thickness_m=0.15,
        material_hint="masonry",
        wall_system="masonry_wall",
        inputs={"json_layer": "muros", "json_length_m": length},
    )


def _level(level_id: str, walls):
    from core.schemas import LevelInventory

    return LevelInventory(
        level_id=level_id,
        level_name=level_id,
        source="json",
        walls=walls,
    )


def test_single_level_keys_are_unique_and_un_namespaced():
    from core.pipeline import build_expanded_takeoffs_from_inventory

    level = _level("level_01", [_wall("level_01")])
    base_takeoffs, expanded_takeoffs = build_expanded_takeoffs_from_inventory([level])

    keys = [t.item_key for t in expanded_takeoffs]
    assert len(keys) == len(set(keys)), f"duplicate keys: {sorted(keys)}"
    # Legacy shape preserved when there's only one level.
    assert "json-wall-muros:length" in keys


def test_multi_level_same_wall_id_produces_unique_keys():
    from core.pipeline import build_expanded_takeoffs_from_inventory

    levels = [
        _level("level_01", [_wall("level_01", length=10.0)]),
        _level("level_02", [_wall("level_02", length=20.0)]),
    ]
    base_takeoffs, expanded_takeoffs = build_expanded_takeoffs_from_inventory(levels)

    keys = [t.item_key for t in expanded_takeoffs]
    duplicates = [k for k in set(keys) if keys.count(k) > 1]
    assert not duplicates, f"duplicate keys across levels: {duplicates}"
    # Per-level namespacing kicks in when there's more than one level.
    assert "level_01:json-wall-muros:length" in keys
    assert "level_02:json-wall-muros:length" in keys


def test_assert_unique_takeoff_keys_does_not_raise_for_multi_level():
    from core.pipeline import _assert_unique_takeoff_keys, build_expanded_takeoffs_from_inventory

    levels = [
        _level(f"level_{i:02d}", [_wall(f"level_{i:02d}", length=5.0 + i)])
        for i in range(1, 4)
    ]
    _, expanded_takeoffs = build_expanded_takeoffs_from_inventory(levels)

    # Must not raise RuntimeError("Duplicate takeoff item_key detected ...").
    _assert_unique_takeoff_keys(expanded_takeoffs)


def test_build_takeoffs_from_sources_cad_only_no_duplicates(monkeypatch):
    """CAD-only fallback collapses to 1 level and must emit unique keys."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from core.pipeline import build_takeoffs_from_sources

    cad_facts = {
        "inventory_hints": {"level_markers": ["Nivel 1", "Nivel 2"]},
        "cad_facts": {
            "blocks": [],
            "geometry_hints": [
                {"layer": "muros", "length": 12.5, "handle": "m1"},
                {"layer": "muros", "length": 4.0, "handle": "m2"},
            ],
        },
    }
    hybrid_inventory, takeoffs = build_takeoffs_from_sources(cad_facts, None)
    assert len(hybrid_inventory) == 1, "CAD-only must collapse to exactly 1 level"
    keys = [t.item_key for t in takeoffs]
    assert len(keys) == len(set(keys)), (
        f"duplicates after CAD-only fallback: "
        f"{[k for k in set(keys) if keys.count(k) > 1]}"
    )


def test_cad_layer_case_variants_merge_into_single_wall(monkeypatch):
    """Two CAD layers that differ only in case (e.g. 'MUROS' vs 'muros') must
    collapse into a single wall — otherwise both ids become 'json-wall-muros'
    and `_assert_unique_takeoff_keys` raises with x2 collisions.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from core.pipeline import build_takeoffs_from_sources

    cad_facts = {
        "cad_facts": {
            "blocks": [],
            "geometry_hints": [
                {"layer": "MUROS", "length": 8.0, "handle": "h1"},
                {"layer": "muros", "length": 4.0, "handle": "h2"},
                {"layer": " MUROS ", "length": 2.0, "handle": "h3"},
            ],
        },
    }
    hybrid_inventory, takeoffs = build_takeoffs_from_sources(cad_facts, None)
    assert len(hybrid_inventory) == 1
    walls = hybrid_inventory[0].walls
    wall_ids = [w.id for w in walls]
    assert wall_ids.count("json-wall-muros") == 1, (
        f"case-variant CAD layers must collapse to one wall; got: {wall_ids}"
    )
    keys = [t.item_key for t in takeoffs]
    assert len(keys) == len(set(keys)), (
        f"duplicates from case-variant layers: "
        f"{[k for k in set(keys) if keys.count(k) > 1]}"
    )
    merged_wall = next(w for w in walls if w.id == "json-wall-muros")
    assert merged_wall.length_m == 14.0, (
        f"lengths from all case variants must sum; got {merged_wall.length_m}"
    )


def test_cad_layer_case_variants_merge_structural_columns(monkeypatch):
    """Same protection for structural elements: 'COLUMNAS' and 'columnas'
    must collapse into one 'json-column-columnas' element.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from core.pipeline import build_takeoffs_from_sources

    cad_facts = {
        "cad_facts": {
            "blocks": [
                {"layer": "COLUMNAS", "block_name": "COL_A", "handle": "b1"},
                {"layer": "columnas", "block_name": "COL_B", "handle": "b2"},
            ],
            "geometry_hints": [],
        },
    }
    hybrid_inventory, takeoffs = build_takeoffs_from_sources(cad_facts, None)
    assert len(hybrid_inventory) == 1
    elements = hybrid_inventory[0].structural_elements
    column_ids = [e.id for e in elements if e.element_type == "column"]
    assert column_ids.count("json-column-columnas") == 1, (
        f"case-variant CAD layers must collapse to one column; got: {column_ids}"
    )
    keys = [t.item_key for t in takeoffs]
    assert len(keys) == len(set(keys)), (
        f"duplicates from case-variant column layers: "
        f"{[k for k in set(keys) if keys.count(k) > 1]}"
    )
