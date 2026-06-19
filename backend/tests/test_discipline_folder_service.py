"""Discipline virtual folder tree tests."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.domain.discipline_folder_paths import DISCIPLINE_FOLDER_REL_PATHS
from app.models.project_file_folder import ProjectFileFolder
from app.services.discipline_folder_service import ensure_discipline_folder_tree, resolve_discipline_folder_id


@pytest.mark.asyncio
async def test_resolve_discipline_folder_id_concurrent_no_duplicate_tecnicos(
    client, master_auth_headers_async, session
) -> None:
    create = await client.post(
        "/api/projects",
        headers=master_auth_headers_async,
        data={"name": "Concurrent folders", "client_name": "Cliente", "project_kind": "CLIENT"},
    )
    assert create.status_code == 201, create.text
    project_id = uuid.UUID(create.json()["uuid"])

    await asyncio.gather(
        resolve_discipline_folder_id(session, project_id, "estructura"),
        resolve_discipline_folder_id(session, project_id, "electrica"),
        resolve_discipline_folder_id(session, project_id, "mecanica"),
    )
    await session.flush()

    rows = list(
        (await session.execute(select(ProjectFileFolder).where(ProjectFileFolder.project_id == project_id))).scalars()
    )
    tecnicos = [row for row in rows if row.name == "TECNICOS"]
    assert len(tecnicos) == 1


@pytest.mark.asyncio
async def test_ensure_discipline_folder_tree_idempotent(client, master_auth_headers_async, session) -> None:
    create = await client.post(
        "/api/projects",
        headers=master_auth_headers_async,
        data={"name": "Folder tree test", "client_name": "Cliente", "project_kind": "CLIENT"},
    )
    assert create.status_code == 201, create.text
    project_id = uuid.UUID(create.json()["uuid"])

    first = await ensure_discipline_folder_tree(session, project_id, created_by=None)
    await session.flush()
    second = await ensure_discipline_folder_tree(session, project_id, created_by=None)

    assert first == second
    assert set(first.keys()) == set(DISCIPLINE_FOLDER_REL_PATHS.keys())

    rows = list(
        (await session.execute(select(ProjectFileFolder).where(ProjectFileFolder.project_id == project_id))).scalars()
    )
    names = {row.name for row in rows}
    assert "PLANOS RECIBIDOS" in names
    tecnicos = [row for row in rows if row.name == "TECNICOS"]
    assert len(tecnicos) == 1
    assert "ELECTRICO" in names
    assert "SIN_CLASIFICAR" in names


@pytest.mark.asyncio
async def test_resolve_discipline_folder_id_electrica(client, master_auth_headers_async, session) -> None:
    create = await client.post(
        "/api/projects",
        headers=master_auth_headers_async,
        data={"name": "Resolve bucket", "client_name": "Cliente", "project_kind": "CLIENT"},
    )
    assert create.status_code == 201, create.text
    project_id = uuid.UUID(create.json()["uuid"])

    folder_id = await resolve_discipline_folder_id(session, project_id, "electrica")
    assert folder_id is not None
    row = await session.get(ProjectFileFolder, folder_id)
    assert row is not None
    assert row.name == "ELECTRICO"
