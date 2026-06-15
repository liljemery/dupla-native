"""Tests for APS model tree flattening."""

from __future__ import annotations

import sys
from pathlib import Path

MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from aps_integration.model_derivative import flatten_model_tree, _merge_property_collections


def test_flatten_model_tree_collects_nested_object_ids() -> None:
    payload = {
        "data": {
            "collection": [
                {
                    "objectid": 1,
                    "objects": [
                        {"objectid": 2, "objects": [{"objectid": 3}]},
                        {"objectid": 4},
                    ],
                }
            ]
        }
    }
    ids = flatten_model_tree(payload)
    assert ids == [1, 2, 3, 4]


def test_merge_property_collections_deduplicates_by_objectid() -> None:
    merged = _merge_property_collections(
        [
            [{"objectid": 1, "name": "a"}, {"objectid": 2, "name": "b"}],
            [{"objectid": 2, "name": "b2"}, {"objectid": 3, "name": "c"}],
        ]
    )
    by_id = {item["objectid"]: item["name"] for item in merged}
    assert by_id == {1: "a", 2: "b2", 3: "c"}
