"""Budget orchestration service.

Bridges the main platform to the processor microservice:
- enqueue_budget_job: forwards file bytes to processor, stores RQ job_id.
- sync_job_status: polls processor for current job state, persists result.
- get_latest_job: returns most recent ProjectBudgetJob for a project.
- get_budget_result: returns the completed budget JSONB.
"""
from __future__ import annotations

import logging
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import get_settings
from app.domain.budget_cad_attachments import (
    ReadableCache,
    auxiliary_dxf_candidates,
    budget_dxf_stems,
    ingest_snapshot,
    refresh_cad_gate_snapshots,
    unusable_dwg_names,
)
from app.domain.budget_pipeline_meta import (
    budget_result_qualifies_for_volumetry,
    sync_volumetry_from_completed_job,
)
from app.models.project_budget_job import ProjectBudgetJob
from app.models.project_file import ProjectFile
from app.models.user import User
from app.services.project_service import ProjectService

logger = logging.getLogger(__name__)

_BUDGET_ALL_DISCIPLINE_ALIASES = {
    "todas",
    "todos",
    "todo",
    "all",
    "*",
    "multidisciplina",
    "multidisciplinas",
}
_BUDGET_AUTO_DISCIPLINE_ALIASES = {"auto", "infer", "inferir", "automatico"}
_BUDGET_DISCIPLINE_ALIASES: dict[str, str] = {
    "arquitectura": "arquitectura",
    "arquitectonica": "arquitectura",
    "arquitectonico": "arquitectura",
    "arq": "arquitectura",
    "estructura": "estructura",
    "estructural": "estructura",
    "est": "estructura",
    "electrico": "electrico",
    "electrica": "electrico",
    "electricidad": "electrico",
    "elec": "electrico",
    "sanitario": "sanitario",
    "sanitaria": "sanitario",
    "plomeria": "sanitario",
    "hidrosanitario": "sanitario",
    "agua potable": "sanitario",
    "aguas negras": "sanitario",
    "drenaje": "sanitario",
    "desague": "sanitario",
}
_BUDGET_DISCIPLINE_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("agua potable", "aguas negras", "hidrosanit", "sanitar", "plomer", "drenaje", "desague", "hs-"),
        "sanitario",
    ),
    (
        ("electrico", "electrica", "electricidad", "luminaria", "tomacorriente", "panel", "e-"),
        "electrico",
    ),
    (
        ("estructura", "estructural", "cimiento", "ciment", "zapata", "viga", "columna", "losa", "encofrado", "es-"),
        "estructura",
    ),
    (
        ("arquitectura", "arquitectonica", "arq", "planta", "fachada", "puerta", "ventana", "a-"),
        "arquitectura",
    ),
)


def _fold_text(value: str | None) -> str:
    """Lowercase and remove accents so UI/backend aliases stay stable."""
    text = (value or "").strip().lower()
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _infer_budget_discipline_from_files(files: list[ProjectFile]) -> str:
    probes: list[str] = []
    for pf in files:
        probes.append(str(pf.discipline or ""))
        probes.append(str(pf.original_name or ""))

    for probe in probes:
        low = _fold_text(probe)
        for keywords, canonical in _BUDGET_DISCIPLINE_HINTS:
            if any(keyword in low for keyword in keywords):
                return canonical
        for alias, canonical in _BUDGET_DISCIPLINE_ALIASES.items():
            if alias and alias in low:
                return canonical

    return "arquitectura"


def _normalize_budget_discipline(raw: str | None, files: list[ProjectFile]) -> str:
    """Return the canonical processor discipline for a budget job.

    The processor now treats an empty discipline as base_extraction. That is
    useful internally, but /budget/jobs must always request a real budget mode
    so the UI does not render a completed empty budget. For this endpoint,
    omitted/empty means "todas" to preserve the existing user workflow.
    """
    value = _fold_text(raw)
    if value in _BUDGET_AUTO_DISCIPLINE_ALIASES:
        return _infer_budget_discipline_from_files(files)
    if not value or value in _BUDGET_ALL_DISCIPLINE_ALIASES:
        return "todas"

    normalized = _BUDGET_DISCIPLINE_ALIASES.get(value)
    if normalized:
        return normalized
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            "Disciplina invalida para presupuesto. Usa arquitectura, "
            "estructura, electrico, sanitario o todas."
        ),
    )


