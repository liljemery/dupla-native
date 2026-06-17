"""
Dupla pipeline stage cache.

Two-tier (Redis + disk) deterministic cache for expensive pipeline stages
(APS extraction, PDF render, Vision per page, PartidaGenerator batch).
Same input hash returns cached output without re-running the compute.

Backends
--------
- redis: fast, ephemeral, shared between processes; TTL applied.
- disk:  local cache dir (DUPLA_CACHE_DIR or processor/var/cache by default).
- both (default): write-through to both; read prefers redis then disk.

Env flags
---------
- DUPLA_NO_CACHE=1            Bypass cache entirely (compute + write).
- DUPLA_CACHE_BACKEND=redis|disk|both   (default: both)
- DUPLA_CACHE_DIR=/app/cache  Disk root.
- DUPLA_CACHE_TTL_DAYS=7      Redis TTL.
- DUPLA_CACHE_DISABLE_WRITE=1 Read-only mode (debug stale hits).
- REDIS_URL                   Standard.

Hash helpers
------------
sha256_bytes(b), sha256_json(obj), sha256_file(path).

Usage
-----
    from core.stage_cache import cached_stage, sha256_bytes

    def _compute():
        return expensive_extraction(...)

    result = cached_stage(
        stage="aps_extract",
        input_hash=sha256_bytes(dwg_bytes) + ":2d",
        compute_fn=_compute,
    )

Metrics
-------
The module keeps an in-process counter accessible via `get_stats()` and
`reset_stats()`. Workers should call `log_stats_summary()` at job end.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger("dupla.stage_cache")

T = TypeVar("T")

def _default_cache_dir() -> str:
    """Container path when present (Docker), else a repo-relative folder so bare
    (non-Docker) checkouts on Windows/macOS still get a writable cache."""
    if os.path.exists("/app/cache"):
        return "/app/cache"
    return str(Path(__file__).resolve().parent.parent / "cache")


_DEFAULT_CACHE_DIR = _default_cache_dir()
_DEFAULT_TTL_DAYS = 7
_REDIS_KEY_PREFIX = "dupla:stage_cache:"


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _env_bool(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _backend() -> str:
    raw = (os.getenv("DUPLA_CACHE_BACKEND") or "both").strip().lower()
    return raw if raw in {"redis", "disk", "both"} else "both"


def _cache_dir() -> Path:
    raw = (os.getenv("DUPLA_CACHE_DIR") or _DEFAULT_CACHE_DIR).strip()
    return Path(raw)


def _ttl_seconds() -> int:
    try:
        days = int((os.getenv("DUPLA_CACHE_TTL_DAYS") or str(_DEFAULT_TTL_DAYS)).strip())
    except ValueError:
        days = _DEFAULT_TTL_DAYS
    return max(60, days * 24 * 3600)


def _bypass() -> bool:
    return _env_bool("DUPLA_NO_CACHE")


def _write_disabled() -> bool:
    return _env_bool("DUPLA_CACHE_DISABLE_WRITE")


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def compose_key(*parts: str) -> str:
    """Stable composite key. Joins with ':' after stripping each part."""
    return ":".join(str(p).strip() for p in parts if p is not None and str(p).strip())


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class _Counters:
    hits: int = 0
    misses: int = 0
    writes: int = 0
    errors: int = 0
    bytes_written: int = 0
    bytes_read: int = 0
    seconds_saved_estimate: float = 0.0  # populated when compute_fn is wrapped


@dataclass
class _Stats:
    by_stage: dict[str, _Counters] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def bump(self, stage: str, **kw: Any) -> None:
        with self.lock:
            c = self.by_stage.setdefault(stage, _Counters())
            for k, v in kw.items():
                if hasattr(c, k):
                    setattr(c, k, getattr(c, k) + v)


_STATS = _Stats()


def get_stats() -> dict[str, dict[str, Any]]:
    with _STATS.lock:
        return {
            stage: {
                "hits": c.hits,
                "misses": c.misses,
                "writes": c.writes,
                "errors": c.errors,
                "bytes_written": c.bytes_written,
                "bytes_read": c.bytes_read,
                "seconds_saved_estimate": round(c.seconds_saved_estimate, 2),
            }
            for stage, c in _STATS.by_stage.items()
        }


def reset_stats() -> None:
    with _STATS.lock:
        _STATS.by_stage.clear()


def log_stats_summary() -> None:
    stats = get_stats()
    if not stats:
        logger.info("[cache] no stages exercised this run")
        return
    total_hits = sum(s["hits"] for s in stats.values())
    total_miss = sum(s["misses"] for s in stats.values())
    total_saved = sum(s["seconds_saved_estimate"] for s in stats.values())
    logger.info(
        "[cache] summary: %d hits / %d misses across %d stages (~%.1fs saved)",
        total_hits, total_miss, len(stats), total_saved,
    )
    for stage, s in sorted(stats.items()):
        logger.info(
            "[cache]   %-24s hits=%d miss=%d writes=%d err=%d saved=~%.1fs",
            stage, s["hits"], s["misses"], s["writes"], s["errors"], s["seconds_saved_estimate"],
        )


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

_REDIS = None
_REDIS_LOCK = threading.Lock()


def _get_redis() -> Any | None:
    global _REDIS
    if _REDIS is not None:
        return _REDIS
    with _REDIS_LOCK:
        if _REDIS is not None:
            return _REDIS
        try:
            from redis import Redis  # type: ignore
            url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
            client = Redis.from_url(url)
            client.ping()
            _REDIS = client
            return _REDIS
        except Exception:
            logger.warning("[cache] redis unavailable — falling back to disk only", exc_info=True)
            _REDIS = False  # sentinel: tried and failed
            return None


def _redis_get(key: str) -> bytes | None:
    client = _get_redis()
    if not client:
        return None
    try:
        return client.get(_REDIS_KEY_PREFIX + key)
    except Exception:
        logger.debug("[cache] redis GET failed for %s", key, exc_info=True)
        return None


def _redis_set(key: str, value: bytes, ttl: int) -> bool:
    client = _get_redis()
    if not client:
        return False
    try:
        client.setex(_REDIS_KEY_PREFIX + key, ttl, value)
        return True
    except Exception:
        logger.debug("[cache] redis SET failed for %s", key, exc_info=True)
        return False


def _safe_filename(key: str) -> str:
    """Hash the composed cache key so on-disk filenames are bounded and
    filesystem-safe (POSIX NAME_MAX is 255 bytes; ext4 enforces it strictly).

    Previously the raw key was used as the filename, which meant any caller
    that forgot to hash a variable-length input would poison the cache directory
    with unwritable paths. Centralizing the hash here removes that footgun.
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json"


