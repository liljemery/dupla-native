"""Clasificación de archivos: extensión + disciplina por contenido + GA-FO."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import Settings, get_settings
from app.db.session import AsyncSessionLocal
from app.domain.file_discipline import discipline_bucket, parse_discipline
from app.domain.ga_fo_01_arquitectura import clear_ga_fo_approval, expected_ga_fo_item_ids
from app.domain.project_uploads import sanitize_project_original_filename
from app.models.project import Project
from app.models.project_file import ProjectFile
from app.services.local_cad_derivative_context import build_local_cad_context
from app.services.discipline_folder_service import resolve_discipline_folder_id
from app.services.motor_file_discipline import folder_rel_posix_for_file, infer_file_discipline_from_content
from app.services.motor_discipline_types import MotorDisciplineInference
from app.services.pliego_ga_fo_file_classifier import (
    classify_ga_fo_matches,
    extract_pdf_text_snippet,
    rule_based_ga_fo_matches,
)

logger = logging.getLogger(__name__)

_classify_sem = asyncio.Semaphore(2)
_scheduled_review: set[UUID] = set()

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


def _ga_fo_is_pdf(path: Path, mime: Optional[str]) -> bool:
    if path.suffix.lower() == ".pdf":
        return True
    m = (mime or "").strip().lower()
    return m == "application/pdf" or m.endswith("/pdf")


def _pdf_snippet_from_cache(cache_key: str | None) -> str | None:
    if not cache_key:
        return None
    root = (os.getenv("COORDINATION_CACHE_ROOT") or "").strip()
    if not root:
        return None
    path = Path(root) / f"{cache_key}.pdf_snippet.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    text = payload.get("text") if isinstance(payload, dict) else None
    return text if isinstance(text, str) and text.strip() else None


def _ga_fo_item_pending(states: dict, item_id: str) -> bool:
    row = states.get(item_id)
    if not isinstance(row, dict):
        return True
    estado = row.get("estado")
    return estado in (None, "", "PENDIENTE", "INCOMPLETO", "EN_REVISION")


async def _pending_ga_fo_item_ids(session: AsyncSession, project_id: UUID) -> frozenset[str]:
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return frozenset()
    spec = project.specifications_document if isinstance(project.specifications_document, dict) else {}
    ga = spec.get("ga_fo_01_arquitectura")
    states = ga.get("item_states") if isinstance(ga, dict) else {}
    states = states if isinstance(states, dict) else {}
    pending = {iid for iid in expected_ga_fo_item_ids() if _ga_fo_item_pending(states, iid)}
    return frozenset(pending)


async def _merge_ga_fo_item_complete(session: AsyncSession, project: Project, pf: ProjectFile, item_id: str) -> bool:
    spec: dict = dict(project.specifications_document) if isinstance(project.specifications_document, dict) else {}
    ga = spec.get("ga_fo_01_arquitectura")
    if not isinstance(ga, dict):
        ga = {}
    states_raw = ga.get("item_states")
    states: dict = dict(states_raw) if isinstance(states_raw, dict) else {}
    if not _ga_fo_item_pending(states, item_id):
        return False
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
    return True


async def _merge_ga_fo_items_complete(
    session: AsyncSession,
    project: Project,
    pf: ProjectFile,
    item_ids: list[str],
) -> int:
    merged = 0
    for item_id in item_ids:
        if item_id and await _merge_ga_fo_item_complete(session, project, pf, item_id):
            merged += 1
    return merged


async def _fill_pending_ga_fo_from_project_files(session: AsyncSession, project_id: UUID) -> None:
    pending = await _pending_ga_fo_item_ids(session, project_id)
    if not pending:
        return
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return
    files_result = await session.execute(
        select(ProjectFile).where(
            ProjectFile.project_id == project_id,
            ProjectFile.ingest_status == "PUBLISHED",
        )
    )
    for pf in files_result.scalars():
        cat = (pf.category or "").strip()
        if cat.startswith("pliego-ga-fo-01:"):
            continue
        matches = rule_based_ga_fo_matches(
            original_name=pf.original_name,
            discipline=pf.discipline,
            mime=pf.mime,
        )
        for item_id, _conf, _reason in matches:
            if item_id not in pending:
                continue
            await _merge_ga_fo_item_complete(session, project, pf, item_id)
            pending = pending - {item_id}
            if not pending:
                return


async def _infer_discipline_from_project_siblings(
    session: AsyncSession,
    pf: ProjectFile,
) -> tuple[str | None, int]:
    """When APS/filename fail, reuse the dominant discipline already set on sibling files."""
    result = await session.execute(
        select(ProjectFile.discipline, func.count().label("cnt"))
        .where(
            ProjectFile.project_id == pf.project_id,
            ProjectFile.id != pf.id,
            ProjectFile.ingest_status == "PUBLISHED",
            ProjectFile.discipline.isnot(None),
            ProjectFile.discipline != "",
        )
        .group_by(ProjectFile.discipline)
        .order_by(func.count().desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None, 0
    disc_str, count = row[0], int(row[1])
    parsed = parse_discipline(str(disc_str))
    return (parsed.value if parsed else None), count


async def _apply_motor_discipline_from_content(session: AsyncSession, pf: ProjectFile) -> None:
    if pf.discipline and str(pf.discipline).strip():
        return
    path = Path(pf.storage_key)
    if not path.is_file():
        return
    settings = get_settings()
    rel_posix = await folder_rel_posix_for_file(session, pf.project_id, pf.folder_id)
    safe_name = sanitize_project_original_filename(pf.original_name)
    object_key = f"dupla/{pf.project_id}/{pf.id}_{safe_name}"[:1024]
    try:
        inference = await infer_file_discipline_from_content(
            storage_path=path,
            rel_posix=rel_posix,
            settings=settings,
            object_key=object_key,
            original_name=pf.original_name,
        )
    except Exception as exc:
        logger.warning("motor discipline inference failed file=%s: %s", pf.id, exc)
        from app.services.fallback_file_discipline import infer_discipline_fallback

        inference = infer_discipline_fallback(path, original_name=pf.original_name, rel_posix=rel_posix)
        snap = dict(inference.snapshot)
        diag = dict(snap.get("extraction_diagnostics") or {})
        diag["error"] = str(exc)
        snap["extraction_diagnostics"] = diag
        inference = MotorDisciplineInference(
            discipline=inference.discipline,
            method=inference.method,
            confidence=inference.confidence,
            snapshot=snap,
        )

    pf.file_ingest_snapshot = inference.snapshot

    if inference.discipline is not None and inference.confidence >= 0.55:
        pf.discipline = inference.discipline.value
    elif inference.discipline is None:
        from app.services.fallback_file_discipline import infer_discipline_fallback

        fallback = infer_discipline_fallback(path, original_name=pf.original_name, rel_posix=rel_posix)
        if fallback.discipline is not None and fallback.confidence >= 0.55:
            pf.discipline = fallback.discipline.value
            snap = dict(inference.snapshot)
            snap["filename_fallback"] = True
            snap["discipline_method"] = fallback.method
            snap["confidence"] = fallback.confidence
            pf.file_ingest_snapshot = snap
        else:
            sibling_disc, sibling_count = await _infer_discipline_from_project_siblings(session, pf)
            if sibling_disc and sibling_count >= 1:
                pf.discipline = sibling_disc
                snap = dict(inference.snapshot)
                snap["project_sibling_hint"] = True
                snap["discipline_method"] = "project_sibling_hint"
                snap["confidence"] = 0.55
                snap["sibling_discipline_count"] = sibling_count
                pf.file_ingest_snapshot = snap
            else:
                pf.discipline = None


async def _assign_discipline_folder(session: AsyncSession, pf: ProjectFile) -> None:
    bucket = discipline_bucket(pf.discipline)
    folder_id = await resolve_discipline_folder_id(
        session,
        pf.project_id,
        bucket,
        created_by=pf.created_by,
    )
    if folder_id:
        pf.folder_id = folder_id


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
    is_cad = path.suffix.lower() in (".dwg", ".dxf")
    logger.info(
        "GA-FO pipeline start file=%s name=%s is_pdf=%s is_cad=%s",
        pf.id,
        pf.original_name,
        is_pdf,
        is_cad,
    )
    snap = pf.file_ingest_snapshot if isinstance(pf.file_ingest_snapshot, dict) else {}
    cache_key = snap.get("cad_cache_key") or snap.get("aps_cache_key")
    pdf_snippet = _pdf_snippet_from_cache(cache_key if isinstance(cache_key, str) else None)
    if not pdf_snippet:
        pdf_snippet = extract_pdf_text_snippet(path)

    cad_analysis = "unavailable"
    if is_pdf:
        logger.info("GA-FO: PDF sin traducción CAD; clasificación por nombre/MIME y texto extraído")
    elif is_cad:
        cad_analysis = build_local_cad_context(path, max_chars=settings.ga_fo_cad_context_max_chars)
        logger.info("GA-FO: contexto local ezdxf file=%s chars=%d", pf.id, len(cad_analysis))

    try:
        matches = await classify_ga_fo_matches(
            settings,
            original_name=pf.original_name,
            mime=pf.mime,
            file_size=path.stat().st_size,
            aps_analysis=cad_analysis,
            pdf_snippet=pdf_snippet,
            discipline=pf.discipline,
        )
    except Exception as exc:
        logger.warning("GA-FO classify: %s", exc)
        return
    if not matches:
        logger.info("GA-FO classify skipped: no matches file=%s", pf.id)
        return
    item_ids = [row[0] for row in matches]
    filled = await _merge_ga_fo_items_complete(session, project, pf, item_ids)
    snap_out = dict(pf.file_ingest_snapshot) if isinstance(pf.file_ingest_snapshot, dict) else {}
    snap_out["ga_fo_matched_items"] = item_ids
    snap_out["ga_fo_multi_v1"] = True
    pf.file_ingest_snapshot = snap_out
    await _fill_pending_ga_fo_from_project_files(session, pf.project_id)
    logger.info(
        "GA-FO auto-filled items=%s file=%s filled=%s",
        item_ids,
        pf.id,
        filled,
    )


def schedule_file_review(
    file_id: UUID,
    *,
    skip_folder_assign: bool = False,
    ga_fo_only: bool = False,
) -> bool:
    if file_id in _scheduled_review:
        return False
    _scheduled_review.add(file_id)

    async def _runner() -> None:
        try:
            await run_file_classification_task(
                file_id,
                skip_folder_assign=skip_folder_assign,
                ga_fo_only=ga_fo_only,
            )
        finally:
            _scheduled_review.discard(file_id)

    asyncio.create_task(_runner())
    return True


async def run_file_classification_task(
    file_id: UUID,
    *,
    skip_folder_assign: bool = False,
    ga_fo_only: bool = False,
) -> None:
    """BackgroundTasks: extensión + disciplina por contenido + GA-FO."""
    logger.info(
        "run_file_classification_task start file_id=%s ga_fo_only=%s",
        file_id,
        ga_fo_only,
    )
    if ga_fo_only:
        async with AsyncSessionLocal() as session:
            try:
                pf = await session.get(ProjectFile, file_id)
                if pf is None:
                    return
                await _run_ga_fo_autofill_from_upload(session, pf)
                await session.commit()
            except Exception:
                logger.exception("run_file_classification_task ga-fo-only failed for %s", file_id)
                await session.rollback()
        return

    async with _classify_sem:
        async with AsyncSessionLocal() as session:
            try:
                pf = await session.get(ProjectFile, file_id)
                if pf is None:
                    return
                await _classify_and_merge_pliego_hint(session, pf)
                await _apply_motor_discipline_from_content(session, pf)
                if not skip_folder_assign:
                    await _assign_discipline_folder(session, pf)
                await session.commit()
            except Exception:
                logger.exception("run_file_classification_task discipline phase failed for %s", file_id)
                await session.rollback()
                return

    async with AsyncSessionLocal() as session:
        try:
            pf = await session.get(ProjectFile, file_id)
            if pf is None:
                return
            await _run_ga_fo_autofill_from_upload(session, pf)
            await session.commit()
        except Exception:
            logger.exception("run_file_classification_task ga-fo phase failed for %s", file_id)
            await session.rollback()



async def requeue_files_needing_review(*, project_id: UUID | None = None) -> int:
    """Re-enqueue PUBLISHED files missing discipline ingest and/or pliego GA-FO link."""
    async with AsyncSessionLocal() as session:
        stmt = select(ProjectFile).where(ProjectFile.ingest_status == "PUBLISHED")
        if project_id is not None:
            stmt = stmt.where(ProjectFile.project_id == project_id)
        result = await session.execute(stmt)
        files = list(result.scalars())

        pending_by_project: dict[UUID, frozenset[str]] = {}
        queued = 0
        for pf in files:
            cat = (pf.category or "").strip()
            if cat.startswith("pliego-ga-fo-01:"):
                continue

            if pf.project_id not in pending_by_project:
                pending_by_project[pf.project_id] = await _pending_ga_fo_item_ids(session, pf.project_id)

            snap = pf.file_ingest_snapshot if isinstance(pf.file_ingest_snapshot, dict) else None
            has_classified = bool(snap and snap.get("classified_at"))
            has_discipline = bool(pf.discipline and str(pf.discipline).strip())
            pending_items = pending_by_project.get(pf.project_id, frozenset())
            has_multi = bool(snap and snap.get("ga_fo_multi_v1"))
            rule_hits = (
                {row[0] for row in rule_based_ga_fo_matches(
                    original_name=pf.original_name,
                    discipline=pf.discipline,
                    mime=pf.mime,
                )}
                if has_classified
                else set()
            )
            unmatched_rule_pending = bool(pending_items & rule_hits)

            needs_full = not has_discipline or not has_classified or pf.folder_id is None
            needs_ga_fo = has_classified and (not has_multi or unmatched_rule_pending)

            if needs_full:
                if schedule_file_review(pf.id):
                    queued += 1
            elif needs_ga_fo:
                if schedule_file_review(pf.id, ga_fo_only=True):
                    queued += 1

    if queued:
        scope = f"project={project_id}" if project_id else "all"
        logger.info("requeue_files_needing_review scope=%s queued=%s", scope, queued)
    return queued


async def requeue_pending_discipline_classifications() -> None:
    await requeue_files_needing_review()
