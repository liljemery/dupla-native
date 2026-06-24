"""Integration health checks."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter
from redis import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


async def _check_coordination(url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/health")
        if resp.status_code == 200:
            return {"status": "ok", "detail": resp.json()}
        return {"status": "degraded", "detail": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"status": "unreachable", "detail": str(exc)}


def _check_redis(url: str) -> dict[str, Any]:
    try:
        r = Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
        r.ping()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "unreachable", "detail": str(exc)}


@router.get("/integrations", summary="Check external integration health")
async def integrations_health() -> dict[str, Any]:
    """Returns the health of Redis and the coordination service."""
    settings = get_settings()

    coordination_url: str = getattr(settings, "coordination_url", "http://coordination-service:8001")
    redis_url: str = getattr(settings, "redis_url", "redis://redis:6379/0")

    coord_status = await _check_coordination(coordination_url)
    redis_status = _check_redis(redis_url)

    all_ok = all(s["status"] == "ok" for s in (coord_status, redis_status))

    return {
        "overall": "ok" if all_ok else "degraded",
        "integrations": {
            "coordination_service": coord_status,
            "redis": redis_status,
        },
    }
