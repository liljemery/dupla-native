"""Shared path defaults for native dev (Windows, macOS, Linux)."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def coordination_output_root() -> Path:
    override = (os.getenv("COORDINATION_OUTPUT_ROOT") or "").strip()
    if override:
        return Path(override)
    return repo_root() / "var" / "coord_outputs"


def coordination_cache_root() -> Path:
    override = (os.getenv("COORDINATION_CACHE_ROOT") or "").strip()
    if override:
        cache = Path(override)
    else:
        cache = coordination_output_root() / "cad_cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def default_redis_url() -> str:
    return (os.getenv("REDIS_URL") or "redis://127.0.0.1:6379/0").strip()


def load_project_env() -> None:
    """Load backend/.env so coordination credentials are visible to the worker."""
    from dotenv import load_dotenv

    load_dotenv()
    backend_env = repo_root() / "backend" / ".env"
    if backend_env.is_file():
        # backend/.env is the source of truth for coordination (APS, smoke mode, paths).
        # override=True so a stale shell COORDINATION_SMOKE_MODE=true cannot win over .env false.
        load_dotenv(backend_env, override=True)
