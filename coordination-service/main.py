from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Form
from redis import Redis
from rq import Queue
from rq.job import Job
from typing import List, Optional
from dotenv import load_dotenv
from pathlib import Path
import os
import logging
import uuid
import json

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(title="Dupla Coordination Service")
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_conn = Redis.from_url(redis_url)
q = Queue("dupla_coordination", connection=redis_conn)

OUTPUT_ROOT = Path(os.getenv("COORDINATION_OUTPUT_ROOT", "/app/output"))


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "coordination"}


@app.post("/jobs/clash-analysis")
async def enqueue_clash_analysis(
    files: List[UploadFile] = File(...),
    profile_slug: Optional[str] = Form(None),
    project_name: Optional[str] = Form("Proyecto"),
    file_metadata: Optional[str] = Form(None),
    control_points_json: Optional[str] = Form(None),
    reanalysis_clash_code: Optional[str] = Form(None),
    x_correlation_id: Optional[str] = Header(None),
):
    try:
        correlation_id = x_correlation_id or str(uuid.uuid4())
        meta_list: list[dict] = []
        if file_metadata:
            try:
                parsed = json.loads(file_metadata)
                if isinstance(parsed, list):
                    meta_list = parsed
            except json.JSONDecodeError:
                meta_list = []

        meta_by_name: dict[str, dict] = {}
        for item in meta_list:
            if isinstance(item, dict) and item.get("original_name"):
                meta_by_name[str(item["original_name"])] = item

        uploads_dir = OUTPUT_ROOT / correlation_id / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        file_entries: list[dict] = []
        for uf in files:
            name_lower = (uf.filename or "").lower()
            if not (name_lower.endswith(".dwg") or name_lower.endswith(".dxf")):
                await uf.read()  # drain to avoid connection issues
                continue
            original_name = uf.filename or "upload.dwg"
            meta = meta_by_name.get(original_name, {})

            safe_name = Path(original_name).name
            dest = uploads_dir / safe_name
            dest.write_bytes(await uf.read())

            file_entries.append(
                {
                    "original_name": original_name,
                    "path": str(dest),
                    "discipline": meta.get("discipline"),
                    "discipline_bucket": meta.get("discipline_bucket"),
                    "folder_path": meta.get("folder_path"),
                }
            )

        if not file_entries:
            raise HTTPException(status_code=422, detail="No .dwg or .dxf file found in uploaded files")

        slug = (profile_slug or "folder").strip() or "folder"

        from tasks.run_clash import run_clash_job

        control_points: list[dict] = []
        if control_points_json:
            try:
                parsed_cp = json.loads(control_points_json)
                if isinstance(parsed_cp, list):
                    control_points = parsed_cp
            except json.JSONDecodeError:
                pass

        job = q.enqueue(
            run_clash_job,
            file_entries,
            slug,
            project_name or "Proyecto",
            correlation_id,
            control_points,
            reanalysis_clash_code,
            job_timeout=int(os.getenv("COORDINATION_JOB_TIMEOUT_SECONDS", "3600")),
        )
        return {"job_id": job.id, "status": "queued", "profile_slug": slug}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to enqueue clash job")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str, x_correlation_id: Optional[str] = Header(None)):
    correlation_id = x_correlation_id or "unknown"
    logger.info("Job status %s correlation=%s", job_id, correlation_id)
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.is_finished:
        return {"job_id": job_id, "status": "completed", "result": job.result}
    if job.is_failed:
        return {"job_id": job_id, "status": "failed", "error": str(job.exc_info)}
    return {"job_id": job_id, "status": job.get_status()}
