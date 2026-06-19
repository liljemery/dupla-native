"""Ingest snapshot and GA-FO APS reuse tests."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.config import get_settings
from app.models.project_file import ProjectFile
from app.services.project_file_classification_service import _aps_context_from_snapshot


def _file(**kwargs) -> ProjectFile:
    base = dict(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        storage_key="/tmp/sample.dwg",
        original_name="sample.dwg",
        created_at=datetime.utcnow(),
    )
    base.update(kwargs)
    return ProjectFile(**base)


def test_aps_context_from_snapshot_uses_layer_summary() -> None:
    pf = _file(
        aps_urn="urn:test",
        file_ingest_snapshot={
            "discipline_method": "aps_layers",
            "confidence": 0.82,
            "dominant_layers": ["EL-POWER", "EL-LIGHT"],
            "entities_sampled": 120,
        },
    )
    text = _aps_context_from_snapshot(pf, get_settings())
    assert text is not None
    assert "EL-POWER" in text
    assert "aps_layers" in text


def test_aps_context_from_snapshot_none_without_urn() -> None:
    pf = _file(
        file_ingest_snapshot={"discipline_method": "aps_layers", "confidence": 0.9},
    )
    assert _aps_context_from_snapshot(pf, get_settings()) is None
