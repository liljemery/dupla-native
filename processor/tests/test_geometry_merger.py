"""
(P2.7) Tests for the GeometryMerger — kills double counting of walls.

Pure geometry, no APS needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def test_two_parallel_faces_collapse_to_one_length():
    from core.geometry_merger import merge_segments

    # Two faces of a 5 m wall, 0.15 m apart, perfectly aligned.
    segs = [((0.0, 0.0), (5.0, 0.0)), ((0.0, 0.15), (5.0, 0.15))]
    res = merge_segments(segs)
    assert abs(res["raw_length_m"] - 10.0) < 1e-6
    assert abs(res["merged_length_m"] - 5.0) < 1e-6  # not 10


def test_far_apart_parallel_lines_not_merged():
    from core.geometry_merger import merge_segments

    # 2 m apart -> not the two faces of one wall (exceeds max thickness).
    segs = [((0.0, 0.0), (5.0, 0.0)), ((0.0, 2.0), (5.0, 2.0))]
    res = merge_segments(segs)
    assert abs(res["merged_length_m"] - 10.0) < 1e-6


def test_perpendicular_lines_not_merged():
    from core.geometry_merger import merge_segments

    segs = [((0.0, 0.0), (5.0, 0.0)), ((0.0, 0.0), (0.0, 5.0))]
    res = merge_segments(segs)
    assert abs(res["merged_length_m"] - 10.0) < 1e-6


def test_collinear_overlap_union():
    from core.geometry_merger import merge_segments

    # Same line drawn twice with overlap: [0,5] and [3,8] -> union 8.
    segs = [((0.0, 0.0), (5.0, 0.0)), ((3.0, 0.0), (8.0, 0.0))]
    res = merge_segments(segs)
    assert abs(res["merged_length_m"] - 8.0) < 1e-6


def test_non_overlapping_parallel_close_kept_separate():
    from core.geometry_merger import merge_segments

    # Parallel and close but no overlap along axis -> two real walls in line.
    segs = [((0.0, 0.0), (2.0, 0.0)), ((5.0, 0.1), (8.0, 0.1))]
    res = merge_segments(segs)
    assert abs(res["merged_length_m"] - 5.0) < 1e-6  # 2 + 3


def test_merge_geometry_hints_drops_duplicate_and_sets_length():
    from core.geometry_merger import merge_geometry_hints

    hints = [
        {"entity_type": "line", "layer": "MUROS", "length": 5.0,
         "start": {"X": 0, "Y": 0}, "end": {"X": 5, "Y": 0}},
        {"entity_type": "line", "layer": "MUROS", "length": 5.0,
         "start": {"X": 0, "Y": 0.15}, "end": {"X": 5, "Y": 0.15}},
        {"entity_type": "block reference", "layer": "PUERTAS"},  # passthrough
    ]
    new_hints, stats = merge_geometry_hints(hints)
    assert stats["applied"] is True
    assert stats["collapsed_segments"] == 1
    line_hints = [h for h in new_hints if h.get("entity_type") == "line"]
    assert len(line_hints) == 1
    assert abs(line_hints[0]["length"] - 5.0) < 1e-6
    assert any(h.get("entity_type") == "block reference" for h in new_hints)  # kept


def test_merge_geometry_hints_noop_without_coords():
    from core.geometry_merger import merge_geometry_hints

    hints = [
        {"entity_type": "line", "layer": "MUROS", "length": 5.0},
        {"entity_type": "line", "layer": "MUROS", "length": 5.0},
    ]
    new_hints, stats = merge_geometry_hints(hints)
    assert stats["applied"] is False
    assert len(new_hints) == 2  # unchanged, cannot dedup without coords


def test_polyline_vertices_expand_to_segments():
    from core.geometry_merger import hint_segments

    hint = {"entity_type": "polyline", "vertices": [
        {"X": 0, "Y": 0}, {"X": 3, "Y": 0}, {"X": 3, "Y": 4}]}
    segs = hint_segments(hint)
    assert len(segs) == 2
