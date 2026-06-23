from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.models.project_clash_item import ProjectClashItem
from app.models.project_clash_job import ProjectClashJob
from app.schemas.clash_viewer import ViewerCoordinateSettings
from app.services.clash_coordinate_mapper import CoordinateMapper
from app.services.clash_viewer_adapter import ClashViewerAdapter, normalize_clash_type, normalize_severity


def _job(project_id: uuid.UUID) -> ProjectClashJob:
    return ProjectClashJob(id=uuid.uuid4(), project_id=project_id, job_id="job-1", status="completed")


def _item(**kwargs) -> ProjectClashItem:
    base = dict(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        clash_code="incident_0001",
        severity="critical",
        report_confidence="medium",
        status="detected",
        dwg_a="architecture.dwg",
        dwg_b="structure.dwg",
        discipline_a="ARQUITECTURA",
        discipline_b="ESTRUCTURA",
        layer_a="A-WALL",
        layer_b="S-COL",
        bounds_minx_mm=670000.0,
        bounds_miny_mm=480000.0,
        bounds_maxx_mm=671200.0,
        bounds_maxy_mm=481400.0,
        centroid_x_mm=670600.0,
        centroid_y_mm=480700.0,
        alignment_dx_mm=658000.0,
        alignment_dy_mm=472000.0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        raw_json={"representative_conflict": {"clash_type": "HARD"}},
    )
    base.update(kwargs)
    return ProjectClashItem(**base)


def test_project_clash_item_model_bounds_generates_valid_viewer_clash() -> None:
    project_id = uuid.uuid4()
    job = _job(project_id)
    item = _item(job_id=job.id)
    adapter = ClashViewerAdapter(session=None)  # type: ignore[arg-type]

    clash = adapter._from_item(project_id, job, item, 1, "model", {}, [])

    assert clash is not None
    assert clash.viewer_bbox.min_x == 670000.0
    assert clash.viewer_bbox.max_y == 481400.0
    assert clash.center.x == 670600.0
    assert clash.clash_type == "hard_2d"


def test_world_coordinate_space_uses_world_bounds_from_alignment() -> None:
    project_id = uuid.uuid4()
    job = _job(project_id)
    item = _item(job_id=job.id)
    warnings: list[str] = []
    adapter = ClashViewerAdapter(session=None)  # type: ignore[arg-type]

    clash = adapter._from_item(project_id, job, item, 1, "world", {}, warnings)

    assert clash is not None
    assert clash.viewer_bbox.min_x == 12000.0
    assert clash.viewer_bbox.min_y == 8000.0
    assert all(not warning.startswith("MISSING_ALIGNMENT_OFFSET") for warning in warnings)


def test_missing_world_bounds_uses_model_bounds_and_warning() -> None:
    project_id = uuid.uuid4()
    job = _job(project_id)
    item = _item(job_id=job.id, alignment_dx_mm=None, alignment_dy_mm=None)
    warnings: list[str] = []
    adapter = ClashViewerAdapter(session=None)  # type: ignore[arg-type]

    clash = adapter._from_item(project_id, job, item, 1, "world", {}, warnings)

    assert clash is not None
    assert clash.viewer_bbox.min_x == 670000.0
    assert "MISSING_ALIGNMENT_OFFSET:incident_0001" in warnings


def test_normalizes_unknown_severity_to_medium_and_type_to_unknown() -> None:
    assert normalize_severity("weird") == "medium"
    assert normalize_clash_type("weird") == "unknown"


def test_excludes_item_without_bbox() -> None:
    project_id = uuid.uuid4()
    job = _job(project_id)
    item = _item(job_id=job.id, bounds_minx_mm=None)
    warnings: list[str] = []
    adapter = ClashViewerAdapter(session=None)  # type: ignore[arg-type]

    assert adapter._from_item(project_id, job, item, 1, "world", {}, warnings) is None
    assert "MISSING_BBOX:incident_0001" in warnings


def test_generates_description_and_recommendation_when_missing() -> None:
    project_id = uuid.uuid4()
    job = _job(project_id)
    item = _item(job_id=job.id, observation=None, recommended_action=None)
    adapter = ClashViewerAdapter(session=None)  # type: ignore[arg-type]

    clash = adapter._from_item(project_id, job, item, 1, "model", {}, [])

    assert clash is not None
    assert "architecture" in clash.description
    assert clash.recommendation


def test_from_item_applies_mapper_scale_and_offset() -> None:
    project_id = uuid.uuid4()
    job = _job(project_id)
    item = _item(job_id=job.id)
    adapter = ClashViewerAdapter(session=None)  # type: ignore[arg-type]

    clash = adapter._from_item(
        project_id,
        job,
        item,
        1,
        "world",
        {},
        [],
        CoordinateMapper(scale=2, offset_x=10, offset_y=20),
        True,
        ViewerCoordinateSettings(scale=2, offset_x=10, offset_y=20),
    )

    assert clash is not None
    assert clash.raw_world_bbox_mm.min_x == 12000.0
    assert clash.viewer_bbox.min_x == 24010.0
    assert clash.viewer_bbox.min_y == 16020.0
    assert clash.mapper_applied is True


def test_from_item_applies_mapper_invert_y() -> None:
    project_id = uuid.uuid4()
    job = _job(project_id)
    item = _item(job_id=job.id)
    adapter = ClashViewerAdapter(session=None)  # type: ignore[arg-type]

    clash = adapter._from_item(project_id, job, item, 1, "world", {}, [], CoordinateMapper(invert_y=True), True)

    assert clash is not None
    assert clash.viewer_bbox.min_y == -9400.0
    assert clash.viewer_bbox.max_y == -8000.0