class BudgetService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self._session = session
        self._project_svc = ProjectService(session, workspace_id)

    async def _get_project_file(self, project_id: UUID, file_uuid: UUID) -> Optional[ProjectFile]:
        result = await self._session.execute(
            select(ProjectFile).where(
                ProjectFile.id == file_uuid,
                ProjectFile.project_id == project_id,
            )
        )
        return result.scalar_one_or_none()

    async def enqueue_budget_job(
        self,
        user: User,
        project_uuid: UUID,
        discipline: Optional[str] = None,
    ) -> ProjectBudgetJob:
        project = await self._project_svc.get_project(user, project_uuid)

        result = await self._session.execute(
            select(ProjectFile)
            .where(ProjectFile.project_id == project.id)
            .order_by(ProjectFile.created_at.asc())
        )
        all_files = list(result.scalars().all())
        budget_files = [pf for pf in all_files if pf.counts_for_budget]

        if not budget_files:
            if all_files:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "No hay archivos válidos para presupuesto. Los subidos tras la fase de presupuesto "
                        "no se incluyen en el cálculo."
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El proyecto no tiene archivos adjuntos",
            )

        budget_discipline = _normalize_budget_discipline(discipline, budget_files)

        upload_root = Path(get_settings().upload_root)
        readable_cache: ReadableCache = {}
        if refresh_cad_gate_snapshots(budget_files):
            await self._session.flush()
        dxf_stems_in_budget = budget_dxf_stems(budget_files)
        unusable = unusable_dwg_names(budget_files, upload_root, readable_cache=readable_cache)
        dwg_count = sum(1 for pf in budget_files if (pf.original_name or "").lower().endswith(".dwg"))
        if dwg_count and len(unusable) / dwg_count > 0.5:
            sample = ", ".join(unusable[:8])
            more = f" (+{len(unusable) - 8} más)" if len(unusable) > 8 else ""
            tool_missing = any(
                str(ingest_snapshot(pf).get("cad_conversion_error_code") or "") == "TOOL_MISSING"
                for pf in budget_files
                if (pf.original_name or "").lower().endswith(".dwg")
            )
            detail = (
                "La mayoría de los DWG no tienen geometría usable para presupuesto. "
                "Exporta DXF desde CAD y súbelos junto a cada DWG. "
                f"Archivos sin DXF: {sample}{more}"
            )
            if tool_missing:
                detail += (
                    " En desarrollo local instala LibreDWG (macOS: brew install libredwg) "
                    "y vuelve a pulsar Procesar, o sube los DXF manualmente."
                )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=detail,
            )

        multipart_files: list[tuple[str, tuple[str, bytes, str]]] = []
        attached_names: set[str] = set()
        for pf in budget_files:
            disk_path = Path(pf.storage_key)
            if not disk_path.exists():
                continue

            mime_type = pf.mime or "application/octet-stream"
            multipart_files.append(("files", (pf.original_name, disk_path.read_bytes(), mime_type)))
            attached_names.add(Path(pf.original_name).name.lower())

            if disk_path.suffix.lower() != ".dwg":
                continue
            stem_lower = Path(pf.original_name).stem.lower()
            if stem_lower in dxf_stems_in_budget:
                continue
            for dxf_path in auxiliary_dxf_candidates(disk_path, upload_root, readable_cache=readable_cache):
                dxf_name = f"{Path(pf.original_name).stem}.dxf"
                if dxf_name.lower() in attached_names:
                    continue
                multipart_files.append(
                    ("files", (dxf_name, dxf_path.read_bytes(), "application/dxf"))
                )
                attached_names.add(dxf_name.lower())

        if not multipart_files:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se encontraron archivos en disco")

        processor_url = get_settings().processor_url
        correlation_id = str(uuid.uuid4())
        logger.info(
            "Enqueuing budget job for project %s with correlation ID: %s discipline=%s",
            project_uuid,
            correlation_id,
            budget_discipline,
        )
        try:
            form_data: dict[str, str] = {
                "discipline": budget_discipline,
                "project_name": project.name,
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{processor_url}/jobs/process",
                    files=multipart_files,
                    data=form_data,
                    headers={"X-Correlation-ID": correlation_id},
                )
        except Exception as exc:
            logger.error("Failed to reach processor service: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Processor service unavailable",
            ) from exc

        if resp.status_code not in (200, 201, 202):
            logger.error("Processor returned %s: %s", resp.status_code, resp.text[:500])
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Processor rejected the request")

        data = resp.json()
        job_id = data.get("job_id")
        if not job_id:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Processor returned no job_id")

        job = ProjectBudgetJob(
            project_id=project.id,
            job_id=str(job_id),
            status="queued",
            discipline=budget_discipline,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def get_latest_job(self, user: User, project_uuid: UUID) -> Optional[ProjectBudgetJob]:
        project = await self._project_svc.get_project(user, project_uuid)
        result = await self._session.execute(
            select(ProjectBudgetJob)
            .where(ProjectBudgetJob.project_id == project.id)
            .order_by(ProjectBudgetJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def sync_job_status(self, job: ProjectBudgetJob) -> ProjectBudgetJob:
        """Refresh job status from processor. Mutates job in-place; caller must commit."""
        if job.status in ("completed", "failed", "completed_partial"):
            return job

        processor_url = get_settings().processor_url
        correlation_id = str(uuid.uuid4())
        logger.info(f"Polling job status for {job.job_id} with correlation ID: {correlation_id}")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{processor_url}/jobs/{job.job_id}",
                    headers={"X-Correlation-ID": correlation_id}
                )
        except Exception as exc:
            logger.warning("Processor status poll failed: %s", exc)
            return job

        if resp.status_code == 404:
            job.status = "failed"
            job.error = "Job not found on processor"
            return job

        if resp.status_code != 200:
            return job

        data = resp.json()
        remote_status = data.get("status", "")

        if remote_status in ("completed", "completed_partial"):
            result = data.get("result")
            job.result = result
            qualifies = budget_result_qualifies_for_volumetry(result if isinstance(result, dict) else None)
            if remote_status == "completed" and not qualifies:
                job.status = "completed_partial"
            else:
                job.status = remote_status
            if job.status == "completed":
                await sync_volumetry_from_completed_job(self._session, job)
        elif remote_status == "failed":
            job.status = "failed"
            job.error = str(data.get("error") or "Unknown error")
        elif remote_status in ("queued", "started", "deferred", "scheduled"):
            job.status = "processing" if remote_status == "started" else "queued"

        phase = data.get("phase")
        if isinstance(phase, str) and phase.strip():
            job.phase = phase.strip()  # type: ignore[attr-defined]
        phase_detail = data.get("phase_detail")
        if isinstance(phase_detail, str) and phase_detail.strip():
            job.phase_detail = phase_detail.strip()  # type: ignore[attr-defined]

        return job

    async def get_budget_result(self, user: User, project_uuid: UUID) -> dict[str, Any]:
        job = await self.get_latest_job(user, project_uuid)
        if job is None or job.status != "completed" or job.result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No completed budget found")
        if not budget_result_qualifies_for_volumetry(job.result if isinstance(job.result, dict) else None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Presupuesto incompleto: ejecuta de nuevo con una disciplina",
            )
        return job.result

    async def save_budget_result(
        self,
        user: User,
        project_uuid: UUID,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        job = await self.get_latest_job(user, project_uuid)
        if job is None or job.result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No hay presupuesto para guardar",
            )
        if job.status not in ("completed", "completed_partial"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El presupuesto aun se esta procesando",
            )
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Se requiere al menos una fila",
            )

        normalized = [_normalize_budget_row(raw) for raw in rows]
        result = dict(job.result)
        result["rows"] = normalized
        result["manually_edited"] = True
        result["manually_edited_at"] = datetime.now(timezone.utc).isoformat()
        job.result = result
        if budget_result_qualifies_for_volumetry(result):
            job.status = "completed"
            await sync_volumetry_from_completed_job(self._session, job)
        flag_modified(job, "result")
        await self._session.flush()
        return result


def _normalize_budget_row(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cada fila debe ser un objeto",
        )
    row = dict(raw)
    row_type = str(row.get("row_type") or "line")
    row["row_type"] = row_type
    row["code"] = str(row.get("code") or "").strip()
    row["summary"] = str(row.get("summary") or "").strip()
    row["unit"] = str(row.get("unit") or "").strip()
    row["nat"] = str(row.get("nat") or "").strip()
    try:
        qty = float(row.get("quantity") or 0)
    except (TypeError, ValueError):
        qty = 0.0
    try:
        unit_price = float(row.get("unit_price") or 0)
    except (TypeError, ValueError):
        unit_price = 0.0
    if row_type == "line":
        row["quantity"] = qty
        row["unit_price"] = round(unit_price, 2)
        row["amount"] = round(qty * unit_price, 2)
    else:
        try:
            amount = float(row.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        row["amount"] = round(amount, 2)
    meta = row.get("metadata")
    row["metadata"] = meta if isinstance(meta, dict) else {}
    return row
