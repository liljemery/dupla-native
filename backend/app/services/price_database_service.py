"""CRUD archivos base de precios por proyecto."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import Settings, get_settings
from app.domain.price_database_uploads import sanitize_price_db_filename, validate_price_db_extension
from app.domain.project_updated import touch_project_updated_at
from app.models.project import Project
from app.models.project_price_database_file import ProjectPriceDatabaseFile
from app.models.user import User
from app.services.project_service import ProjectService

logger = logging.getLogger(__name__)

CONFIDENCE_MIN = 0.42


class PriceDatabaseService:
    def __init__(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        settings: Optional[Settings] = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._projects = ProjectService(session, workspace_id)

    async def _get_project(self, user: User, project_uuid: UUID) -> Project:
        return await self._projects.get_project(user, project_uuid)

    async def upload_file(self, user: User, project_uuid: UUID, upload: UploadFile) -> ProjectPriceDatabaseFile:
        project = await self._get_project(user, project_uuid)
        safe_name = sanitize_price_db_filename(upload.filename or "file")
        validate_price_db_extension(safe_name)
        raw = await upload.read()
        if not raw:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo vacío")

        root = Path(self._settings.upload_root)
        dest_dir = root / str(project.id) / "price_db"
        dest_dir.mkdir(parents=True, exist_ok=True)
        fid = uuid.uuid4()
        storage_key = str(dest_dir / f"{fid}_{safe_name}")
        Path(storage_key).write_bytes(raw)

        row = ProjectPriceDatabaseFile(
            id=fid,
            project_id=project.id,
            storage_key=storage_key,
            original_name=upload.filename or "file",
            mime=upload.content_type,
            file_size_bytes=len(raw),
            status="processing",
            price_category=None,
            is_active=False,
            error_message=None,
            classified_at=None,
            created_by=user.id,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(row)
        touch_project_updated_at(project)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_files(self, user: User, project_uuid: UUID) -> list[ProjectPriceDatabaseFile]:
        project = await self._get_project(user, project_uuid)
        result = await self._session.execute(
            select(ProjectPriceDatabaseFile)
            .where(ProjectPriceDatabaseFile.project_id == project.id)
            .order_by(ProjectPriceDatabaseFile.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_file(self, user: User, project_uuid: UUID, file_uuid: UUID) -> None:
        project = await self._get_project(user, project_uuid)
        row = await self._session.get(ProjectPriceDatabaseFile, file_uuid)
        if row is None or row.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")
        path = Path(row.storage_key)
        await self._session.delete(row)
        touch_project_updated_at(project)
        await self._session.flush()
        try:
            if path.is_file():
                path.unlink()
        except OSError as exc:
            logger.warning("price_db unlink %s: %s", path, exc)

    async def confirm_apply(self, user: User, project_uuid: UUID) -> Project:
        """Marca confirmación en workflow_meta (presupuestos activos pueden leer este sello)."""
        project = await self._get_project(user, project_uuid)
        meta: dict = dict(project.workflow_meta) if isinstance(project.workflow_meta, dict) else {}
        price_block: dict = dict(meta.get("price_database") or {}) if isinstance(meta.get("price_database"), dict) else {}
        price_block["last_confirmed_at"] = datetime.now(timezone.utc).isoformat()
        meta["price_database"] = price_block
        project.workflow_meta = meta
        flag_modified(project, "workflow_meta")
        touch_project_updated_at(project)
        await self._session.flush()
        await self._session.refresh(project)
        return project


async def finalize_price_database_classification(
    session: AsyncSession,
    file_id: UUID,
    *,
    category: str,
    confidence: float,
    reason: str,
    error: Optional[str] = None,
) -> None:
    """Marca resultado de IA: processed + activar categoría, o error."""
    row = await session.get(ProjectPriceDatabaseFile, file_id)
    if row is None:
        return

    if error:
        row.status = "error"
        row.error_message = error[:2000]
        row.price_category = None
        row.is_active = False
        row.classified_at = datetime.now(timezone.utc)
        await session.flush()
        return

    if confidence < CONFIDENCE_MIN:
        row.status = "error"
        row.error_message = (
            f"Confianza insuficiente ({confidence:.2f} < {CONFIDENCE_MIN}). {reason}".strip()[:2000]
        )
        row.price_category = None
        row.is_active = False
        row.classified_at = datetime.now(timezone.utc)
        await session.flush()
        return

    row.price_category = category
    row.status = "processed"
    row.error_message = None
    row.classified_at = datetime.now(timezone.utc)

    await session.execute(
        update(ProjectPriceDatabaseFile)
        .where(
            ProjectPriceDatabaseFile.project_id == row.project_id,
            ProjectPriceDatabaseFile.price_category == category,
            ProjectPriceDatabaseFile.id != row.id,
        )
        .values(is_active=False)
    )
    row.is_active = True

    proj = await session.get(Project, row.project_id)
    if proj is not None:
        touch_project_updated_at(proj)

    await session.flush()
