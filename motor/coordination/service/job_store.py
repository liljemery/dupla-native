"""Thread-safe in-memory job store with optional disk persistence."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class JobRecord:
    job_id: str
    status: str  # "queued" | "running" | "completed" | "failed"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result: dict[str, Any] | None = None
    error: str | None = None


class JobStore:
    """Thread-safe in-memory job registry with optional disk persistence for crash recovery."""

    def __init__(self, persist_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, JobRecord] = {}
        self._persist_dir = persist_dir
        if persist_dir:
            persist_dir.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def create(self) -> JobRecord:
        job_id = str(uuid.uuid4())
        record = JobRecord(job_id=job_id, status="queued")
        with self._lock:
            self._jobs[job_id] = record
        self._flush_status(record)
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs: Any) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            for k, v in kwargs.items():
                setattr(record, k, v)
            self._flush_status(record)

    def _flush_status(self, record: JobRecord) -> None:
        if not self._persist_dir:
            return
        path = self._persist_dir / f"{record.job_id}.status.json"
        data = {
            "job_id": record.job_id,
            "status": record.status,
            "created_at": record.created_at,
            "error": record.error,
        }
        try:
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _load_from_disk(self) -> None:
        if not self._persist_dir:
            return
        for path in sorted(self._persist_dir.glob("*.status.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                job_id = data["job_id"]
                status = data.get("status", "unknown")
                # Jobs that were "running" at last persist are interrupted — mark as failed
                if status == "running":
                    status = "failed"
                self._jobs[job_id] = JobRecord(
                    job_id=job_id,
                    status=status,
                    created_at=data.get("created_at", ""),
                    error=data.get("error") or ("Interrupted by service restart" if status == "failed" else None),
                )
            except Exception:
                pass
