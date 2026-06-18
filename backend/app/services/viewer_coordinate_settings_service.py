from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_viewer_coordinate_settings import ProjectViewerCoordinateSettings
from app.schemas.clash_viewer import ViewerCoordinateSettings
from app.services.clash_coordinate_mapper import CoordinateMapper


def default_coordinate_settings(coordinate_space: str = "world") -> ViewerCoordinateSettings:
    return ViewerCoordinateSettings(coordinate_space="model" if coordinate_space == "model" else "world")


def mapper_from_settings(settings: ViewerCoordinateSettings) -> CoordinateMapper:
    return CoordinateMapper(
        scale=settings.scale,
        offset_x=settings.offset_x,
        offset_y=settings.offset_y,
        offset_z=settings.offset_z,
        invert_y=settings.invert_y,
        rotation_degrees=settings.rotation_degrees,
        unit_factor=settings.unit_factor,
    )


class ViewerCoordinateSettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, project_id: UUID, coordinate_space: str = "world") -> ViewerCoordinateSettings:
        row = await self._row(project_id)
        if row is None:
            return default_coordinate_settings(coordinate_space)
        return _schema_from_row(row)

    async def upsert(
        self,
        project_id: UUID,
        payload: ViewerCoordinateSettings,
        *,
        created_by: UUID | None = None,
    ) -> ViewerCoordinateSettings:
        row = await self._row(project_id)
        now = datetime.now(timezone.utc)
        if row is None:
            row = ProjectViewerCoordinateSettings(
                project_id=project_id,
                created_by=created_by,
                created_at=now,
            )
            self._session.add(row)
        row.coordinate_space = "model" if payload.coordinate_space == "model" else "world"
        row.scale = payload.scale
        row.offset_x = payload.offset_x
        row.offset_y = payload.offset_y
        row.offset_z = payload.offset_z
        row.invert_y = payload.invert_y
        row.rotation_degrees = payload.rotation_degrees
        row.unit_factor = payload.unit_factor
        row.notes = payload.notes
        row.updated_at = now
        await self._session.commit()
        await self._session.refresh(row)
        return _schema_from_row(row)

    async def reset(self, project_id: UUID, coordinate_space: str = "world") -> ViewerCoordinateSettings:
        row = await self._row(project_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.commit()
        return default_coordinate_settings(coordinate_space)

    async def _row(self, project_id: UUID) -> ProjectViewerCoordinateSettings | None:
        result = await self._session.execute(
            select(ProjectViewerCoordinateSettings).where(ProjectViewerCoordinateSettings.project_id == project_id)
        )
        return result.scalar_one_or_none()


def _schema_from_row(row: ProjectViewerCoordinateSettings) -> ViewerCoordinateSettings:
    return ViewerCoordinateSettings(
        coordinate_space="model" if row.coordinate_space == "model" else "world",
        scale=float(row.scale),
        offset_x=float(row.offset_x),
        offset_y=float(row.offset_y),
        offset_z=float(row.offset_z),
        invert_y=bool(row.invert_y),
        rotation_degrees=float(row.rotation_degrees),
        unit_factor=float(row.unit_factor),
        notes=row.notes,
    )
