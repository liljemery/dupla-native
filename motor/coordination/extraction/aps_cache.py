"""Small JSON cache helpers for APS coordination extractors."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def file_cache_key(path: Path) -> str:
    """Content-based cache key so staged copies reuse APS extractions."""
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(str(stat.st_size).encode("ascii"))
    digest.update(str(int(stat.st_mtime_ns)).encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:20]


def cache_json_path(cache_root: Path, *, key: str, suffix: str) -> Path:
    safe_suffix = suffix.replace("/", "_")
    return cache_root / f"{key}.{safe_suffix}.json"


def load_cached_json(cache_root: Path | None, *, key: str, suffix: str) -> Any | None:
    if cache_root is None:
        return None
    path = cache_json_path(cache_root, key=key, suffix=suffix)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_cached_json(cache_root: Path | None, *, key: str, suffix: str, payload: Any) -> None:
    if cache_root is None:
        return
    cache_root.mkdir(parents=True, exist_ok=True)
    path = cache_json_path(cache_root, key=key, suffix=suffix)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
