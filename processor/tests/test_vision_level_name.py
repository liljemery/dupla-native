"""Tests for vision level-name resolution.

The cache key for vision_agent.analyze_plan used to embed the raw level_name
string. A CAD file with a long annotation marker (e.g. "El nivel de desplante
sera de 0.80m...") would produce a filename longer than NAME_MAX and crash
the worker with OSError 36. _resolve_vision_level_name must now reject markers
that are clearly annotations rather than labels.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def test_long_annotation_marker_is_rejected():
    from agents.vision_agent import _resolve_vision_level_name

    long_marker = (
        "El nivel de desplante sera de 0.80m bajo nivel de terreno natural "
        "considerando que la cota de la base de la zapata corresponde a -0.80 "
        "respecto al N+0.00 indicado en el plano de implantacion general."
    )
    assert len(long_marker) > 40
    cad = {"inventory_hints": {"level_markers": [long_marker]}}
    assert _resolve_vision_level_name(cad) == "level_01"


def test_nivel_1_label_is_accepted():
    from agents.vision_agent import _resolve_vision_level_name

    cad = {"inventory_hints": {"level_markers": ["Nivel 1"]}}
    assert _resolve_vision_level_name(cad) == "Nivel 1"


def test_n_plus_elevation_marker_is_accepted():
    from agents.vision_agent import _resolve_vision_level_name

    cad = {"inventory_hints": {"level_markers": ["N+0.00"]}}
    assert _resolve_vision_level_name(cad) == "N+0.00"


def test_empty_markers_returns_default():
    from agents.vision_agent import _resolve_vision_level_name

    assert _resolve_vision_level_name({}) == "level_01"
    assert _resolve_vision_level_name({"inventory_hints": {}}) == "level_01"
    assert _resolve_vision_level_name({"inventory_hints": {"level_markers": []}}) == "level_01"


def test_first_acceptable_marker_wins_over_leading_annotation():
    from agents.vision_agent import _resolve_vision_level_name

    long_marker = "Detalle de armado: refuerzo principal " + "x" * 200
    cad = {
        "inventory_hints": {
            "level_markers": [long_marker, {"content": "Planta Baja"}],
        }
    }
    assert _resolve_vision_level_name(cad) == "Planta Baja"
