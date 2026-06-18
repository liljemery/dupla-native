from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.config import Settings, get_settings
from app.domain.project_uploads import sanitize_project_original_filename
from app.models.project_file import ProjectFile
from app.schemas.clash_viewer import (
    ApsFileManifestRefreshResponse,
    ApsManifestResponse,
    ApsTokenResponse,
    ApsTranslateResponse,
    ViewerConfigResponse,
    ViewerFileConfig,
)
from app.services.aps_derivative_pipeline import (
    APS_AUTH,
    APS_MD_BASE,
    _aps_token,
    _ensure_bucket,
    _fetch_manifest,
    _normalize_bucket_key,
    _oss_upload_file,
    _oss_wait_object_readable,
    _post_translate_job,
    _translation_views_list,
)
from app.services.clash_viewer_adapter import aps_urn_for_object


class ApsViewerService:
    def __init__(self, session: AsyncSession | None = None, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    async def token(self) -> ApsTokenResponse:
        cid = (self._settings.aps_client_id or "").strip()
        secret = (self._settings.aps_client_secret or "").strip()
        if not cid or not secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="APS credentials are not configured",
            )
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                APS_AUTH,
                data={
                    "client_id": cid,
                    "client_secret": secret,
                    "grant_type": "client_credentials",
                    "scope": "data:read viewables:read",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"APS token request failed with status {response.status_code}",
            )
        data = response.json()
        return ApsTokenResponse(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in"),
        )

    async def viewer_config(self, project_id: UUID, coordinate_space: str = "world") -> ViewerConfigResponse:
        files, warnings = await self._project_viewer_files(project_id)
        if not files:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Modelo no traducido en APS todavía",
            )
        primary = files[0]
        if not primary.viewable_guid:
            warnings.append("MISSING_VIEWABLE_GUID")
        return ViewerConfigResponse(
            project_id=str(project_id),
            urn=primary.urn,
            default_viewable_guid=primary.viewable_guid,
            viewer_mode="2d",
            default_coordinate_space="model" if coordinate_space == "model" else "world",
            clashes_url=f"/api/projects/{project_id}/viewer/clashes?coordinate_space={coordinate_space}",
            manifest_url=f"/api/projects/{project_id}/aps/manifest",
            viewables=files,
            warnings=list(dict.fromkeys(warnings)),
        )

    async def manifest(self, project_id: UUID) -> ApsManifestResponse:
        files, _warnings = await self._project_viewer_files(project_id)
        if not files:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Modelo no traducido en APS todavía",
            )
        urn = files[0].urn
        token = await self.token()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{APS_MD_BASE}/designdata/{urn}/manifest",
                headers={"Authorization": f"Bearer {token.access_token}"},
            )
        if response.status_code == 404:
            return ApsManifestResponse(status="missing", progress=None, urn=urn, derivatives=[])
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"APS manifest request failed with status {response.status_code}",
            )
        data = response.json()
        viewable_guid = _first_viewable_guid(data)
        return ApsManifestResponse(
            status=str(data.get("status") or "unknown"),
            progress=data.get("progress"),
            urn=urn,
            derivatives=data.get("derivatives") if isinstance(data.get("derivatives"), list) else [],
            viewable_guid=viewable_guid,
        )

    async def translate_file(self, project_id: UUID, file_id: UUID) -> ApsTranslateResponse:
        file = await self._file_for_project(project_id, file_id)
        bucket = _normalize_bucket_key((file.aps_bucket_key or self._settings.aps_bucket_name or "").strip())
        if not bucket:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="APS bucket is not configured")
        object_key = file.aps_object_key or _object_key_for_file(file)
        object_id = _object_id(bucket, object_key)
        urn = file.aps_urn or aps_urn_for_object(bucket, object_key)
        disk_path = Path(file.storage_key)
        if not disk_path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project file is missing on disk")

        async with httpx.AsyncClient() as client:
            token0 = await _aps_token(client, self._settings)
            if not token0:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="APS credentials are not configured")
            token_box = [token0]
            if not await _ensure_bucket(client, self._settings, token_box, bucket):
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="APS bucket could not be created or read")
            if not await _oss_upload_file(client, self._settings, token_box, bucket, object_key, disk_path, file.mime):
                file.aps_derivative_status = "upload_failed"
                await self._session.commit()
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="APS upload failed")
            await _oss_wait_object_readable(client, self._settings, token_box, bucket, object_key)
            posted = await _post_translate_job(client, self._settings, token_box, urn, _translation_views_list(self._settings))
            status_text = "submitted" if posted else "submit_failed"

        file.aps_bucket_key = bucket
        file.aps_object_key = object_key
        file.aps_object_id = object_id
        file.aps_urn = urn
        file.aps_derivative_status = status_text
        file.aps_last_translated_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(file)
        return ApsTranslateResponse(
            project_id=str(project_id),
            file_id=str(file.id),
            filename=file.original_name,
            aps_bucket_key=file.aps_bucket_key or bucket,
            aps_object_key=file.aps_object_key or object_key,
            aps_object_id=file.aps_object_id or object_id,
            aps_urn=file.aps_urn or urn,
            aps_derivative_status=file.aps_derivative_status or status_text,
            aps_viewable_guid=file.aps_viewable_guid,
        )

    async def refresh_file_manifest(self, project_id: UUID, file_id: UUID) -> ApsFileManifestRefreshResponse:
        file = await self._file_for_project(project_id, file_id)
        urn = (file.aps_urn or "").strip()
        if not urn:
            bucket = _normalize_bucket_key((file.aps_bucket_key or self._settings.aps_bucket_name or "").strip())
            object_key = file.aps_object_key or _object_key_for_file(file)
            urn = aps_urn_for_object(bucket, object_key)
        async with httpx.AsyncClient() as client:
            token0 = await _aps_token(client, self._settings)
            if not token0:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="APS credentials are not configured")
            manifest = await _fetch_manifest(client, self._settings, [token0], urn)
        if manifest is None:
            file.aps_derivative_status = "missing"
            file.aps_manifest_json = None
            viewable_guid = None
            progress = None
        else:
            file.aps_manifest_json = manifest
            file.aps_derivative_status = str(manifest.get("status") or "unknown")
            viewable_guid = _first_viewable_guid(manifest)
            if viewable_guid:
                file.aps_viewable_guid = viewable_guid
            progress = manifest.get("progress")
        file.aps_urn = urn
        await self._session.commit()
        await self._session.refresh(file)
        return ApsFileManifestRefreshResponse(
            project_id=str(project_id),
            file_id=str(file.id),
            aps_urn=urn,
            aps_derivative_status=file.aps_derivative_status or "unknown",
            aps_viewable_guid=file.aps_viewable_guid,
            progress=progress,
        )

    async def _file_for_project(self, project_id: UUID, file_id: UUID) -> ProjectFile:
        if self._session is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database session is required")
        result = await self._session.execute(
            select(ProjectFile).where(ProjectFile.project_id == project_id, ProjectFile.id == file_id)
        )
        file = result.scalar_one_or_none()
        if file is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project file not found")
        return file

    async def _project_viewer_files(self, project_id: UUID) -> tuple[list[ViewerFileConfig], list[str]]:
        if self._session is None:
            return [], []
        result = await self._session.execute(
            select(ProjectFile)
            .where(ProjectFile.project_id == project_id)
            .order_by(ProjectFile.created_at.asc())
        )
        files = [f for f in result.scalars().all() if _is_viewable_file(f)]
        bucket = _normalize_bucket_key(self._settings.aps_bucket_name or "")
        warnings: list[str] = []
        out: list[ViewerFileConfig] = []
        for file in files:
            urn = (file.aps_urn or "").strip()
            if not urn:
                effective_bucket = _normalize_bucket_key(file.aps_bucket_key or bucket)
                if not effective_bucket:
                    continue
                urn = aps_urn_for_object(effective_bucket, file.aps_object_key or _object_key_for_file(file))
                warnings.append("USING_DERIVED_URN_FALLBACK")
            viewable_guid = _viewable_guid_from_file(file) or _first_viewable_guid(file.aps_manifest_json or {})
            out.append(
                ViewerFileConfig(
                    file_id=str(file.id),
                    filename=file.original_name,
                    urn=urn,
                    viewable_guid=viewable_guid,
                    sheet_id=None,
                    discipline=file.discipline,
                )
            )
        return out, warnings


