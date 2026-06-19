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


async def _check_aps() -> dict[str, Any]:
    settings = get_settings()
    client_id = getattr(settings, "aps_client_id", None) or ""
    client_secret = getattr(settings, "aps_client_secret", None) or ""
    if not client_id or not client_secret:
        return {"status": "not_configured", "detail": "APS_CLIENT_ID / APS_CLIENT_SECRET not set"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://developer.api.autodesk.com/authentication/v2/token",
                data={
                    "grant_type": "client_credentials",
                    "scope": "data:read",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code == 200:
            return {"status": "ok"}
        return {
            "status": "auth_failed",
            "detail": f"HTTP {resp.status_code}: {resp.text[:200]}",
        }
    except Exception as exc:
        return {"status": "unreachable", "detail": str(exc)}


@router.get("/integrations", summary="Check external integration health")
async def integrations_health() -> dict[str, Any]:
    """Returns the health of Redis, coordination service, and APS."""
    settings = get_settings()

    coordination_url: str = getattr(settings, "coordination_url", "http://coordination-service:8001")
    redis_url: str = getattr(settings, "redis_url", "redis://redis:6379/0")

    coord_status = await _check_coordination(coordination_url)
    redis_status = _check_redis(redis_url)
    aps_status = await _check_aps()

    all_ok = all(
        s["status"] == "ok"
        for s in (coord_status, redis_status, aps_status)
    )

    return {
        "overall": "ok" if all_ok else "degraded",
        "integrations": {
            "coordination_service": coord_status,
            "redis": redis_status,
            "aps": aps_status,
        },
    }
