"""Clash / structural analysis orchestration service."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.file_discipline import (
    CLASSIFIED_BUCKETS,
    DISCIPLINE_BUCKETS,
    DISCIPLINE_LABELS,
    DISCIPLINE_SHORT,
    discipline_bucket,
)
from app.models.project import Project
from app.models.project_clash_job import ProjectClashJob
from app.models.project_file import ProjectFile
from app.models.project_file_folder import ProjectFileFolder
from app.models.user import User
from app.services.project_service import ProjectService

logger = logging.getLogger(__name__)
settings = get_settings()

FOLDER_DRIVEN_PROFILE = "folder"


def compute_cad_fingerprint(cad_files: list[ProjectFile]) -> str:
    parts: list[str] = []
    for pf in sorted(cad_files, key=lambda x: str(x.id)):
        parts.append(f"{pf.id}|{pf.original_name}|{pf.discipline or ''}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def resolve_run_sequence(
    completed_jobs: list[tuple[str | None, int | None]],
    fingerprint: str,
) -> int:
    """Pick run sequence from prior completed jobs (newest first)."""
    for job_fingerprint, seq in completed_jobs:
        if job_fingerprint == fingerprint and seq:
            return seq
    max_seq = max((seq or 0 for _, seq in completed_jobs), default=0)
    return max(max_seq + 1, 1)


def extract_clash_report(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    if "report" in result and isinstance(result["report"], dict):
        return result["report"]
    return result


def extract_clash_artifacts(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    artifacts = result.get("artifacts")
    return artifacts if isinstance(artifacts, dict) else {}


def extract_output_dir(artifacts: dict[str, Any] | None) -> str | None:
    """Resolve coordination output path from job artifacts."""
    if not isinstance(artifacts, dict):
        return None
    direct = artifacts.get("output_dir")
    if direct:
        return str(direct)
    paths = artifacts.get("paths")
    if isinstance(paths, dict) and paths.get("output_dir"):
        return str(paths["output_dir"])
    return None


def _is_cad_filename(name: str) -> bool:
    lower = (name or "").lower()
    return lower.endswith(".dwg") or lower.endswith(".dxf")


class ClashService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self._session = session
        self._project_svc = ProjectService(session, workspace_id)

    async def _all_folders(self, project_id: UUID) -> list[ProjectFileFolder]:
        result = await self._session.execute(
            select(ProjectFileFolder)
            .where(ProjectFileFolder.project_id == project_id)
            .order_by(ProjectFileFolder.name.asc())
        )
        return list(result.scalars().all())

    async def _folder_path_parts(self, project_id: UUID, folder_id: UUID | None) -> list[str]:
        if folder_id is None:
            return []
        parts: list[str] = []
        cur: UUID | None = folder_id
        for _ in range(128):
            if cur is None:
                break
            row = await self._session.get(ProjectFileFolder, cur)
            if row is None or row.project_id != project_id:
                break
            parts.append(row.name)
            cur = row.parent_id
        parts.reverse()
        return parts

    async def _descendant_folder_ids(self, project_id: UUID, root_folder_id: UUID) -> set[UUID]:
        all_folders = await self._all_folders(project_id)
        children: dict[UUID | None, list[UUID]] = {}
        for fo in all_folders:
            children.setdefault(fo.parent_id, []).append(fo.id)
        out: set[UUID] = set()
        stack = [root_folder_id]
        while stack:
            fid = stack.pop()
            if fid in out:
                continue
            out.add(fid)
            stack.extend(children.get(fid, []))
        return out

    async def _require_folder(self, project_id: UUID, folder_uuid: UUID) -> ProjectFileFolder:
        row = await self._session.get(ProjectFileFolder, folder_uuid)
        if row is None or row.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpeta no encontrada")
        return row

    async def count_all_project_files(self, user: User, project_uuid: UUID) -> int:
        project = await self._project_svc.get_project(user, project_uuid)
        q = select(func.count()).select_from(ProjectFile).where(ProjectFile.project_id == project.id)
        return int((await self._session.execute(q)).scalar_one())

    async def list_coordination_folders(self, user: User, project_uuid: UUID) -> list[dict[str, Any]]:
        project = await self._project_svc.get_project(user, project_uuid)
        folders = await self._all_folders(project.id)
        out: list[dict[str, Any]] = []
        for fo in folders:
            parts = await self._folder_path_parts(project.id, fo.id)
            path = "Raíz / " + " / ".join(parts) if parts else fo.name
            out.append({"uuid": str(fo.id), "name": fo.name, "path": path, "parent_uuid": str(fo.parent_id) if fo.parent_id else None})
        out.sort(key=lambda x: x["path"])
        return out

    async def _cad_files_in_folders(
        self,
        project_id: UUID,
        folder_ids: set[UUID],
    ) -> list[ProjectFile]:
        if not folder_ids:
            return []
        result = await self._session.execute(
            select(ProjectFile)
            .where(
                ProjectFile.project_id == project_id,
                ProjectFile.folder_id.in_(folder_ids),
            )
            .order_by(ProjectFile.created_at.asc())
        )
        rows = list(result.scalars().all())
        return [pf for pf in rows if _is_cad_filename(pf.original_name or "")]

    def _file_inventory_row(self, pf: ProjectFile, folder_path: str) -> dict[str, Any]:
        disk_exists = Path(pf.storage_key).is_file()
        return {
            "uuid": str(pf.id),
            "file_name": pf.original_name,
            "discipline": pf.discipline,
            "discipline_bucket": discipline_bucket(pf.discipline),
            "folder_path": folder_path,
            "status": "ok" if disk_exists else "error",
        }

    async def get_coordination_inventory(
        self,
        user: User,
        project_uuid: UUID,
        folder_uuid: UUID | None = None,
    ) -> dict[str, Any]:
        project = await self._project_svc.get_project(user, project_uuid)
        blockers: list[str] = []

        folder_info: dict[str, Any] | None = None
        cad_files: list[ProjectFile] = []

        if folder_uuid is None:
            blockers.append("Selecciona una carpeta fuente con planos CAD (ej. TEST_01).")
        else:
            folder = await self._require_folder(project.id, folder_uuid)
            parts = await self._folder_path_parts(project.id, folder.id)
            path_display = "Raíz / " + " / ".join(parts) if parts else folder.name
            folder_info = {"uuid": str(folder.id), "name": folder.name, "path": path_display}
            folder_ids = await self._descendant_folder_ids(project.id, folder.id)
            cad_files = await self._cad_files_in_folders(project.id, folder_ids)
            if not cad_files:
                blockers.append(f"La carpeta «{folder.name}» no contiene archivos .dwg/.dxf.")

        files_by_discipline: dict[str, list[dict[str, Any]]] = {k: [] for k in DISCIPLINE_BUCKETS}
        folder_path = folder_info["path"] if folder_info else ""
        for pf in cad_files:
            bucket = discipline_bucket(pf.discipline)
            rel_parts = await self._folder_path_parts(project.id, pf.folder_id)
            file_folder_path = "Raíz / " + " / ".join(rel_parts) if rel_parts else folder_path
            files_by_discipline[bucket].append(self._file_inventory_row(pf, file_folder_path))
            if bucket == "sin_clasificar":
                blockers.append(f"«{pf.original_name}» no tiene disciplina (etiquétalo en Archivos).")

        missing_disk = [f for f in cad_files if not Path(f.storage_key).is_file()]
        if missing_disk:
            blockers.append(f"{len(missing_disk)} archivo(s) no encontrados en disco.")

        discipline_lines: list[dict[str, Any]] = []
        for bucket in DISCIPLINE_BUCKETS:
            if bucket == "sin_clasificar":
                continue
            count = len(files_by_discipline[bucket])
            if count > 0:
                discipline_lines.append(
                    {
                        "bucket": bucket,
                        "label": DISCIPLINE_LABELS[bucket],
                        "short": DISCIPLINE_SHORT[bucket],
                        "count": count,
                    }
                )

        classified_count = sum(line["count"] for line in discipline_lines)
        if cad_files and classified_count == 0:
            blockers.append("Etiqueta cada DWG con su disciplina en Archivos (ARQ, EST, ELC, etc.).")
        elif cad_files and len(discipline_lines) < 2:
            blockers.append(
                "Se necesitan planos de al menos dos disciplinas distintas para comparar clashes entre ellas."
            )

        unique_blockers = list(dict.fromkeys(blockers))
        ready = (
            folder_uuid is not None
            and len(cad_files) > 0
            and len(discipline_lines) >= 2
            and len(files_by_discipline["sin_clasificar"]) == 0
            and not missing_disk
        )

        return {
            "project_name": project.name,
            "folder": folder_info,
            "files_by_discipline": files_by_discipline,
            "discipline_lines": discipline_lines,
            "summary": {
                "total_cad": len(cad_files),
                "sin_clasificar": len(files_by_discipline["sin_clasificar"]),
                "discipline_count": len(discipline_lines),
                "by_bucket": {b: len(files_by_discipline[b]) for b in DISCIPLINE_BUCKETS},
            },
            "ready": ready,
            "blockers": unique_blockers,
        }

    async def _prepare_cad_payload(
        self,
        project: Project,
        folder_uuid: UUID,
    ) -> tuple[list[dict[str, Any]], list[tuple[str, tuple[str, bytes, str]]]]:
        folder = await self._require_folder(project.id, folder_uuid)
        folder_ids = await self._descendant_folder_ids(project.id, folder.id)
        cad_files = await self._cad_files_in_folders(project.id, folder_ids)
        if not cad_files:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"La carpeta «{folder.name}» no contiene archivos CAD (.dwg/.dxf)",
            )

        parts = await self._folder_path_parts(project.id, folder.id)
        folder_path = "Raíz / " + " / ".join(parts) if parts else folder.name

        metadata: list[dict[str, Any]] = []
        multipart: list[tuple[str, tuple[str, bytes, str]]] = []

        for pf in cad_files:
            disk_path = Path(pf.storage_key)
            if not disk_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Archivo no encontrado en disco: {pf.original_name}",
                )
            mime_type = pf.mime or "application/octet-stream"
            multipart.append(("files", (pf.original_name, disk_path.read_bytes(), mime_type)))
            metadata.append(
                {
                    "original_name": pf.original_name,
                    "discipline": pf.discipline,
                    "discipline_bucket": discipline_bucket(pf.discipline),
                    "folder_path": folder_path,
                }
            )

        return metadata, multipart

    async def _resolve_run_sequence(
        self,
        project_id: UUID,
        folder_id: UUID,
        fingerprint: str,
    ) -> int:
        result = await self._session.execute(
            select(ProjectClashJob)
            .where(
                ProjectClashJob.project_id == project_id,
                ProjectClashJob.folder_id == folder_id,
                ProjectClashJob.status == "completed",
            )
            .order_by(ProjectClashJob.created_at.desc())
        )
        jobs = list(result.scalars().all())
        job_rows = [(j.cad_fingerprint, j.run_sequence) for j in jobs]
        return resolve_run_sequence(job_rows, fingerprint)

    async def enqueue_clash_job(
        self,
        user: User,
        project_uuid: UUID,
        profile_slug: Optional[str] = None,
        folder_uuid: Optional[UUID] = None,
    ) -> ProjectClashJob:
        project = await self._project_svc.get_project(user, project_uuid)

        if folder_uuid is None:
            meta = dict(project.workflow_meta or {})
            last = meta.get("coordination_last_folder_uuid")
            if last:
                try:
                    folder_uuid = UUID(str(last))
                except ValueError:
                    folder_uuid = None
        if folder_uuid is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Selecciona una carpeta fuente con planos CAD antes de ejecutar el análisis.",
            )

        file_metadata, multipart_files = await self._prepare_cad_payload(project, folder_uuid)
        folder = await self._require_folder(project.id, folder_uuid)
        folder_ids = await self._descendant_folder_ids(project.id, folder.id)
        cad_files = await self._cad_files_in_folders(project.id, folder_ids)
        cad_fingerprint = compute_cad_fingerprint(cad_files)
        run_sequence = await self._resolve_run_sequence(project.id, folder_uuid, cad_fingerprint)

        # Validate same rules as inventory pre-flight
        buckets = {m["discipline_bucket"] for m in file_metadata}
        classified = buckets & CLASSIFIED_BUCKETS
        if "sin_clasificar" in buckets:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Hay DWG sin disciplina. Etiquétalos en Archivos antes de ejecutar.",
            )
        if len(classified) < 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Se necesitan planos de al menos dos disciplinas distintas en la carpeta seleccionada.",
            )

        slug = FOLDER_DRIVEN_PROFILE
        coordination_url = settings.coordination_url
        correlation_id = str(uuid.uuid4())
        logger.info(
            "Enqueuing clash job project=%s folder=%s files=%d disciplines=%s",
            project_uuid,
            folder_uuid,
            len(multipart_files),
            sorted(classified),
        )

        form_data = {
            "profile_slug": slug,
            "project_name": project.name,
            "file_metadata": json.dumps(file_metadata, ensure_ascii=False),
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{coordination_url}/jobs/clash-analysis",
                    files=multipart_files,
                    data=form_data,
                    headers={"X-Correlation-ID": correlation_id},
                )
        except Exception as exc:
            logger.error("Failed to reach coordination service: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Coordination service unavailable",
            ) from exc

        if resp.status_code not in (200, 201, 202):
            logger.error("Coordination service returned %s: %s", resp.status_code, resp.text[:500])
            detail = "Coordination service rejected the request"
            try:
                body = resp.json()
                if isinstance(body, dict) and body.get("detail"):
                    detail = str(body["detail"])
            except Exception:
                pass
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)

        data = resp.json()
        job_id = data.get("job_id")
        if not job_id:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Coordination service returned no job_id")

        meta = dict(project.workflow_meta or {})
        meta["coordination_last_folder_uuid"] = str(folder_uuid)
        project.workflow_meta = meta

        job = ProjectClashJob(
            project_id=project.id,
            job_id=str(job_id),
            status="queued",
            coordination_profile=slug,
            folder_id=folder_uuid,
            folder_name=folder.name,
            cad_fingerprint=cad_fingerprint,
            run_sequence=run_sequence,
            triggered_by_user_id=user.id,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def get_latest_job(self, user: User, project_uuid: UUID) -> Optional[ProjectClashJob]:
        project = await self._project_svc.get_project(user, project_uuid)
        result = await self._session.execute(
            select(ProjectClashJob)
            .where(ProjectClashJob.project_id == project.id)
            .order_by(ProjectClashJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def sync_job_status(self, job: ProjectClashJob) -> ProjectClashJob:
        if job.status in ("completed", "failed"):
            return job

        coordination_url = settings.coordination_url
        correlation_id = str(uuid.uuid4())
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{coordination_url}/jobs/{job.job_id}",
                    headers={"X-Correlation-ID": correlation_id},
                )
        except Exception as exc:
            logger.warning("Coordination status poll failed: %s", exc)
            return job

        if resp.status_code == 404:
            job.status = "failed"
            job.error = "Job not found on coordination service"
            return job

        if resp.status_code != 200:
            return job

        data = resp.json()
        remote_status = data.get("status", "")

        if remote_status == "completed":
            job.status = "completed"
            raw_result = data.get("result") or {}
            if isinstance(raw_result, dict):
                report = raw_result.get("report")
                artifacts = raw_result.get("artifacts")
                if isinstance(report, dict):
                    job.result = {"report": report, "artifacts": artifacts if isinstance(artifacts, dict) else {}}
                else:
                    job.result = raw_result
                if isinstance(artifacts, dict):
                    output_dir = extract_output_dir(artifacts)
                    if output_dir:
                        job.output_dir = output_dir
            else:
                job.result = raw_result
            try:
                from app.services.clash_workflow_service import ClashWorkflowService

                wf = ClashWorkflowService(self._session)
                await wf.ensure_ingested(job, actor="system")
            except Exception as exc:
                logger.warning("Clash workflow ingest after job complete failed: %s", exc)
        elif remote_status == "failed":
            job.status = "failed"
            job.error = str(data.get("error") or "Unknown error")
        elif remote_status in ("queued", "started", "deferred", "scheduled"):
            job.status = "processing" if remote_status == "started" else "queued"

        return job

    async def get_structural_analysis_report(self, user: User, project_uuid: UUID) -> dict[str, Any]:
        job = await self.get_latest_job(user, project_uuid)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No clash analysis found for this project")

        if job.status not in ("completed", "failed"):
            job = await self.sync_job_status(job)
            await self._session.flush()

        if job.status == "completed" and job.result is not None:
            report = extract_clash_report(job.result if isinstance(job.result, dict) else None)
            if report is not None:
                return report

        if job.status in ("queued", "processing"):
            project = await self._project_svc.get_project(user, project_uuid)
            return {
                "run_status": "running",
                "title": f"Informe de coordinación — {project.name}",
                "subtitle": "Análisis en curso…",
                "summary": {"errors": 0, "warnings": 0, "ok": 0},
                "clashes": [],
                "clash_relationships": [],
                "analyzed_documents": [],
                "ai_insight": "El análisis de clashes está en ejecución.",
                "zoning_rows": [],
                "footer_status_message": f"Estado del job: {job.status}",
            }

        if job.status == "failed":
            return {
                "run_status": "failed",
                "title": "Informe de coordinación",
                "subtitle": "El análisis no pudo completarse",
                "summary": {"errors": 0, "warnings": 0, "ok": 0},
                "clashes": [],
                "clash_relationships": [],
                "analyzed_documents": [],
                "ai_insight": job.error or "Error desconocido en la corrida de clashes.",
                "zoning_rows": [],
                "footer_status_message": job.error or "Análisis fallido",
            }

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No completed clash analysis found")

    async def get_completed_report_for_project_id(self, project_id: UUID) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(ProjectClashJob)
            .where(
                ProjectClashJob.project_id == project_id,
                ProjectClashJob.status == "completed",
                ProjectClashJob.result.isnot(None),
            )
            .order_by(ProjectClashJob.created_at.desc())
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if job is None or not isinstance(job.result, dict):
            return None
        return extract_clash_report(job.result)

    async def get_job_for_export(
        self,
        user: User,
        project_uuid: UUID,
        job_id: UUID | None = None,
    ) -> ProjectClashJob:
        project = await self._project_svc.get_project(user, project_uuid)
        if job_id is not None:
            job = await self._session.get(ProjectClashJob, job_id)
            if job is None or job.project_id != project.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clash job not found")
        else:
            job = await self.get_latest_job(user, project_uuid)
            if job is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No clash job found for this project")

        if job.status != "completed":
            job = await self.sync_job_status(job)
            await self._session.flush()

        if job.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No completed clash analysis available for export",
            )
        if not isinstance(job.result, dict) or not extract_clash_artifacts(job.result):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Export artifacts not available for this clash job",
            )
        return job
