"""
Runtime path resolution that works both inside Docker (/app/...) and on a bare
Windows/macOS/Linux checkout (no container).

The original pipeline hardcoded container paths like ``/app/data`` and
``/app/output``. On a non-Docker host those never exist, so the constructor
pricing Excel, BC3 catalogs and PRES.xlsx silently failed to load and the
budget fell back to "no APU pricing". Every directory here is resolved as:

    1. explicit env var (DUPLA_DATA_DIR, DUPLA_OUTPUT_DIR, ...), else
    2. the legacy ``/app/<name>`` path when it actually exists (Docker), else
    3. a repo-relative folder under ``processor/`` (bare checkout).

This keeps existing Docker deployments working while making local runs find the
files that ship in the repository (processor/data/...).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("dupla.paths")

# .../processor/core/paths.py -> .../processor
_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent


def _resolve_dir(env_var: str, container_path: str, repo_subdir: str) -> Path:
    explicit = (os.getenv(env_var) or "").strip()
    if explicit:
        return Path(explicit)
    container = Path(container_path)
    if container.exists():
        return container
    return _PROCESSOR_ROOT / repo_subdir


def data_dir() -> Path:
    """Bundled inputs: pricing Excel, BC3 catalogs, PRES.xlsx."""
    return _resolve_dir("DUPLA_DATA_DIR", "/app/data", "data")


def output_dir() -> Path:
    """Run outputs / deliverables root."""
    return _resolve_dir("DUPLA_OUTPUT_DIR", "/app/output", "output")


def knowledge_dir() -> Path:
    """Office methodology and prompt knowledge base."""
    return _resolve_dir("DUPLA_KNOWLEDGE_DIR", "/app/knowledge", "knowledge")


def artifact_dir() -> Path:
    """Content-addressed extraction artifacts (APS + rendered pages)."""
    return _resolve_dir("DUPLA_ARTIFACT_DIR", "/app/artifacts", "artifacts")


def cache_dir() -> Path:
    """Stage cache root."""
    return _resolve_dir("DUPLA_CACHE_DIR", "/app/cache", "cache")


def pricing_excel_path() -> Path | None:
    """Locate the constructor pricing Excel (USD).

    Checks, in order: an explicit ``DUPLA_PRICING_EXCEL`` override, then
    ``<data_dir>/Lista de precios-analisis-MO.xlsx``, then the copy that lives at
    the processor root (where the repo also keeps it). Returns ``None`` when no
    file is found so the caller can log and continue without APU pricing.
    """
    explicit = (os.getenv("DUPLA_PRICING_EXCEL") or "").strip()
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None

    name = "Lista de precios-analisis-MO.xlsx"
    candidates = [data_dir() / name, _PROCESSOR_ROOT / name]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
