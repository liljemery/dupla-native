"""Tests for core.pipeline._extract_level_markers.

The pipeline used to accept any string from inventory_hints.level_markers as a
level name. CAD files with annotation markers (e.g. structural notes captured
as TEXT entities) leaked through and were treated as fake levels, producing
duplicate takeoffs downstream. The filter must reject anything that is not
clearly a level label.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def _cad(markers: list) -> dict:
    return {"inventory_hints": {"level_markers": markers}}


def test_long_annotation_marker_is_rejected():
    from core.pipeline import _extract_level_markers

    long_marker = (
        "El nivel de desplante sera de 0.80m bajo nivel de terreno natural "
        "considerando que la cota de la base de la zapata corresponde a -0.80 "
        "respecto al N+0.00 indicado en el plano de implantacion general."
    )
    assert len(long_marker) > 40
    assert _extract_level_markers(_cad([long_marker])) == []


def test_accepts_nivel_label():
    from core.pipeline import _extract_level_markers

    assert _extract_level_markers(_cad(["Nivel 1"])) == ["Nivel 1"]


def test_accepts_elevation_marker():
    from core.pipeline import _extract_level_markers

    assert _extract_level_markers(_cad(["N+0.00"])) == ["N+0.00"]


def test_accepts_planta_baja():
    from core.pipeline import _extract_level_markers

    assert _extract_level_markers(_cad(["Planta Baja"])) == ["Planta Baja"]


def test_accepts_sotano_1():
    from core.pipeline import _extract_level_markers

    assert _extract_level_markers(_cad(["Sotano 1"])) == ["Sotano 1"]


def test_duplicates_are_collapsed():
    from core.pipeline import _extract_level_markers

    markers = ["Nivel 1", "Nivel 1", "Nivel 2", "Nivel 1", "Nivel 2"]
    assert _extract_level_markers(_cad(markers)) == ["Nivel 1", "Nivel 2"]


def test_mapping_marker_with_content_key_is_accepted():
    from core.pipeline import _extract_level_markers

    cad = _cad([{"content": "Nivel 1"}, {"content": "x" * 200}])
    assert _extract_level_markers(cad) == ["Nivel 1"]


def test_empty_or_missing_returns_empty_list():
    from core.pipeline import _extract_level_markers

    assert _extract_level_markers({}) == []
    assert _extract_level_markers({"inventory_hints": {}}) == []
    assert _extract_level_markers(_cad([])) == []
