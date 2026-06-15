"""Reglas comunes para archivos de proyecto en disco (extensiones permitidas)."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status

ALLOWED_PROJECT_FILE_EXTENSIONS = frozenset({".dwg", ".dxf", ".pdf", ".ifc", ".docx"})


def sanitize_project_original_filename(raw: str) -> str:
    name = Path(raw or "file").name.replace("..", "_").strip()
    return name if name else "file"


def validate_project_file_extension(filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_PROJECT_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Solo se permiten archivos .dwg, .dxf, .pdf, .ifc o .docx",
        )
