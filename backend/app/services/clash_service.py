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
from app.services.folder_path_parts import (
    build_folder_children_map,
    build_folder_path_index,
    descendant_folder_ids,
    folder_path_parts,
    format_folder_path,
)
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


def extract_extraction_progress(remote_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(remote_payload, dict):
        return None
    progress = remote_payload.get("progress")
    return progress if isinstance(progress, dict) else None


def format_extraction_progress_message(progress: dict[str, Any] | None) -> str | None:
    if not progress:
        return None
    processed = int(progress.get("processed") or 0)
    total = int(progress.get("total") or 0)
    phase = str(progress.get("phase") or "extraction")
    if total <= 0:
        return None
    if phase == "clash":
        return f"Detectando clashes ({processed}/{total} planos extraídos)…"
    return f"Extrayendo planos {processed}/{total}…"


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


def _is_pdf_filename(name: str) -> bool:
    return (name or "").lower().endswith(".pdf")


class ClashService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self._session = session
        self._workspace_id = workspace_id
        self._project_svc = ProjectService(session, workspace_id)

    async def _all_folders(self, project_id: UUID) -> list[ProjectFileFolder]:
        result = await self._session.execute(
            select(ProjectFileFolder)
            .where(ProjectFileFolder.project_id == project_id)
            .order_by(ProjectFileFolder.name.asc())
        )
        return list(result.scalars().all())

    async def _folder_path_parts(self, project_id: UUID, folder_id: UUID | None) -> list[str]:
        return await folder_path_parts(self._session, project_id, folder_id)

    async def _descendant_folder_ids(self, project_id: UUID, root_folder_id: UUID) -> set[UUID]:
        folders = await self._all_folders(project_id)
        children = build_folder_children_map(folders)
        return descendant_folder_ids(root_folder_id, children)

    async def _coordination_tree(
        self,
        project_id: UUID,
    ) -> tuple[
        list[ProjectFileFolder],
        dict[UUID | None, list[UUID]],
        dict[UUID, list[str]],
        list[ProjectFile],
    ]:
        folders = await self._all_folders(project_id)
        children = build_folder_children_map(folders)
        paths = build_folder_path_index(folders)
        result = await self._session.execute(
            select(ProjectFile)
            .where(ProjectFile.project_id == project_id)
            .order_by(ProjectFile.created_at.asc())
        )
        cad_files = [pf for pf in result.scalars() if _is_cad_filename(pf.original_name or "")]
        return folders, children, paths, cad_files

    @staticmethod
    def _cad_stats_for_tree(
        folder_id: UUID,
        *,
        children: dict[UUID | None, list[UUID]],
        cad_files: list[ProjectFile],
    ) -> tuple[int, int, bool, int]:
        tree_ids = descendant_folder_ids(folder_id, children)
        in_tree = [pf for pf in cad_files if pf.folder_id in tree_ids]
        buckets = {
            discipline_bucket(pf.discipline)
            for pf in in_tree
            if discipline_bucket(pf.discipline) != "sin_clasificar"
        }
        unclassified = sum(1 for pf in in_tree if discipline_bucket(pf.discipline) == "sin_clasificar")
        missing_disk = sum(1 for pf in in_tree if not Path(pf.storage_key).is_file())
        ready = (
            len(in_tree) > 0
            and len(buckets) >= 2
            and unclassified == 0
            and missing_disk == 0
        )
        return len(in_tree), len(buckets), ready, unclassified

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
        folders, children, paths, cad_files = await self._coordination_tree(project.id)
        out: list[dict[str, Any]] = []
        for fo in folders:
            cad_count, discipline_count, ready, sin_clasificar = self._cad_stats_for_tree(
                fo.id,
                children=children,
                cad_files=cad_files,
            )
            if cad_count == 0:
                continue
            path = format_folder_path(paths.get(fo.id, []), leaf_name=fo.name)
            out.append(
                {
                    "uuid": str(fo.id),
                    "name": fo.name,
                    "path": path,
                    "parent_uuid": str(fo.parent_id) if fo.parent_id else None,
                    "cad_count": cad_count,
                    "discipline_count": discipline_count,
                    "sin_clasificar": sin_clasificar,
                    "ready": ready,
                }
            )

        def _sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
            return (
                0 if row.get("ready") else 1,
                0 if int(row.get("discipline_count") or 0) >= 2 else 1,
                str(row.get("path") or ""),
            )

        out.sort(key=_sort_key)
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

    async def _pdf_files_in_folders(
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
        return [pf for pf in rows if _is_pdf_filename(pf.original_name or "")]

    async def _count_non_cad_files_in_folders(
        self,
        project_id: UUID,
        folder_ids: set[UUID],
    ) -> int:
        if not folder_ids:
            return 0
        result = await self._session.execute(
            select(ProjectFile).where(
                ProjectFile.project_id == project_id,
                ProjectFile.folder_id.in_(folder_ids),
            )
        )
        rows = list(result.scalars().all())
        return sum(1 for pf in rows if not _is_cad_filename(pf.original_name or ""))

    async def _parent_folder_coordination_hint(
        self,
        project_id: UUID,
        folder_uuid: UUID,
        *,
        children: dict[UUID | None, list[UUID]] | None = None,
        paths: dict[UUID, list[str]] | None = None,
        cad_files: list[ProjectFile] | None = None,
    ) -> str | None:
        folder = await self._session.get(ProjectFileFolder, folder_uuid)
        if folder is None or folder.parent_id is None:
            return None
        parent = await self._session.get(ProjectFileFolder, folder.parent_id)
        if parent is None:
            return None
        if children is None or paths is None or cad_files is None:
            _, children, paths, cad_files = await self._coordination_tree(project_id)
        parent_ids = descendant_folder_ids(parent.id, children)
        parent_disc_count = len(
            {
                discipline_bucket(pf.discipline)
                for pf in cad_files
                if pf.folder_id in parent_ids and discipline_bucket(pf.discipline) != "sin_clasificar"
            }
        )
        if parent_disc_count < 2:
            return None
        path_display = format_folder_path(paths.get(parent.id, []), leaf_name=parent.name)
        return (
            f"La subcarpeta «{folder.name}» solo agrupa una disciplina CAD. "
            f"Selecciona la carpeta padre «{path_display}» para comparar todas las disciplinas."
        )

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
        children: dict[UUID | None, list[UUID]] = {}
        paths: dict[UUID, list[str]] = {}

        if folder_uuid is None:
            blockers.append("Selecciona una carpeta fuente con planos CAD (ej. TEST_01).")
        else:
            _, children, paths, all_cad = await self._coordination_tree(project.id)
            folder = await self._require_folder(project.id, folder_uuid)
            path_display = format_folder_path(paths.get(folder.id, []), leaf_name=folder.name)
            folder_info = {"uuid": str(folder.id), "name": folder.name, "path": path_display}
            folder_ids = descendant_folder_ids(folder.id, children)
            cad_files = [pf for pf in all_cad if pf.folder_id in folder_ids]
            if not cad_files:
                other_count = await self._count_non_cad_files_in_folders(project.id, folder_ids)
                if other_count > 0:
                    blockers.append(
                        f"La carpeta «{folder.name}» tiene {other_count} archivo(s) (PDF, etc.) "
                        "pero el análisis de clashes requiere planos .dwg/.dxf."
                    )
                else:
                    blockers.append(f"La carpeta «{folder.name}» no contiene archivos .dwg/.dxf.")

        files_by_discipline: dict[str, list[dict[str, Any]]] = {k: [] for k in DISCIPLINE_BUCKETS}
        folder_path = folder_info["path"] if folder_info else ""
        for pf in cad_files:
            bucket = discipline_bucket(pf.discipline)
            rel_parts = paths.get(pf.folder_id, []) if pf.folder_id else []
            file_folder_path = format_folder_path(rel_parts) if rel_parts else folder_path
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
            parent_hint = await self._parent_folder_coordination_hint(
                project.id,
                folder_uuid,
                children=children,
                paths=paths,
                cad_files=all_cad,
            )
            if parent_hint:
                blockers.append(parent_hint)
            else:
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

        pdf_files = await self._pdf_files_in_folders(project.id, folder_ids)
        payload_files = [*cad_files, *pdf_files]

        metadata: list[dict[str, Any]] = []
        multipart: list[tuple[str, tuple[str, bytes, str]]] = []

        for pf in payload_files:
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
                    "companion_only": not _is_cad_filename(pf.original_name or ""),
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
        cad_metadata = [m for m in file_metadata if _is_cad_filename(str(m.get("original_name") or ""))]
        buckets = {m["discipline_bucket"] for m in cad_metadata}
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

        from app.services.control_points_service import ControlPointsService

        cp_svc = ControlPointsService(self._session, self._workspace_id)
        control_points = await cp_svc.get_for_job(project.id)

        form_data = {
            "profile_slug": slug,
            "project_name": project.name,
            "file_metadata": json.dumps(file_metadata, ensure_ascii=False),
            "budget_scope": "1",
        }
        if control_points:
            form_data["control_points_json"] = json.dumps(control_points, ensure_ascii=False)

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
        progress = extract_extraction_progress(data)
        if progress:
            job.extraction_progress = progress  # type: ignore[attr-defined]

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

            if job.is_reanalysis and job.reanalysis_item_uuid:
                try:
                    await self._resolve_reanalysis_item(job)
                except Exception as exc:
                    logger.warning("Reanalysis item resolution failed: %s", exc)
            else:
                try:
                    from app.services.clash_workflow_service import ClashWorkflowService

                    wf = ClashWorkflowService(self._session, self._workspace_id)
                    await wf.ensure_ingested(job, actor="system")
                except Exception as exc:
                    logger.warning("Clash workflow ingest after job complete failed: %s", exc)
        elif remote_status == "failed":
            job.status = "failed"
            job.error = str(data.get("error") or "Unknown error")
        elif remote_status in ("queued", "started", "deferred", "scheduled"):
            job.status = "processing" if remote_status == "started" else "queued"

        return job

    async def _resolve_reanalysis_item(self, job: ProjectClashJob) -> None:
        """Auto-transition the reanalysis item to resolved or still_present."""
        from app.domain.clash_workflow_enums import (
            ClashStatus,
            CorrectionResult,
            EventType,
            can_transition,
        )
        from app.models.project_clash_correction import ProjectClashCorrection
        from app.models.project_clash_item import ProjectClashItem
        from sqlalchemy.orm import selectinload

        item = await self._session.get(
            ProjectClashItem,
            job.reanalysis_item_uuid,
            options=[selectinload(ProjectClashItem.corrections)],
        )
        if item is None:
            return

        result = job.result or {}
        clash_items = result.get("clash_items") or result.get("report", {}).get("clash_items") or []
        clash_found = bool(clash_items)

        try:
            current = ClashStatus(item.status)
        except ValueError:
            return

        target = ClashStatus.STILL_PRESENT if clash_found else ClashStatus.RESOLVED
        if not can_transition(current, target):
            return

        from datetime import timezone

        previous = item.status
        item.status = target.value
        item.updated_at = datetime.now(timezone.utc)

        corrections = sorted(item.corrections, key=lambda c: c.uploaded_at or datetime.utcnow())
        if corrections:
            latest = corrections[-1]
            latest.result = (
                CorrectionResult.STILL_PRESENT.value if clash_found else CorrectionResult.RESOLVED.value
            )
            latest.reanalysis_run_id = job.job_id

        from app.models.project_clash_event import ProjectClashEvent

        self._session.add(
            ProjectClashEvent(
                id=uuid.uuid4(),
                clash_item_id=item.id,
                event_type=EventType.REANALYSIS.value,
                actor="system",
                previous_status=previous,
                new_status=target.value,
                comment=(
                    "Reanálisis completado: el clash persiste." if clash_found
                    else "Reanálisis completado: clash resuelto."
                ),
                related_run_id=job.job_id,
            )
        )

    async def enqueue_pair_reanalysis(
        self,
        *,
        job: ProjectClashJob,
        item: Any,
        corrected_path: Path,
        corrected_original_name: str,
        corrected_discipline: str | None,
        ref_path: Path | None,
        ref_original_name: str | None,
        ref_discipline: str | None,
        user: User,
    ) -> str:
        """Enqueue a 2-file clash reanalysis job and return the new job_id."""
        from app.models.project_clash_item import ProjectClashItem

        coordination_url = settings.coordination_url
        correlation_id = str(uuid.uuid4())

        file_metadata: list[dict] = [
            {
                "original_name": corrected_original_name,
                "discipline": corrected_discipline,
                "discipline_bucket": discipline_bucket(corrected_discipline or ""),
            }
        ]
        multipart_files: list[tuple] = [
            (
                "files",
                (corrected_original_name, corrected_path.read_bytes(), "application/octet-stream"),
            )
        ]

        if ref_path and ref_original_name:
            file_metadata.append(
                {
                    "original_name": ref_original_name,
                    "discipline": ref_discipline,
                    "discipline_bucket": discipline_bucket(ref_discipline or ""),
                }
            )
            multipart_files.append(
                ("files", (ref_original_name, ref_path.read_bytes(), "application/octet-stream"))
            )

        form_data = {
            "profile_slug": "reanalysis",
            "project_name": "reanalysis",
            "file_metadata": json.dumps(file_metadata),
            "reanalysis_clash_code": item.clash_code,
            "budget_scope": "1",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{coordination_url}/jobs/clash-analysis",
                    files=multipart_files,
                    data=form_data,
                    headers={"X-Correlation-ID": correlation_id},
                )
        except Exception as exc:
            logger.error("Failed to reach coordination service for reanalysis: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Coordination service unavailable",
            ) from exc

        if resp.status_code not in (200, 201, 202):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Coordination service rejected reanalysis request",
            )

        data = resp.json()
        new_job_id = data.get("job_id")
        if not new_job_id:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Coordination service returned no job_id for reanalysis",
            )

        new_job = ProjectClashJob(
            project_id=job.project_id,
            job_id=str(new_job_id),
            status="queued",
            coordination_profile="reanalysis",
            folder_id=job.folder_id,
            folder_name=job.folder_name,
            is_reanalysis=True,
            reanalysis_item_uuid=item.id,
            triggered_by_user_id=user.id,
        )
        self._session.add(new_job)
        await self._session.flush()
        return str(new_job_id)

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
            progress_msg = format_extraction_progress_message(getattr(job, "extraction_progress", None))
            subtitle = progress_msg or "Análisis en curso…"
            return {
                "run_status": "running",
                "title": f"Informe de coordinación — {project.name}",
                "subtitle": subtitle,
                "summary": {"errors": 0, "warnings": 0, "ok": 0},
                "clashes": [],
                "clash_relationships": [],
                "analyzed_documents": [],
                "ai_insight": "El análisis de clashes está en ejecución.",
                "zoning_rows": [],
                "footer_status_message": progress_msg or f"Estado del job: {job.status}",
                "extraction_progress": getattr(job, "extraction_progress", None),
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
