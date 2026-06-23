from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import require_budget_access
from app.models.user import User
from app.schemas.clash_viewer import (
    ApsFileManifestRefreshResponse,
    ApsManifestResponse,
    ApsTokenResponse,
    ApsTranslateResponse,
)
from app.services.aps_vie_service import ApsViewerService

router = APIRouter(prefix="/api", tags=["aps-viewer"])


@router.get("/aps/token", response_model=ApsTokenResponse)
async def aps_token(current: Annotated[User, Depends(get_current_user)]) -> ApsTokenResponse:
    return await ApsViewerService().token()


@router.get("/projects/{project_id}/aps/manifest", response_model=ApsManifestResponse)
async def aps_manifest(
    project_id: str,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApsManifestResponse:
    if project_id == "demo":
        return ApsManifestResponse(status="demo", progress="complete", urn="demo", derivatives=[], viewable_guid=None)
    try:
        project_uuid = UUID(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from exc
    return await ApsViewerService(session).manifest(project_uuid)


@router.post("/projects/{project_id}/aps/translate", response_model=ApsTranslateResponse)
async def aps_translate_project_primary_file(
    project_id: str,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApsTranslateResponse:
    project_uuid = _parse_uuid(project_id)
    from sqlalchemy import select
    from app.models.project_file import ProjectFile

    result = await session.execute(
        select(ProjectFile)
        .where(ProjectFile.project_id == project_uuid)
        .order_by(ProjectFile.created_at.asc())
        .limit(1)
    )
    file = result.scalar_one_or_none()
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project file not found")
    return await ApsViewerService(session).translate_file(project_uuid, file.id)


@router.post("/projects/{project_id}/files/{file_id}/aps/translate", response_model=ApsTranslateResponse)
async def aps_translate_file(
    project_id: str,
    file_id: str,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApsTranslateResponse:
    return await ApsViewerService(session).translate_file(_parse_uuid(project_id), _parse_uuid(file_id))


@router.post("/projects/{project_id}/files/{file_id}/aps/refresh-manifest", response_model=ApsFileManifestRefreshResponse)
async def aps_refresh_file_manifest(
    project_id: str,
    file_id: str,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApsFileManifestRefreshResponse:
    return await ApsViewerService(session).refresh_file_manifest(_parse_uuid(project_id), _parse_uuid(file_id))


def _parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from exc
