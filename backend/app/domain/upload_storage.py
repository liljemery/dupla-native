"""Helpers for streaming uploaded files to disk."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile, status

UPLOAD_CHUNK_SIZE = 1024 * 1024


async def write_upload_to_path(
    upload: UploadFile,
    destination: Path,
    *,
    max_bytes: Optional[int] = None,
    max_label: Optional[str] = None,
) -> int:
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as out:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if max_bytes is not None and total > max_bytes:
                    detail = "Archivo demasiado grande"
                    if max_label:
                        detail = f"{detail} (max. {max_label})"
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=detail,
                    )
                out.write(chunk)
    except Exception:
        try:
            if destination.is_file():
                destination.unlink()
        except OSError:
            pass
        raise
    return total
