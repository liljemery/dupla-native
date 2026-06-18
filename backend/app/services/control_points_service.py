"""Layer C manual alignment control points per project."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_control_points import ProjectControlPoints
from app.models.user import User
from app.services.project_service import ProjectService


_POINT_REQUIRED_KEYS = {"label", "model_xy", "ref_xy"}


def _validate_point(p: Any) -> None:
    if not isinstance(p, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each point must be an object with label, model_xy, ref_xy.",
        )
    missing = _POINT_REQUIRED_KEYS - set(p.keys())
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Point missing required keys: {sorted(missing)}",
        )
    for coord_key in ("model_xy", "ref_xy"):
        val = p.get(coord_key)
        if not isinstance(val, (list, tuple)) or len(val) != 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Point.{coord_key} must be a [x, y] list.",
            )
        try:
            float(val[0])
            float(val[1])
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Point.{coord_key} coordinates must be numeric.",
            ) from exc


class ControlPointsService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self._session = session
        self._workspace_id = workspace_id
        self._project_svc = ProjectService(session, workspace_id)

    async def _get_project(self, user: User, project_uuid: UUID):
        return await self._project_svc.get_project(user, project_uuid)

    async def list_control_points(
        self, user: User, project_uuid: UUID
    ) -> list[dict[str, Any]]:
        project = await self._get_project(user, project_uuid)
        result = await self._session.execute(
            select(ProjectControlPoints)
            .where(ProjectControlPoints.project_id == project.id)
            .order_by(ProjectControlPoints.discipline)
        )
        rows = list(result.scalars().all())
        return [_row_to_dict(r) for r in rows]

    async def upsert_control_points(
        self,
        user: User,
        project_uuid: UUID,
        discipline: str,
        reference: str,
        points: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not discipline.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="discipline is required.",
            )
        if not points:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide at least one control point.",
            )
        for p in points:
            _validate_point(p)

        project = await self._get_project(user, project_uuid)
        result = await self._session.execute(
            select(ProjectControlPoints)
            .where(
                ProjectControlPoints.project_id == project.id,
                ProjectControlPoints.discipline == discipline.strip().upper(),
            )
        )
        row = result.scalar_one_or_none()

        clean_points = [
            {
                "label": str(p["label"]),
                "model_xy": [float(p["model_xy"][0]), float(p["model_xy"][1])],
                "ref_xy": [float(p["ref_xy"][0]), float(p["ref_xy"][1])],
            }
            for p in points
        ]

        if row is None:
            row = ProjectControlPoints(
                id=uuid.uuid4(),
                project_id=project.id,
                discipline=discipline.strip().upper(),
                reference=reference.strip().upper() or "ARQ",
                points=clean_points,
                created_by=user.email,
            )
            self._session.add(row)
        else:
            row.points = clean_points
            row.reference = reference.strip().upper() or row.reference
            row.updated_at = datetime.now(timezone.utc)

        await self._session.flush()
        return _row_to_dict(row)

    async def delete_control_points(
        self, user: User, project_uuid: UUID, discipline: str
    ) -> None:
        project = await self._get_project(user, project_uuid)
        result = await self._session.execute(
            select(ProjectControlPoints)
            .where(
                ProjectControlPoints.project_id == project.id,
                ProjectControlPoints.discipline == discipline.strip().upper(),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No control points found for discipline {discipline!r}.",
            )
        await self._session.delete(row)

    async def get_for_job(self, project_id: UUID) -> list[dict[str, Any]]:
        """Return all control points for a project (no auth — internal use for job enqueue)."""
        result = await self._session.execute(
            select(ProjectControlPoints).where(
                ProjectControlPoints.project_id == project_id
            )
        )
        return [_row_to_dict(r) for r in result.scalars().all()]


def _row_to_dict(row: ProjectControlPoints) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "discipline": row.discipline,
        "reference": row.reference,
        "points": row.points or [],
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
