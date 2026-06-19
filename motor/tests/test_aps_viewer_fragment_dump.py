"""Tests for APS Viewer fragment world-bounds extraction."""

from __future__ import annotations

import sys
from pathlib import Path

MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from coordination.core.models_25d import Discipline
from coordination.extraction.from_aps_viewer_dump import elements_from_viewer_dump


def _extract(objects: list[dict]) -> list:
    return elements_from_viewer_dump(
        {
            "views": [
                {
                    "name": "A-1.1",
                    "sheet_bounds": [0.0, 0.0, 36.27, 24.0],
                    "objects": objects,
                }
            ]
        },
        discipline=Discipline.ARCH,
        level_doc=None,
        default_level_id="P1",
        translation_mm=(0.0, 0.0),
        path_label="PLANOS ARQ",
        coordination_issue_key="issue",
        max_entities=10,
    )


def test_fragment_world_bounds_preserve_handle_and_sheet_units() -> None:
    elements = _extract(
        [
            {
                "handle": "82600EF",
                "dbId": 123,
                "layer": "NASAS_ARQ_P1_NPT",
                "world_bounds": [4.5575, 6.5008, 6.5717, 7.7767],
                "fragments": [{"world_bounds": [4.5575, 6.5008, 6.5717, 7.7767]}],
            }
        ]
    )

    assert len(elements) == 1
    metadata = elements[0].metadata
    assert metadata["handle"] == "82600EF"
    assert metadata["dbId"] == "123"
    assert metadata["geometry_source"] == "dwg_aps_fragment_world_bounds"
    assert metadata["geometry_quality"] == "good"
    assert metadata["coordinate_unit"] == "sheet_paper_units"
    assert metadata["center"] == [5.5646, 7.13875]
    assert elements[0].footprint_coords_mm == [
        (4.5575, 6.5008),
        (6.5717, 6.5008),
        (6.5717, 7.7767),
        (4.5575, 7.7767),
    ]


def test_full_sheet_aggregate_uses_tighter_fragment_when_available() -> None:
    elements = _extract(
        [
            {
                "handle": "3CD104E",
                "dbId": 456,
                "layer": "NASAS_ARQ_P1_NPT",
                "world_bounds": [0.0, 0.0, 36.27, 24.0],
                "fragments": [
                    {"world_bounds": [0.0, 0.0, 36.27, 24.0]},
                    {"world_bounds": [10.0, 10.0, 11.0, 11.0]},
                ],
            }
        ]
    )

    assert len(elements) == 1
    metadata = elements[0].metadata
    assert metadata["handle"] == "3CD104E"
    assert metadata["geometry_quality"] == "good"
    assert metadata["refinement"] == "fragment_refined"
    assert metadata["world_bounds"] == [10.0, 10.0, 11.0, 11.0]