def _disk_path(stage: str, key: str) -> Path:
    root = _cache_dir() / stage
    filename = _safe_filename(key)
    # shard by first 2 chars of the digest to keep folders shallow
    shard = filename[:2]
    return root / shard / filename


_MIGRATION_DONE = False
_MIGRATION_LOCK = threading.Lock()


def _warn_long_filenames_once() -> None:
    """One-time scan: log a warning if the cache dir contains pre-migration
    entries with very long basenames (the unhashed-filename layout). Those
    files are unreachable through the new hashed-path layout and are treated
    as cache misses on read. We do not auto-delete — the operator should
    clean them up explicitly (see PR description for the rm command)."""
    global _MIGRATION_DONE
    if _MIGRATION_DONE:
        return
    with _MIGRATION_LOCK:
        if _MIGRATION_DONE:
            return
        _MIGRATION_DONE = True
        root = _cache_dir()
        if not root.exists():
            return
        try:
            long_count = 0
            for p in root.rglob("*.json"):
                if len(p.name) > 200:
                    long_count += 1
                    if long_count >= 5:
                        break
            if long_count:
                logger.warning(
                    "[cache] found pre-migration entries with long filenames in %s; "
                    "they are ignored (treated as misses). Remove manually if desired.",
                    root,
                )
        except Exception:
            logger.debug("[cache] migration scan failed", exc_info=True)


def _disk_get(stage: str, key: str) -> bytes | None:
    _warn_long_filenames_once()
    path = _disk_path(stage, key)
    if not path.exists():
        return None
    try:
        return path.read_bytes()
    except Exception:
        logger.debug("[cache] disk read failed: %s", path, exc_info=True)
        return None


