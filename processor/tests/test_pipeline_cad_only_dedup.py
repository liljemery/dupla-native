"""Regression test for the CAD-only fallback duplicate-takeoff bug.

When vision payloads error out and the pipeline falls back to CAD-only, the
old code spawned one LevelInventory per "marker" found in
inventory_hints.level_markers. A CAD file with 66 noise markers therefore
produced 66 levels, each contributing the same CAD-derived takeoffs, which
crashed _assert_unique_takeoff_keys with:

    RuntimeError: Duplicate takeoff item_key detected before budget generation.
    Top offenders: json-wall-muros:length x66, ...

The fix: _build_cad_only_levels must always return exactly one level.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def _cad_facts_with_many_noise_markers(count: int = 50) -> dict:
    long_annotation = (
        "El nivel de desplante sera de 0.80m bajo nivel de terreno natural "
        "considerando la cota de la base de la zapata respecto al N+0.00 "
        "indicado en el plano de implantacion general. Nota tecnica numero "
    )
    markers = [long_annotation + str(i) for i in range(count)]
    return {
        "inventory_hints": {"level_markers": markers},
        "cad_facts": {"blocks": []},
    }


def test_cad_only_fallback_returns_exactly_one_level(monkeypatch):
    # Ensure GPT layer classification is skipped — keeps the test offline.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from core.pipeline import build_hybrid_inventory

    cad_facts = _cad_facts_with_many_noise_markers(50)
    levels = build_hybrid_inventory(cad_facts, None)

    assert len(levels) == 1, f"expected exactly 1 level, got {len(levels)}"
    assert levels[0].level_id == "level_01"


def test_build_takeoffs_does_not_raise_duplicate_key_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from core.pipeline import build_takeoffs_from_sources

    cad_facts = _cad_facts_with_many_noise_markers(50)

    # Must not raise RuntimeError("Duplicate takeoff item_key detected ...").
    hybrid_inventory, takeoffs = build_takeoffs_from_sources(cad_facts, None)

    assert len(hybrid_inventory) == 1
    item_keys = [t.item_key for t in takeoffs]
    assert len(item_keys) == len(set(item_keys)), (
        f"duplicate item_keys: {[k for k in set(item_keys) if item_keys.count(k) > 1]}"
    )


def test_single_valid_marker_is_adopted_as_level_name(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from core.pipeline import build_hybrid_inventory

    cad_facts = {
        "inventory_hints": {"level_markers": ["Nivel 1"]},
        "cad_facts": {"blocks": []},
    }
    levels = build_hybrid_inventory(cad_facts, None)
    assert len(levels) == 1
    assert levels[0].level_name == "Nivel 1"


def test_multiple_valid_markers_collapse_to_default_name(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from core.pipeline import build_hybrid_inventory

    cad_facts = {
        "inventory_hints": {"level_markers": ["Nivel 1", "Nivel 2", "Nivel 3"]},
        "cad_facts": {"blocks": []},
    }
    levels = build_hybrid_inventory(cad_facts, None)
    # CAD facts cannot be split per level without per-level vision evidence;
    # multiple markers must still collapse to exactly one level.
    assert len(levels) == 1
    assert levels[0].level_name == "level_01"
