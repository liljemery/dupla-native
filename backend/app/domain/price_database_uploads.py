"""Reglas para archivos de base de precios (PDF, Excel, CSV)."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status

ALLOWED_PRICE_DB_EXTENSIONS = frozenset({".pdf", ".xlsx", ".xls", ".csv"})


def sanitize_price_db_filename(raw: str) -> str:
    name = Path(raw or "file").name.replace("..", "_").strip()
    return name if name else "file"


def validate_price_db_extension(filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_PRICE_DB_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Solo se permiten archivos .pdf, .xlsx, .xls o .csv",
        )