def _disk_set(stage: str, key: str, value: bytes) -> bool:
    _warn_long_filenames_once()
    path = _disk_path(stage, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_bytes(value)
        os.replace(tmp, path)
        return True
    except Exception:
        logger.debug("[cache] disk write failed: %s", path, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def cache_get(stage: str, key: str) -> Any | None:
    """Lookup without compute. Returns deserialized JSON or None."""
    if _bypass():
        return None
    backend = _backend()
    raw: bytes | None = None
    if backend in {"redis", "both"}:
        raw = _redis_get(f"{stage}:{key}")
    if raw is None and backend in {"disk", "both"}:
        raw = _disk_get(stage, key)
    if raw is None:
        return None
    try:
        result = json.loads(raw.decode("utf-8"))
    except Exception:
        _STATS.bump(stage, errors=1)
        return None
    _STATS.bump(stage, hits=1, bytes_read=len(raw))
    return result


def cache_set(stage: str, key: str, value: Any) -> None:
    """Store value (JSON-serializable) in configured backends."""
    if _bypass() or _write_disabled():
        return
    try:
        raw = json.dumps(value, default=str, ensure_ascii=False).encode("utf-8")
    except Exception:
        _STATS.bump(stage, errors=1)
        logger.warning("[cache] failed to serialize %s value, skipping write", stage)
        return
    backend = _backend()
    ttl = _ttl_seconds()
    wrote = False
    if backend in {"redis", "both"}:
        wrote = _redis_set(f"{stage}:{key}", raw, ttl) or wrote
    if backend in {"disk", "both"}:
        wrote = _disk_set(stage, key, raw) or wrote
    if wrote:
        _STATS.bump(stage, writes=1, bytes_written=len(raw))


def cached_stage(
    stage: str,
    input_hash: str,
    compute_fn: Callable[[], T],
    *,
    force: bool = False,
) -> T:
    """
    Run compute_fn(); cache result under (stage, input_hash); return result.
    On a hit, compute_fn is NOT called and the cached value is returned.

    `force=True` recomputes and overwrites the cache entry (used for cache
    refresh / manual invalidation paths).
    """
    if not force and not _bypass():
        hit = cache_get(stage, input_hash)
        if hit is not None:
            logger.info("[cache] HIT %s:%s", stage, input_hash[:12])
            return hit  # type: ignore[return-value]
    _STATS.bump(stage, misses=1)
    logger.info("[cache] MISS %s:%s — computing", stage, input_hash[:12])
    t0 = time.monotonic()
    result = compute_fn()
    elapsed = time.monotonic() - t0
    _STATS.bump(stage, seconds_saved_estimate=elapsed)  # future hits "save" this much
    cache_set(stage, input_hash, result)
    return result


async def cached_stage_async(
    stage: str,
    input_hash: str,
    compute_async: Callable[[], Awaitable[T]],
    *,
    force: bool = False,
) -> T:
    """
    Async cached_stage with single-flight (in-proc coalesce + Redis lock).

    Prevents cache stampede when several concurrent tasks request the same key
    before the winner has written. Lock TTL is governed by
    DUPLA_LOCK_TTL_SECONDS in core.concurrency.
    """
    if not force and not _bypass():
        hit = cache_get(stage, input_hash)
        if hit is not None:
            logger.info("[cache] HIT %s:%s", stage, input_hash[:12])
            return hit  # type: ignore[return-value]

    # Lazy import to avoid a circular dependency at module load.
    from core.concurrency import single_flight_async

    lock_key = f"{stage}:{input_hash}"
    _STATS.bump(stage, misses=1)
    logger.info("[cache] MISS %s:%s — computing (single-flight)", stage, input_hash[:12])

    async def _compute_and_store() -> T:
        # Re-check cache: another waiter may have already populated it during
        # the brief window between probe and lock acquisition.
        hit = cache_get(stage, input_hash)
        if hit is not None:
            return hit  # type: ignore[return-value]
        t0 = time.monotonic()
        result = await compute_async()
        _STATS.bump(stage, seconds_saved_estimate=time.monotonic() - t0)
        cache_set(stage, input_hash, result)
        return result

    return await single_flight_async(
        lock_key,
        _compute_and_store,
        cache_probe=lambda: cache_get(stage, input_hash),
    )


def invalidate(stage: str | None = None, key: str | None = None) -> int:
    """
    Clear cache entries. Returns count of entries removed (disk only counted).

    - invalidate() — clear everything (DANGER).
    - invalidate(stage="aps_extract") — clear all entries for one stage.
    - invalidate(stage="aps_extract", key="<hash>") — clear single entry.
    """
    removed = 0
    # Redis side
    client = _get_redis()
    if client:
        try:
            if stage and key:
                client.delete(_REDIS_KEY_PREFIX + f"{stage}:{key}")
            elif stage:
                for k in client.scan_iter(match=_REDIS_KEY_PREFIX + f"{stage}:*"):
                    client.delete(k)
            else:
                for k in client.scan_iter(match=_REDIS_KEY_PREFIX + "*"):
                    client.delete(k)
        except Exception:
            logger.warning("[cache] redis invalidate failed", exc_info=True)
    # Disk side
    root = _cache_dir()
    if not root.exists():
        return removed
    if stage and key:
        path = _disk_path(stage, key)
        if path.exists():
            path.unlink()
            removed += 1
    elif stage:
        stage_root = root / stage
        if stage_root.exists():
            for p in stage_root.rglob("*.json"):
                p.unlink()
                removed += 1
    else:
        for p in root.rglob("*.json"):
            p.unlink()
            removed += 1
    logger.info("[cache] invalidated stage=%s key=%s (disk_removed=%d)", stage, key, removed)
    return removed