def _is_viewable_file(file: ProjectFile) -> bool:
    suffix = Path(file.original_name or "").suffix.lower()
    return suffix in {".dwg", ".dxf", ".pdf", ".ifc"}


def _object_key_for_file(file: ProjectFile) -> str:
    safe_name = sanitize_project_original_filename(file.original_name)
    return f"dupla/{file.project_id}/{file.id}_{safe_name}"[:1024]


def _object_id(bucket_key: str, object_key: str) -> str:
    return f"urn:adsk.objects:os.object:{bucket_key}/{object_key}"


def _viewable_guid_from_file(file: ProjectFile) -> str | None:
    # No schema column exists yet. Preserve forward compatibility if later stored
    # in description or JSON-like metadata fields.
    for attr in ("aps_viewable_guid", "viewable_guid"):
        value = getattr(file, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_viewable_guid(manifest: dict[str, Any]) -> str | None:
    two_d: list[str] = []
    fallback: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            guid = node.get("guid")
            role = str(node.get("role") or "").lower()
            node_type = str(node.get("type") or "").lower()
            name = str(node.get("name") or "").lower()
            if isinstance(guid, str) and guid and node_type == "geometry":
                if role in {"2d", "sheet"} or "sheet" in name or "layout" in name:
                    two_d.append(guid)
                else:
                    fallback.append(guid)
            for child in node.get("children") or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(manifest.get("derivatives") or [])
    return two_d[0] if two_d else (fallback[0] if fallback else None)
