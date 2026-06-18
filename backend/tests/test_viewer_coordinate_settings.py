from __future__ import annotations

import uuid

import pytest

from app.models.project_viewer_coordinate_settings import ProjectViewerCoordinateSettings
from app.schemas.clash_viewer import ViewerCoordinateSettings
from app.services.viewer_coordinate_settings_service import ViewerCoordinateSettingsService


class _ScalarResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeSession:
    def __init__(self):
        self.row = None
        self.added = None
        self.deleted = None

    async def execute(self, _stmt):
        return _ScalarResult(self.row)

    def add(self, row):
        self.row = row
        self.added = row

    async def commit(self):
        return None

    async def refresh(self, row):
        return None

    async def delete(self, row):
        self.deleted = row
        self.row = None


@pytest.mark.asyncio
async def test_get_defaults_when_no_settings() -> None:
    settings = await ViewerCoordinateSettingsService(_FakeSession()).get(uuid.uuid4(), "world")  # type: ignore[arg-type]

    assert settings.scale == 1.0
    assert settings.coordinate_space == "world"


@pytest.mark.asyncio
async def test_update_settings() -> None:
    session = _FakeSession()
    project_id = uuid.uuid4()
    payload = ViewerCoordinateSettings(coordinate_space="model", scale=1.5, offset_x=25, invert_y=True)

    settings = await ViewerCoordinateSettingsService(session).upsert(project_id, payload)  # type: ignore[arg-type]

    assert settings.coordinate_space == "model"
    assert settings.scale == 1.5
    assert settings.offset_x == 25
    assert settings.invert_y is True
    assert isinstance(session.added, ProjectViewerCoordinateSettings)


@pytest.mark.asyncio
async def test_reset_returns_defaults_and_deletes_row() -> None:
    session = _FakeSession()
    session.row = ProjectViewerCoordinateSettings(project_id=uuid.uuid4(), scale=2.0)

    settings = await ViewerCoordinateSettingsService(session).reset(uuid.uuid4(), "world")  # type: ignore[arg-type]

    assert settings.scale == 1.0
    assert session.deleted is not None
