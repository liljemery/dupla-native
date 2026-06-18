"""HTTP request/response models for the coordination service."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class FileMetadataItem(BaseModel):
    original_name: str
    discipline: str | None = None
    discipline_bucket: str
    folder_path: str | None = None


class JobCreatedResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # "queued" | "running" | "completed" | "failed"
    result: dict[str, Any] | None = None
    error: str | None = None
