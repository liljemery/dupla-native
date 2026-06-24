from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Form, Query
from fastapi.responses import JSONResponse, FileResponse
from redis import Redis
from rq import Queue
from rq.job import Job
from typing import List, Optional
from dotenv import load_dotenv
import os
import logging

from core.stage_cache import get_stats as cache_get_stats, invalidate as cache_invalidate

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(title="Dupla Processor Service")
redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
redis_conn = Redis.from_url(redis_url)
q = Queue("dupla_processing", connection=redis_conn)


def _env_bool(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


@app.on_event("startup")
def log_multi_discipline_mode() -> None:
    if _env_bool("DUPLA_ALLOW_MULTI_DISCIPLINE"):
        logger.warning(
            "DUPLA_ALLOW_MULTI_DISCIPLINE is enabled; 'todas' runs process 4 disciplines "
            "and should be expected to cost roughly 4x a single-discipline cold run."
        )


def _job_timeout_seconds() -> int:
    raw = (os.getenv("DUPLA_JOB_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return 3600
    try:
        return max(300, int(raw))
    except ValueError:
        logger.warning("Invalid DUPLA_JOB_TIMEOUT_SECONDS=%r; using 3600", raw)
        return 3600

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/cache/stats")
def cache_stats():
    """Return in-process cache hit/miss counters per stage."""
    return cache_get_stats()


@app.post("/cache/clear")
def cache_clear(
    stage: Optional[str] = Query(None, description="Stage name; omit to clear ALL"),
    key: Optional[str] = Query(None, description="Specific entry key; requires stage"),
):
    """Invalidate cache entries.

    - No params: wipe everything (use with care).
    - stage only: wipe all entries for one stage.
    - stage + key: wipe single entry.
    """
    if key and not stage:
        raise HTTPException(status_code=400, detail="key requires stage")
    removed = cache_invalidate(stage=stage, key=key)
    return {"stage": stage, "key": key, "disk_removed": removed}

@app.post("/jobs/process")
async def process_project(
    files: List[UploadFile] = File(...),
    discipline: Optional[str] = Form(None),
    project_name: Optional[str] = Form(None),
    x_correlation_id: Optional[str] = Header(None),
):
    """
    Accept one or more uploaded files (DWG / PDF).
    All .dwg/.dxf files are extracted via the local ezdxf pipeline (LibreDWG + ezdxf)
    and merged into a single
    unified cad_facts; the first .pdf file found is used for vision analysis.

    Optional ``discipline`` form field (arquitectura | estructura | electrico |
    sanitario | todas) controls calculation. When omitted the worker extracts
    planos first and then auto-continues into budget (unless
    DUPLA_EXTRACTION_ONLY=1).
    """
    try:
        correlation_id = x_correlation_id or "unknown"
        logger.info(f"Received job processing request with correlation ID: {correlation_id}")
        dwg_files: List[tuple[str, bytes]] = []
        dxf_files: List[tuple[str, bytes]] = []
        pdf_files: List[tuple[str, bytes]] = []

        for uf in files:
            name_lower = (uf.filename or "").lower()
            content = await uf.read()
            if name_lower.endswith(".dwg"):
                dwg_files.append((uf.filename or "upload.dwg", content))
            elif name_lower.endswith(".dxf"):
                dxf_files.append((uf.filename or "upload.dxf", content))
            elif name_lower.endswith(".pdf"):
                pdf_files.append((uf.filename or "upload.pdf", content))

        if not dwg_files and not dxf_files:
            raise HTTPException(status_code=422, detail="No .dwg or .dxf file found in uploaded files")

        from tasks import run_dupla_pipeline
        job_timeout = _job_timeout_seconds()
        logger.info(
            "Enqueuing processor job: discipline=%s project_name=%s dwgs=%d dxfs=%d pdfs=%d timeout=%ss",
            discipline or "(base_extraction)",
            project_name or "(none)",
            len(dwg_files),
            len(dxf_files),
            len(pdf_files),
            job_timeout,
        )
        job = q.enqueue(
            run_dupla_pipeline,
            dwg_files,
            pdf_files=pdf_files,
            discipline_id=discipline,
            project_name=project_name,
            correlation_id=correlation_id,
            dxf_files=dxf_files,
            job_timeout=job_timeout,
        )
        return {"job_id": job.id, "status": "queued"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _resolve_finished_status(result: object) -> str:
    """Map processor result to API job status."""
    if not isinstance(result, dict):
        return "completed"
    rows = result.get("rows") or []
    mode = (result.get("output") or {}).get("mode") or (result.get("extraction") or {}).get("mode")
    if mode == "base_extraction" and not rows:
        return "completed_partial"
    return "completed"


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str, x_correlation_id: Optional[str] = Header(None)):
    correlation_id = x_correlation_id or "unknown"
    logger.info(f"Received job status request for {job_id} with correlation ID: {correlation_id}")
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.is_finished:
        status = _resolve_finished_status(job.result)
        return {"job_id": job_id, "status": status, "result": job.result}
    elif job.is_failed:
        return {"job_id": job_id, "status": "failed", "error": str(job.exc_info)}
    else:
        payload: dict[str, object] = {"job_id": job_id, "status": job.get_status()}
        meta = job.meta or {}
        if meta.get("phase"):
            payload["phase"] = meta["phase"]
        if meta.get("phase_detail"):
            payload["phase_detail"] = meta["phase_detail"]
        return payload


@app.get("/jobs/{job_id}/download")
def download_job_artifacts(job_id: str):
    """Stream the zipped deliverables (Excel, BC3, reports) for a finished job.

    Reads the archive path from the job result. The output directory is a
    shared volume (dupla_outputs) so this API container can serve files the
    worker container produced.
    """
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.is_finished:
        raise HTTPException(status_code=409, detail="Job not finished")

    result = job.result if isinstance(job.result, dict) else {}
    output = result.get("output") or {}
    archive = output.get("archive")
    if not archive or not os.path.exists(archive):
        raise HTTPException(status_code=404, detail="No artifact archive available for this job")

    return FileResponse(
        archive,
        media_type="application/zip",
        filename=os.path.basename(archive),
    )
