from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_clash_item import ProjectClashItem
from app.models.project_clash_job import ProjectClashJob
from app.models.project_file import ProjectFile


async def _create_project(client, headers) -> uuid.UUID:
    res = await client.post(
        "/api/projects",
        headers=headers,
        data={"name": "Viewer demo", "project_kind": "CLIENT"},
    )
    assert res.status_code == 201, res.text
    return uuid.UUID(res.json()["uuid"])


async def _seed_job(session: AsyncSession, project_id: uuid.UUID) -> tuple[ProjectClashJob, ProjectClashItem]:
    job = ProjectClashJob(id=uuid.uuid4(), project_id=project_id, job_id="job-viewer", status="completed")
    item = ProjectClashItem(
        id=uuid.uuid4(),
        job_id=job.id,
        clash_code="incident_0001",
        priority="P1",
        severity="critical",
        report_confidence="medium",
        status="detected",
        dwg_a="architecture.dwg",
        dwg_b="structure.dwg",
        discipline_a="ARQUITECTURA",
        discipline_b="ESTRUCTURA",
        layer_a="A-WALL",
        layer_b="S-COL",
        bounds_minx_mm=670000,
        bounds_miny_mm=480000,
        bounds_maxx_mm=671200,
        bounds_maxy_mm=481400,
        centroid_x_mm=670600,
        centroid_y_mm=480700,
        alignment_dx_mm=658000,
        alignment_dy_mm=472000,
        raw_json={"representative_conflict": {"clash_type": "HARD"}},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(job)
    session.add(item)
    await session.commit()
    return job, item


@pytest.mark.asyncio
async def test_viewer_config_fails_clear_if_missing_urn(client, master_auth_headers_async: dict[str, str]) -> None:
    project_id = await _create_project(client, master_auth_headers_async)

    res = await client.get(f"/api/projects/{project_id}/viewer/config", headers=master_auth_headers_async)

    assert res.status_code == 404
    assert "Modelo no traducido" in res.text


@pytest.mark.asyncio
async def test_viewer_config_returns_urn_if_file_exists(
    client,
    session: AsyncSession,
    master_auth_headers_async: dict[str, str],
) -> None:
    project_id = await _create_project(client, master_auth_headers_async)
    session.add(
        ProjectFile(
            id=uuid.uuid4(),
            project_id=project_id,
            storage_key="/tmp/architecture.dwg",
            original_name="architecture.dwg",
            mime="application/octet-stream",
            discipline="architecture",
        )
    )
    await session.commit()

    res = await client.get(f"/api/projects/{project_id}/viewer/config", headers=master_auth_headers_async)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["urn"]
    assert body["clashes_url"].endswith("coordinate_space=world")


@pytest.mark.asyncio
async def test_viewer_clashes_world_and_model_coordinate_spaces(
    client,
    session: AsyncSession,
    master_auth_headers_async: dict[str, str],
) -> None:
    project_id = await _create_project(client, master_auth_headers_async)
    await _seed_job(session, project_id)

    world = await client.get(
        f"/api/projects/{project_id}/viewer/clashes?coordinate_space=world",
        headers=master_auth_headers_async,
    )
    model = await client.get(
        f"/api/projects/{project_id}/viewer/clashes?coordinate_space=model",
        headers=master_auth_headers_async,
    )

    assert world.status_code == 200, world.text
    assert model.status_code == 200, model.text
    assert world.json()["clashes"][0]["viewer_bbox"]["min_x"] == 12000
    assert model.json()["clashes"][0]["viewer_bbox"]["min_x"] == 670000


@pytest.mark.asyncio
async def test_viewer_clashes_filters(
    client,
    session: AsyncSession,
    master_auth_headers_async: dict[str, str],
) -> None:
    project_id = await _create_project(client, master_auth_headers_async)
    await _seed_job(session, project_id)

    high = await client.get(
        f"/api/projects/{project_id}/viewer/clashes?severity=high",
        headers=master_auth_headers_async,
    )
    structure = await client.get(
        f"/api/projects/{project_id}/viewer/clashes?discipline=structure",
        headers=master_auth_headers_async,
    )

    assert high.status_code == 200
    assert high.json()["summary"]["total"] == 0
    assert structure.status_code == 200
    assert structure.json()["summary"]["total"] == 1
