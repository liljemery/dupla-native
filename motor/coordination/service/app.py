"""FastAPI coordination service.

Exposes:
  POST /jobs/clash-analysis  — accept uploaded CAD files, start pipeline
  GET  /jobs/{job_id}        — poll for job status and result
  GET  /health               — liveness check

Start with:
  uvicorn coordination.service.app:app --host 0.0.0.0 --port 8001

Environment variables:
  COORDINATION_OUTPUT_ROOT   — base dir for run outputs (default: var/coord_outputs)
  COORDINATION_MAX_WORKERS   — parallel extraction workers (default: 2)
  COORDINATION_CACHE_ROOT    — accore cache dir (default: <output_root>/cache)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
import traceback
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from .job_store import JobStore
from .pipeline import FileInput, PipelineConfig, run_clash_pipeline
from .schemas import FileMetadataItem, JobCreatedResponse, JobStatusResponse

logger = logging.getLogger("dupla.coordination.service")

# ── Configuration ─────────────────────────────────────────────────────────────

_OUTPUT_ROOT = Path(os.environ.get("COORDINATION_OUTPUT_ROOT", "var/coord_outputs")).resolve()
_MAX_WORKERS = int(os.environ.get("COORDINATION_MAX_WORKERS", "2"))
_CACHE_ROOT_ENV = os.environ.get("COORDINATION_CACHE_ROOT")
_CACHE_ROOT = Path(_CACHE_ROOT_ENV).resolve() if _CACHE_ROOT_ENV else _OUTPUT_ROOT / "cache"

# ── App + shared state ─────────────────────────────────────────────────────────

app = FastAPI(
    title="Dupla Coordination Service",
    description="Clash detection pipeline for multi-discipline CAD files",
    version="1.0.0",
)

_job_store = JobStore(persist_dir=_OUTPUT_ROOT / ".jobs")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs/clash-analysis", response_model=JobCreatedResponse, status_code=202)
async def enqueue_clash_analysis(
    files: list[UploadFile] = File(...),
    profile_slug: str = Form(...),
    project_name: str = Form(...),
    file_metadata: str = Form(...),
) -> JSONResponse:
    """Accept uploaded CAD files and start a clash analysis job.

    Multipart body (same as what clash_service.py sends):
      files          — one UploadFile per CAD file
      profile_slug   — "folder" (currently only one profile is supported)
      project_name   — display name for reports
      file_metadata  — JSON array of FileMetadataItem objects
    """
    try:
        raw_metadata: list[dict[str, Any]] = json.loads(file_metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"file_metadata JSON inválido: {exc}")

    if len(files) != len(raw_metadata):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Se recibieron {len(files)} archivos pero {len(raw_metadata)} entradas de metadata.",
        )

    try:
        metadata_items = [FileMetadataItem.model_validate(m) for m in raw_metadata]
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"file_metadata inválida: {exc}")

    # Read file bytes before returning control (UploadFile is not thread-safe)
    file_bytes: list[bytes] = []
    for uf in files:
        content = await uf.read()
        file_bytes.append(content)

    job = _job_store.create()
    job_id = job.job_id

    # Run the pipeline in a background daemon thread
    thread = threading.Thread(
        target=_run_pipeline_thread,
        args=(job_id, project_name, metadata_items, file_bytes),
        daemon=True,
        name=f"clash-job-{job_id[:8]}",
    )
    thread.start()

    return JSONResponse(content={"job_id": job_id}, status_code=202)


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    record = _job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job no encontrado: {job_id}")
    return JobStatusResponse(
        job_id=record.job_id,
        status=record.status,
        result=record.result,
        error=record.error,
    )


# ── Background pipeline runner ─────────────────────────────────────────────────


def _run_pipeline_thread(
    job_id: str,
    project_name: str,
    metadata_items: list[FileMetadataItem],
    file_bytes: list[bytes],
) -> None:
    tmp_dir: Path | None = None
    try:
        _job_store.update(job_id, status="running")
        logger.info("Job %s started: project=%r files=%d", job_id, project_name, len(file_bytes))

        # Write uploaded files to a temp directory
        tmp_dir = Path(tempfile.mkdtemp(prefix=f"clash_{job_id[:8]}_"))
        inputs: list[FileInput] = []
        for meta, content in zip(metadata_items, file_bytes):
            dest = tmp_dir / meta.original_name
            dest.write_bytes(content)
            inputs.append(
                FileInput(
                    path=dest,
                    original_name=meta.original_name,
                    discipline_bucket=meta.discipline_bucket,
                )
            )

        run_dir = _OUTPUT_ROOT / f"job_{job_id[:8]}"
        run_dir.mkdir(parents=True, exist_ok=True)

        config = PipelineConfig(
            max_workers=_MAX_WORKERS,
            cache_root=_CACHE_ROOT,
        )

        result = run_clash_pipeline(
            inputs=inputs,
            project_name=project_name,
            output_dir=run_dir,
            config=config,
        )

        _job_store.update(job_id, status="completed", result=result)
        incidents = len((result.get("artifacts", {}).get("primary_incidents") or {}).get("incidents") or [])
        logger.info("Job %s completed: %d incidents", job_id, incidents)

    except Exception:
        tb = traceback.format_exc()
        logger.error("Job %s failed:\n%s", job_id, tb)
        _job_store.update(job_id, status="failed", error=tb[-2000:])
    finally:
        if tmp_dir and tmp_dir.exists():
            try:
                shutil.rmtree(tmp_dir)
            except OSError:
                pass


# ── Entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=8001)
