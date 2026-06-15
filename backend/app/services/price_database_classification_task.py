"""BackgroundTasks: clasificar archivo base de precios con OpenAI."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.price_database_file_classifier import build_text_preview, classify_price_database_file
from app.services.price_database_service import finalize_price_database_classification
from app.models.project_price_database_file import ProjectPriceDatabaseFile

logger = logging.getLogger(__name__)

_sem = asyncio.Semaphore(4)


async def run_price_database_classification_task(file_id: UUID) -> None:
    async with _sem:
        async with AsyncSessionLocal() as session:
            try:
                row = await session.get(ProjectPriceDatabaseFile, file_id)
                if row is None:
                    return
                path = Path(row.storage_key)
                if not path.is_file():
                    await finalize_price_database_classification(
                        session,
                        file_id,
                        category="",
                        confidence=0.0,
                        reason="",
                        error="Archivo no encontrado en disco",
                    )
                    await session.commit()
                    return

                settings = get_settings()
                preview = build_text_preview(path)
                cat, conf, reason = await classify_price_database_file(
                    settings,
                    original_name=row.original_name,
                    mime=row.mime,
                    file_size=int(row.file_size_bytes or path.stat().st_size),
                    text_preview=preview,
                )
                if not cat:
                    await finalize_price_database_classification(
                        session,
                        file_id,
                        category="",
                        confidence=0.0,
                        reason=reason or "",
                        error=reason or "No se pudo clasificar",
                    )
                else:
                    await finalize_price_database_classification(
                        session,
                        file_id,
                        category=cat,
                        confidence=conf,
                        reason=reason,
                        error=None,
                    )
                await session.commit()
            except Exception:
                logger.exception("run_price_database_classification_task failed for %s", file_id)
                await session.rollback()
                try:
                    async with AsyncSessionLocal() as session2:
                        await finalize_price_database_classification(
                            session2,
                            file_id,
                            category="",
                            confidence=0.0,
                            reason="",
                            error="Error interno al clasificar",
                        )
                        await session2.commit()
                except Exception:
                    logger.exception("price_db error persist failed for %s", file_id)
