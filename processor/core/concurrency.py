"""
Dupla concurrency primitives.

Provides:
- single_flight_async(stage, key, compute_async): coalesces in-process
  duplicate requests and adds a distributed Redis lock to prevent
  cross-process cache stampede when paralelizing pipeline stages.
- gather_throttled(coros, semaphore): asyncio.gather respecting a Semaphore.
- run_in_thread(fn, *args, **kw): typed asyncio.to_thread wrapper.
- get_pdf_executor(): lazy-initialized module-level ProcessPoolExecutor
  for CPU-bound pymupdf page rendering, shut down via atexit.

Env vars
--------
DUPLA_LOCK_TTL_SECONDS      Redis lock TTL (default 120; bumped from 600
                            so a hard-killed worker does not park siblings
                            longer than a real OpenAI/APS call timeout).
OPENAI_VISION_CONCURRENCY   Max concurrent vision calls (default 8).
OPENAI_PARTIDA_CONCURRENCY  Max concurrent partida-generator calls (default 4).
APS_CONCURRENCY             Max concurrent APS extractions (default 2;
                            Autodesk rate-limits aggressively).
PDF_RENDER_WORKERS          Process pool size for pymupdf rendering
                            (default min(cpu_count, 4)).
DUPLA_SINGLE_FLIGHT_POLL_S  Seconds between cache polls while another
                            worker holds the lock (default 1.0).
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import os
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger("dupla.concurrency")

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("[concurrency] %s=%r invalid, using default %d", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0.05, float(raw))
    except ValueError:
        return default


def lock_ttl_seconds() -> int:
    return _env_int("DUPLA_LOCK_TTL_SECONDS", 120)


def vision_concurrency() -> int:
    return _env_int("OPENAI_VISION_CONCURRENCY", 8)


def partida_concurrency() -> int:
    return _env_int("OPENAI_PARTIDA_CONCURRENCY", 4)


def aps_concurrency() -> int:
    return _env_int("APS_CONCURRENCY", 2)


def pdf_render_workers() -> int:
    raw = (os.getenv("PDF_RENDER_WORKERS") or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    cpus = os.cpu_count() or 4
    return min(cpus, 4)


# ---------------------------------------------------------------------------
# Semaphore registry (named, cached per-loop)
# ---------------------------------------------------------------------------

_SEM_REGISTRY: dict[tuple[int, str], asyncio.Semaphore] = {}
_SEM_LOCK = threading.Lock()


def get_semaphore(name: str, size: int) -> asyncio.Semaphore:
    """Return a named asyncio.Semaphore unique per running event loop."""
    loop_id = id(asyncio.get_event_loop())
    key = (loop_id, name)
    with _SEM_LOCK:
        sem = _SEM_REGISTRY.get(key)
        if sem is None:
            sem = asyncio.Semaphore(size)
            _SEM_REGISTRY[key] = sem
        return sem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def run_in_thread(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """asyncio.to_thread wrapper preserving typing."""
    return await asyncio.to_thread(fn, *args, **kwargs)


async def gather_throttled(
    coros: list[Awaitable[T]],
    semaphore: asyncio.Semaphore,
    *,
    return_exceptions: bool = False,
) -> list[T]:
    """asyncio.gather but each coro acquires the semaphore first."""
    async def _wrap(c: Awaitable[T]) -> T:
        async with semaphore:
            return await c
    return await asyncio.gather(
        *[_wrap(c) for c in coros],
        return_exceptions=return_exceptions,
    )


# ---------------------------------------------------------------------------
# Single-flight: in-proc coalesce + distributed Redis lock
# ---------------------------------------------------------------------------

_INFLIGHT: dict[str, asyncio.Future] = {}
_INFLIGHT_LOCK_PER_LOOP: dict[int, asyncio.Lock] = {}


def _inflight_lock() -> asyncio.Lock:
    loop_id = id(asyncio.get_event_loop())
    lock = _INFLIGHT_LOCK_PER_LOOP.get(loop_id)
    if lock is None:
        lock = asyncio.Lock()
        _INFLIGHT_LOCK_PER_LOOP[loop_id] = lock
    return lock


async def _coalesce(key: str, compute_async: Callable[[], Awaitable[T]]) -> T:
    """In-process: piggyback on a sibling task already computing this key."""
    async with _inflight_lock():
        fut = _INFLIGHT.get(key)
        if fut is not None:
            logger.debug("[single_flight] in-proc coalesce on %s", key)
            return await fut
        loop = asyncio.get_event_loop()
        my_fut: asyncio.Future = loop.create_future()
        _INFLIGHT[key] = my_fut
    try:
        result = await compute_async()
        if not my_fut.done():
            my_fut.set_result(result)
        return result
    except BaseException as exc:
        if not my_fut.done():
            my_fut.set_exception(exc)
        raise
    finally:
        _INFLIGHT.pop(key, None)


async def single_flight_async(
    lock_key: str,
    compute_async: Callable[[], Awaitable[T]],
    *,
    cache_probe: Callable[[], T | None] | None = None,
    poll_interval_seconds: float | None = None,
    max_wait_seconds: int | None = None,
) -> T:
    """
    Coordinate concurrent calls so only one actually runs compute_async.

    Layers:
      1. In-process: asyncio Future per key. Sibling tasks await the same Future.
      2. Cross-process: Redis SETNX lock (TTL = DUPLA_LOCK_TTL_SECONDS, default 120s).
         Waiters poll `cache_probe` until they see the written value or the lock
         disappears, then fall through and compute themselves.

    `cache_probe` is a no-arg callable returning the cached value (or None). When
    omitted, waiters cannot see the result early and will just race once the lock
    is released. Pass it for stages that go through stage_cache.

    Lock TTL deliberately short (120s default): if a worker crashes mid-compute
    the lock auto-expires within an OpenAI/APS timeout window rather than
    parking siblings for the legacy 600s.
    """
    poll = poll_interval_seconds if poll_interval_seconds is not None else _env_float("DUPLA_SINGLE_FLIGHT_POLL_S", 1.0)
    ttl = lock_ttl_seconds()
    deadline = (max_wait_seconds if max_wait_seconds is not None else ttl) + 10

    async def _with_redis_lock() -> T:
        client = _try_get_redis()
        if client is None:
            # Redis unavailable — fall back to in-process coalesce only.
            return await compute_async()

        rkey = f"dupla:single_flight:{lock_key}"
        try:
            acquired = await asyncio.to_thread(client.set, rkey, "1", nx=True, ex=ttl)
        except Exception:
            logger.debug("[single_flight] redis SET failed for %s", rkey, exc_info=True)
            return await compute_async()

        if acquired:
            try:
                return await compute_async()
            finally:
                try:
                    await asyncio.to_thread(client.delete, rkey)
                except Exception:
                    logger.debug("[single_flight] redis DELETE failed for %s", rkey, exc_info=True)
        else:
            # Another worker computing. Poll the cache until value lands.
            waited = 0.0
            while waited < deadline:
                if cache_probe is not None:
                    hit = cache_probe()
                    if hit is not None:
                        logger.info("[single_flight] cross-proc wait hit on %s after %.1fs", lock_key, waited)
                        return hit  # type: ignore[return-value]
                # Also bail if the lock disappeared (winner errored, no cache write).
                try:
                    still_locked = await asyncio.to_thread(client.exists, rkey)
                except Exception:
                    still_locked = 1
                if not still_locked:
                    logger.info("[single_flight] lock released without cache write — racing on %s", lock_key)
                    return await compute_async()
                await asyncio.sleep(poll)
                waited += poll
            logger.warning("[single_flight] wait timeout on %s — computing anyway", lock_key)
            return await compute_async()

    return await _coalesce(lock_key, _with_redis_lock)


def _try_get_redis() -> Any | None:
    """Borrow the redis client already used by stage_cache (avoids two pools)."""
    try:
        from core.stage_cache import _get_redis  # type: ignore
    except Exception:
        return None
    return _get_redis()


# ---------------------------------------------------------------------------
# PDF rendering process pool (module-level singleton)
# ---------------------------------------------------------------------------

_PDF_POOL: ProcessPoolExecutor | None = None
_PDF_POOL_LOCK = threading.Lock()


def get_pdf_executor() -> ProcessPoolExecutor:
    """Lazy-init a process pool dedicated to PDF page rendering.

    Built once per worker process, reused across jobs, shut down at exit.
    Avoids the ~200-400ms fork/spawn cost per page render that a per-call
    pool would incur.
    """
    global _PDF_POOL
    if _PDF_POOL is not None:
        return _PDF_POOL
    with _PDF_POOL_LOCK:
        if _PDF_POOL is None:
            workers = pdf_render_workers()
            logger.info("[concurrency] starting PDF render pool (workers=%d)", workers)
            _PDF_POOL = ProcessPoolExecutor(max_workers=workers)
            atexit.register(_shutdown_pdf_executor)
    return _PDF_POOL


def _shutdown_pdf_executor() -> None:
    global _PDF_POOL
    if _PDF_POOL is None:
        return
    logger.info("[concurrency] shutting down PDF render pool")
    try:
        _PDF_POOL.shutdown(wait=True, cancel_futures=True)
    except Exception:
        logger.debug("[concurrency] PDF pool shutdown error", exc_info=True)
    _PDF_POOL = None


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def concurrency_summary() -> dict[str, Any]:
    return {
        "lock_ttl_seconds": lock_ttl_seconds(),
        "openai_vision_concurrency": vision_concurrency(),
        "openai_partida_concurrency": partida_concurrency(),
        "aps_concurrency": aps_concurrency(),
        "pdf_render_workers": pdf_render_workers(),
        "pdf_pool_started": _PDF_POOL is not None,
        "inflight_keys": len(_INFLIGHT),
    }
