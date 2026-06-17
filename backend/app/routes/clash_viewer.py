from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.domain.clash_workflow_enums import ClashStatus
from app.models.project_clash_item import ProjectClashItem
from app.models.project_clash_job import ProjectClashJob
from app.models.user import User
from app.schemas.clash_viewer import (
    ClashMappingCandidatesResponse,
    ClashStatusUpdate,
    ClashViewerResponse,
    MappingWarning,
    ViewerConfigResponse,
    ViewerCoordinateSettings,
)
from app.services.aps_vie_service import ApsViewerService
from app.services.clash_element_mapping_service import ClashElementMappingService
from app.services.clash_viewer_adapter import ClashViewerAdapter
from app.services.viewer_coordinate_settings_service import ViewerCoordinateSettingsService, default_coordinate_settings

router = APIRouter(prefix="/api/projects", tags=["clash-viewer"])


def _static_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "static" / "aps_viewer"


def _parse_project_id(project_id: str) -> UUID:
    try:
        return UUID(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from exc


@router.get("/{project_id}/viewer")
async def aps_clash_viewer(
    project_id: str,
    coordinate_space: Annotated[str, Query(pattern="^(world|model)$")] = "world",
    debug: bool = False,
) -> FileResponse:
    index = _static_dir() / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Viewer not installed")
    return FileResponse(index)


@router.get("/demo/viewer/config", response_model=ViewerConfigResponse)
async def demo_viewer_config(
    coordinate_space: Annotated[str, Query(pattern="^(world|model)$")] = "world",
) -> ViewerConfigResponse:
    return ViewerConfigResponse(
        project_id="demo",
        urn="demo",
        default_viewable_guid=None,
        viewer_mode="2d",
        default_coordinate_space="model" if coordinate_space == "model" else "world",
        clashes_url=f"/api/projects/demo/viewer/clashes?coordinate_space={coordinate_space}",
        manifest_url="/api/projects/demo/aps/manifest",
        warnings=["DEMO_MODE_NO_APS_MODEL"],
    )


@router.get("/demo/viewer/clashes", response_model=ClashViewerResponse)
async def demo_viewer_clashes(
    coordinate_space: Annotated[str, Query(pattern="^(world|model)$")] = "world",
    severity: str | None = None,
    discipline: str | None = None,
) -> ClashViewerResponse:
    from app.services.clash_viewer_demo import demo_clashes_response

    return demo_clashes_response(coordinate_space=coordinate_space, severity=severity, discipline=discipline)


@router.get("/demo/viewer/coordinate-settings", response_model=ViewerCoordinateSettings)
async def demo_get_coordinate_settings(
    coordinate_space: Annotated[str, Query(pattern="^(world|model)$")] = "world",
) -> ViewerCoordinateSettings:
    return default_coordinate_settings(coordinate_space)


@router.put("/demo/viewer/coordinate-settings", response_model=ViewerCoordinateSettings)
async def demo_put_coordinate_settings(body: ViewerCoordinateSettings) -> ViewerCoordinateSettings:
    return body


@router.post("/demo/viewer/coordinate-settings/reset", response_model=ViewerCoordinateSettings)
async def demo_reset_coordinate_settings(
    coordinate_space: Annotated[str, Query(pattern="^(world|model)$")] = "world",
) -> ViewerCoordinateSettings:
    return default_coordinate_settings(coordinate_space)


@router.get("/{project_id}/viewer/config", response_model=ViewerConfigResponse)
async def viewer_config(
    project_id: str,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    coordinate_space: Annotated[str, Query(pattern="^(world|model)$")] = "world",
) -> ViewerConfigResponse:
    if project_id == "demo":
        return await demo_viewer_config(coordinate_space)
    return await ApsViewerService(session).viewer_config(_parse_project_id(project_id), coordinate_space)


@router.get("/{project_id}/viewer/clashes", response_model=ClashViewerResponse)
async def viewer_clashes(
    project_id: str,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    coordinate_space: Annotated[str, Query(pattern="^(world|model)$")] = "world",
    severity: str | None = None,
    discipline: str | None = None,
    include_resolved: bool = False,
) -> ClashViewerResponse:
    if project_id == "demo":
        return await demo_viewer_clashes(coordinate_space, severity, discipline)
    return await ClashViewerAdapter(session).build_response(
        _parse_project_id(project_id),
        coordinate_space=coordinate_space,
        severity=severity,
        discipline=discipline,
        include_resolved=include_resolved,
    )


@router.get("/{project_id}/viewer/coordinate-settings", response_model=ViewerCoordinateSettings)
async def get_coordinate_settings(
    project_id: str,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    coordinate_space: Annotated[str, Query(pattern="^(world|model)$")] = "world",
) -> ViewerCoordinateSettings:
    if project_id == "demo":
        return default_coordinate_settings(coordinate_space)
    return await ViewerCoordinateSettingsService(session).get(_parse_project_id(project_id), coordinate_space)


@router.put("/{project_id}/viewer/coordinate-settings", response_model=ViewerCoordinateSettings)
async def put_coordinate_settings(
    project_id: str,
    body: ViewerCoordinateSettings,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ViewerCoordinateSettings:
    if project_id == "demo":
        return body
    return await ViewerCoordinateSettingsService(session).upsert(
        _parse_project_id(project_id),
        body,
        created_by=current.id,
    )


@router.post("/{project_id}/viewer/coordinate-settings/reset", response_model=ViewerCoordinateSettings)
async def reset_coordinate_settings(
    project_id: str,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    coordinate_space: Annotated[str, Query(pattern="^(world|model)$")] = "world",
) -> ViewerCoordinateSettings:
    if project_id == "demo":
        return default_coordinate_settings(coordinate_space)
    return await ViewerCoordinateSettingsService(session).reset(_parse_project_id(project_id), coordinate_space)


@router.get("/{project_id}/viewer/clashes/{clash_id}/mapping-candidates", response_model=ClashMappingCandidatesResponse)
async def mapping_candidates(
    project_id: str,
    clash_id: str,
    current: Annotated[User, Depends(get_current_user)],
) -> ClashMappingCandidatesResponse:
    if project_id != "demo":
        _parse_project_id(project_id)
    await ClashElementMappingService().find_candidates_by_bbox(UUID(int=0), {"clash_id": clash_id})
    return ClashMappingCandidatesResponse(
        clash_id=clash_id,
        candidates=[],
        strategy="not_implemented",
        warnings=[
            MappingWarning(
                code="DBID_MAPPING_NOT_IMPLEMENTED",
                message="El viewer funciona por bbox. El mapeo exacto a dbId queda para la siguiente fase.",
            )
        ],
    )


@router.post("/{project_id}/viewer/clashes/{clash_id}/status")
async def update_viewer_clash_status(
    project_id: str,
    clash_id: str,
    body: ClashStatusUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    if project_id == "demo":
        return {"status": body.status, "comment": body.comment or ""}

    project_uuid = _parse_project_id(project_id)
    target_status = {
        "open": ClashStatus.DETECTED.value,
        "reviewed": ClashStatus.NEEDS_REVIEW.value,
        "ignored": ClashStatus.FALSE_POSITIVE.value,
        "resolved": ClashStatus.RESOLVED.value,
    }[body.status]
    job_result = await session.execute(
        select(ProjectClashJob)
        .where(ProjectClashJob.project_id == project_uuid)
        .order_by(ProjectClashJob.created_at.desc())
        .limit(1)
    )
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No clash job found")

    predicates = [ProjectClashItem.clash_code == clash_id]
    clash_uuid = _uuid_or_none(clash_id)
    if clash_uuid is not None:
        predicates.append(ProjectClashItem.id == clash_uuid)
    item_result = await session.execute(
        select(ProjectClashItem).where(ProjectClashItem.job_id == job.id, or_(*predicates))
    )
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clash not found")
    item.status = target_status
    if body.comment:
        item.observation = f"{item.observation}\n{body.comment}" if item.observation else body.comment
    await session.commit()
    return {"status": body.status, "comment": body.comment or ""}


def _uuid_or_none(value: str):
    try:
        return UUID(value)
    except ValueError:
        return None
