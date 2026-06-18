from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.config import get_settings
from app.models.project_file import ProjectFile
from app.services.aps_vie_service import ApsViewerService, _first_viewable_guid


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.committed = False

    async def execute(self, _stmt):
        return _Result(self.rows)

    async def commit(self):
        self.committed = True

    async def refresh(self, _row):
        return None


def _file(**kwargs) -> ProjectFile:
    base = dict(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        storage_key="/tmp/missing.dwg",
        original_name="architecture.dwg",
        mime="application/acad",
        created_at=datetime.utcnow(),
    )
    base.update(kwargs)
    return ProjectFile(**base)


def test_first_viewable_guid_prefers_2d_sheet_over_3d_geometry() -> None:
    manifest = {
        "derivatives": [
            {
                "children": [
                    {"type": "geometry", "role": "3d", "guid": "model-3d"},
                    {"type": "geometry", "role": "2d", "guid": "sheet-2d"},
                ]
            }
        ]
    }

    assert _first_viewable_guid(manifest) == "sheet-2d"


@pytest.mark.asyncio
async def test_viewer_config_uses_explicit_aps_urn() -> None:
    project_id = uuid.uuid4()
    file = _file(project_id=project_id, aps_urn="explicit-urn", aps_viewable_guid="sheet-guid")

    config = await ApsViewerService(_FakeSession([file]), get_settings()).viewer_config(project_id)

    assert config.urn == "explicit-urn"
    assert config.default_viewable_guid == "sheet-guid"
    assert "USING_DERIVED_URN_FALLBACK" not in config.warnings


@pytest.mark.asyncio
async def test_viewer_config_falls_back_to_derived_urn_with_warning() -> None:
    project_id = uuid.uuid4()
    file = _file(project_id=project_id)

    config = await ApsViewerService(_FakeSession([file]), get_settings()).viewer_config(project_id)

    assert config.urn
    assert "USING_DERIVED_URN_FALLBACK" in config.warnings


@pytest.mark.asyncio
async def test_refresh_manifest_updates_status_and_viewable_guid(monkeypatch) -> None:
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()
    file = _file(id=file_id, project_id=project_id, aps_urn="urn-1")
    session = _FakeSession([file])

    async def fake_token(_client, _settings):
        return "token"

    async def fake_fetch(_client, _settings, _token_box, _urn):
        return {"status": "success", "progress": "complete", "derivatives": [{"children": [{"type": "geometry", "guid": "guid-1"}]}]}

    monkeypatch.setattr("app.services.aps_vie_service._aps_token", fake_token)
    monkeypatch.setattr("app.services.aps_vie_service._fetch_manifest", fake_fetch)

    response = await ApsViewerService(session, get_settings()).refresh_file_manifest(project_id, file_id)

    assert response.aps_derivative_status == "success"
    assert response.aps_viewable_guid == "guid-1"
    assert file.aps_manifest_json["status"] == "success"
    assert session.committed is True
