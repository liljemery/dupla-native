"""Clasificación de archivos: extensión + sugerencias, APS/Model Derivative + OpenAI → pliego GA-FO-01."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import Settings, get_settings
from app.db.session import AsyncSessionLocal
from app.domain.ga_fo_01_arquitectura import clear_ga_fo_approval
from app.domain.project_uploads import sanitize_project_original_filename
from app.models.project import Project
from app.models.project_file import ProjectFile
from app.services.aps_derivative_pipeline import run_aps_derivative_context
from app.services.pliego_ga_fo_file_classifier import (
    classify_ga_fo_item,
    extract_pdf_text_snippet,
)

logger = logging.getLogger(__name__)

_classify_sem = asyncio.Semaphore(5)

FILE_CAT_PDF = "PDF_DOCUMENT"
FILE_CAT_CAD = "CAD_DRAWING"
FILE_CAT_BIM = "BIM_MODEL"
FILE_CAT_LEGAL = "LEGAL_TECHNICAL"

SUGGESTIONS_KEY = "file_classification_suggestions"


def _category_from_path(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return FILE_CAT_PDF
    if ext in (".dwg", ".dxf"):
        return FILE_CAT_CAD
    if ext == ".ifc":
        return FILE_CAT_BIM
    if ext == ".docx":
        return FILE_CAT_LEGAL
    return None


async def _classify_and_merge_pliego_hint(session: AsyncSession, pf: ProjectFile) -> None:
    path = Path(pf.storage_key)
    if not path.is_file():
        return
    kind = _category_from_path(path)
    if kind is None:
        return
    if pf.category and str(pf.category).strip():
        return
    pf.category = kind

    result = await session.execute(select(Project).where(Project.id == pf.project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return
    spec: dict = dict(project.specifications_document) if isinstance(project.specifications_document, dict) else {}
    hints: list = list(spec.get(SUGGESTIONS_KEY) or [])
    fid = str(pf.id)
    hints = [h for h in hints if isinstance(h, dict) and str(h.get("file_uuid")) != fid]
    hints.append(
        {
            "file_uuid": fid,
            "category": kind,
            "name": pf.original_name,
        }
    )
    spec[SUGGESTIONS_KEY] = hints[-80:]
    project.specifications_document = spec
    flag_modified(project, "specifications_document")


def _aps_configured(settings: Settings) -> bool:
    return bool(
        (settings.aps_client_id or "").strip()
        and (settings.aps_client_secret or "").strip()
        and (settings.aps_bucket_name or "").strip()
    )


def _ga_fo_is_pdf(path: Path, mime: Optional[str]) -> bool:
    if path.suffix.lower() == ".pdf":
        return True
    m = (mime or "").strip().lower()
    return m == "application/pdf" or m.endswith("/pdf")


async def _merge_ga_fo_item_complete(session: AsyncSession, project: Project, pf: ProjectFile, item_id: str) -> None:
    spec: dict = dict(project.specifications_document) if isinstance(project.specifications_document, dict) else {}
    ga = spec.get("ga_fo_01_arquitectura")
    if not isinstance(ga, dict):
        ga = {}
    states_raw = ga.get("item_states")
    states: dict = dict(states_raw) if isinstance(states_raw, dict) else {}
    fid = str(pf.id)
    prev = states.get(item_id) if isinstance(states.get(item_id), dict) else {}
    states[item_id] = {
        **prev,
        "estado": "COMPLETO",
        "file_uuid": fid,
        "file_name": pf.original_name,
    }
    ga["item_states"] = states
    ga["schema_version"] = 1
    clear_ga_fo_approval(ga)
    spec["ga_fo_01_arquitectura"] = ga
    project.specifications_document = spec
    flag_modified(project, "specifications_document")


async def _run_ga_fo_autofill_from_upload(session: AsyncSession, pf: ProjectFile) -> None:
    cat = (pf.category or "").strip()
    if cat.startswith("pliego-ga-fo-01:"):
        return
    settings = get_settings()
    if not (settings.openai_api_key or "").strip():
        logger.warning(
            "GA-FO autofill omitido: OPENAI_API_KEY vacía o ausente (file=%s project_id=%s)",
            pf.id,
            pf.project_id,
        )
        return
    path = Path(pf.storage_key)
    if not path.is_file():
        return
    result = await session.execute(select(Project).where(Project.id == pf.project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return

    is_pdf = _ga_fo_is_pdf(path, pf.mime)
    logger.info(
        "GA-FO pipeline start file=%s name=%s aps_configured=%s is_pdf=%s",
        pf.id,
        pf.original_name,
        _aps_configured(settings),
        is_pdf,
    )
    pdf_snippet = extract_pdf_text_snippet(path)
    aps_analysis = "unavailable"
    if is_pdf:
        logger.info("GA-FO: PDF sin APS (Model Derivative); clasificación por nombre/MIME y texto extraído")
    elif _aps_configured(settings):
        safe_name = sanitize_project_original_filename(pf.original_name)
        object_key = f"dupla/{pf.project_id}/{pf.id}_{safe_name}"[:1024]
        if settings.aps_auto_unique_object_name:
            suffix = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            object_key = f"dupla/{pf.project_id}/{pf.id}_{suffix}_{safe_name}"[:1024]
        try:
            aps_analysis = await run_aps_derivative_context(
                settings,
                path,
                settings.aps_bucket_name or "",
                object_key,
                pf.mime,
            )
        except Exception as exc:
            logger.warning("APS pipeline: %s", exc)
            aps_analysis = "unavailable"

    try:
        item_id, conf, reason = await classify_ga_fo_item(
            settings,
            original_name=pf.original_name,
            mime=pf.mime,
            file_size=path.stat().st_size,
            aps_analysis=aps_analysis,
            pdf_snippet=pdf_snippet,
        )
    except Exception as exc:
        logger.warning("GA-FO classify: %s", exc)
        return
    if not item_id:
        logger.info("GA-FO classify skipped: conf=%s reason=%s", conf, reason)
        return
    await _merge_ga_fo_item_complete(session, project, pf, item_id)
    logger.info("GA-FO auto-filled item=%s file=%s conf=%s", item_id, pf.id, conf)


async def run_file_classification_task(file_id: UUID) -> None:
    """BackgroundTasks: extensión + GA-FO (APS + OpenAI)."""
    logger.info("run_file_classification_task start file_id=%s", file_id)
    async with _classify_sem:
        async with AsyncSessionLocal() as session:
            try:
                pf = await session.get(ProjectFile, file_id)
                if pf is None:
                    return
                await _classify_and_merge_pliego_hint(session, pf)
                await _run_ga_fo_autofill_from_upload(session, pf)
                await session.commit()
            except Exception:
                logger.exception("run_file_classification_task failed for %s", file_id)
                await session.rollback()
