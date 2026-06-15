"""APS: OAuth 2-legged, OSS (signed S3 upload), Model Derivative + manifest resumido para IA.

Flujo alineado con pipeline tipo extract_dwg_data: manifest primero, reutilización si success,
reintento de job tras failed (con grace polls), vistas configurables (p. ej. solo 2d), bucket
transient por defecto, reintento HTTP en 401 con token nuevo.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

APS_AUTH = "https://developer.api.autodesk.com/authentication/v2/token"
APS_OSS_BASE = "https://developer.api.autodesk.com/oss/v2"
APS_MD_BASE = "https://developer.api.autodesk.com/modelderivative/v2"

_OSS_DETAILS_POLL_INTERVAL_S = 1.0
_OSS_DETAILS_MAX_WAIT_S = 25.0
_PRE_TRANSLATE_SETTLE_S = 1.5


def _normalize_aps_region(raw: str) -> str:
    """Valores típicos OSS: US, EMEA, APAC (según cuenta APS)."""
    s = (raw or "").strip().upper()
    if s in ("", "USA"):
        return "US"
    if s == "EU":
        return "EMEA"
    return s or "US"


def _normalize_bucket_key(raw: str) -> str:
    s = "".join(c if (c.isalnum() or c == "-") else "-" for c in raw.strip().lower())
    s = s.strip("-")[:63]
    if len(s) < 3:
        return f"dupla-{s}"[:63]
    return s


def _urn_for_model_derivative(bucket_key: str, object_key: str) -> str:
    raw = f"urn:adsk.objects:os.object:{bucket_key}/{object_key}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _quote_object_key(object_key: str) -> str:
    return quote(object_key, safe="")


def _translation_views_list(settings: Settings) -> list[str]:
    raw = (settings.aps_translation_views or "2d").strip().lower()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    allowed = {"2d", "3d"}
    out = [p for p in parts if p in allowed]
    return out if out else ["2d"]


def _manifest_roles_sample(manifest: dict[str, Any]) -> set[str]:
    found: set[str] = set()

    def walk(node: Any, depth: int) -> None:
        if depth > 14:
            return
        if isinstance(node, dict):
            role = node.get("role")
            if isinstance(role, str) and role.strip():
                found.add(role.strip().lower())
            for ch in node.get("children") or []:
                walk(ch, depth + 1)
        elif isinstance(node, list):
            for ch in node[:80]:
                walk(ch, depth)

    for d in manifest.get("derivatives") or []:
        walk(d, 0)
    return found


def _manifest_covers_views(manifest: dict[str, Any], views: list[str]) -> bool:
    """Comprueba si el manifest ya incluye derivados para las vistas pedidas (2d / 3d)."""
    roles = _manifest_roles_sample(manifest)
    for v in views:
        vlow = v.lower()
        if vlow == "2d":
            if not any("2d" in r or r == "2d" or r.startswith("2d") for r in roles):
                if not any("sheet" in r for r in roles):
                    return False
        elif vlow == "3d":
            if not any("3d" in r or r == "3d" or r.startswith("3d") for r in roles):
                if not any("geometry" in r for r in roles):
                    return False
    return True


async def _aps_token(client: httpx.AsyncClient, settings: Settings) -> Optional[str]:
    cid = (settings.aps_client_id or "").strip()
    sec = (settings.aps_client_secret or "").strip()
    if not cid or not sec:
        return None
    scope = "data:read data:write bucket:read bucket:create code:all"
    try:
        r = await client.post(
            APS_AUTH,
            data={
                "client_id": cid,
                "client_secret": sec,
                "grant_type": "client_credentials",
                "scope": scope,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30.0,
        )
        if r.status_code != 200:
            logger.warning("APS token failed: %s %s", r.status_code, r.text[:500])
            return None
        data = r.json()
        tok = data.get("access_token")
        return tok if isinstance(tok, str) and tok else None
    except Exception as exc:
        logger.warning("APS token exception: %s", exc)
        return None


async def _aps_request(
    client: httpx.AsyncClient,
    settings: Settings,
    token_box: list[Optional[str]],
    method: str,
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    json_body: Any = None,
    params: Optional[dict[str, str]] = None,
    content: Optional[bytes] = None,
    timeout: float = 60.0,
) -> httpx.Response:
    """Un reintento en 401 tras renovar token (equivalente a _request_with_token_refresh)."""
    merged: dict[str, str] = dict(headers) if headers else {}
    for attempt in range(2):
        tok = token_box[0]
        if not tok:
            return httpx.Response(401, request=httpx.Request(method, url))
        merged["Authorization"] = f"Bearer {tok}"
        r = await client.request(
            method,
            url,
            headers=merged,
            json=json_body,
            params=params,
            content=content,
            timeout=timeout,
        )
        if r.status_code != 401 or attempt == 1:
            return r
        new_tok = await _aps_token(client, settings)
        if not new_tok:
            return r
        token_box[0] = new_tok
    return r


async def _ensure_bucket(
    client: httpx.AsyncClient,
    settings: Settings,
    token_box: list[Optional[str]],
    bucket_key: str,
) -> bool:
    url = f"{APS_OSS_BASE}/buckets/{quote(bucket_key, safe='')}/details"
    try:
        r = await _aps_request(client, settings, token_box, "GET", url, timeout=30.0)
        if r.status_code == 200:
            return True
        if r.status_code != 404:
            logger.warning("APS bucket details: %s %s", r.status_code, r.text[:300])
    except Exception as exc:
        logger.warning("APS bucket check: %s", exc)
        return False

    create_url = f"{APS_OSS_BASE}/buckets"
    policy = (settings.aps_bucket_policy or "transient").strip().lower()
    reg = _normalize_aps_region(settings.aps_region)
    body: dict[str, Any] = {"bucketKey": bucket_key, "policyKey": policy, "region": reg}
    try:
        r2 = await _aps_request(
            client,
            settings,
            token_box,
            "POST",
            create_url,
            headers={"Content-Type": "application/json"},
            json_body=body,
            timeout=30.0,
        )
        if r2.status_code in (200, 201, 409):
            return True
        logger.warning("APS bucket create: %s %s", r2.status_code, r2.text[:500])
    except Exception as exc:
        logger.warning("APS bucket create exception: %s", exc)
    return False


async def _oss_upload_file(
    client: httpx.AsyncClient,
    settings: Settings,
    token_box: list[Optional[str]],
    bucket_key: str,
    object_key: str,
    file_path: Path,
    mime: Optional[str],
) -> bool:
    """GET signed URLs → PUT bytes → POST complete."""
    enc_key = _quote_object_key(object_key)
    base = f"{APS_OSS_BASE}/buckets/{quote(bucket_key, safe='')}/objects/{enc_key}/signeds3upload"
    size = file_path.stat().st_size
    data_bytes = file_path.read_bytes()
    try:
        r = await _aps_request(
            client,
            settings,
            token_box,
            "GET",
            base,
            params={"firstPart": "1", "parts": "1", "minutesExpiration": "45"},
            timeout=60.0,
        )
        if r.status_code != 200:
            logger.warning("APS signeds3upload GET: %s %s", r.status_code, r.text[:400])
            return False
        j = r.json()
        upload_key = j.get("uploadKey")
        urls = j.get("urls")
        if not isinstance(upload_key, str) or not isinstance(urls, list) or not urls:
            logger.warning("APS signeds3upload GET unexpected: %s", j)
            return False
        put_url = urls[0]
        if not isinstance(put_url, str):
            return False
        headers_put = {"Content-Type": mime or "application/octet-stream"}
        r2 = await client.put(put_url, content=data_bytes, headers=headers_put, timeout=300.0)
        if r2.status_code not in (200, 201, 204):
            logger.warning("APS S3 PUT: %s %s", r2.status_code, r2.text[:300])
            return False
        complete_body: dict[str, Any] = {"uploadKey": upload_key, "size": size}
        r3 = await _aps_request(
            client,
            settings,
            token_box,
            "POST",
            base,
            headers={"Content-Type": "application/json"},
            json_body=complete_body,
            timeout=60.0,
        )
        if r3.status_code not in (200, 201):
            logger.warning("APS signeds3upload complete: %s %s", r3.status_code, r3.text[:400])
            return False
        return True
    except Exception as exc:
        logger.warning("APS OSS upload exception: %s", exc)
        return False


async def _oss_wait_object_readable(
    client: httpx.AsyncClient,
    settings: Settings,
    token_box: list[Optional[str]],
    bucket_key: str,
    object_key: str,
) -> bool:
    enc_key = _quote_object_key(object_key)
    url = f"{APS_OSS_BASE}/buckets/{quote(bucket_key, safe='')}/objects/{enc_key}/details"
    waited = 0.0
    while waited <= _OSS_DETAILS_MAX_WAIT_S:
        try:
            r = await _aps_request(client, settings, token_box, "GET", url, timeout=30.0)
            if r.status_code == 200:
                return True
            if r.status_code not in (404, 400):
                logger.warning("APS OSS object details: %s %s", r.status_code, r.text[:300])
        except Exception as exc:
            logger.warning("APS OSS object details poll: %s", exc)
        await asyncio.sleep(_OSS_DETAILS_POLL_INTERVAL_S)
        waited += _OSS_DETAILS_POLL_INTERVAL_S
    logger.warning(
        "APS OSS object not visible after %ss (bucket=%s key_prefix=%s…); translation may fail",
        int(_OSS_DETAILS_MAX_WAIT_S),
        bucket_key,
        object_key[:48],
    )
    return False


async def _fetch_manifest(
    client: httpx.AsyncClient,
    settings: Settings,
    token_box: list[Optional[str]],
    urn_b64: str,
) -> Optional[dict[str, Any]]:
    url = f"{APS_MD_BASE}/designdata/{quote(urn_b64, safe='')}/manifest"
    r = await _aps_request(client, settings, token_box, "GET", url, timeout=60.0)
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        logger.warning("APS manifest GET: %s %s", r.status_code, r.text[:400])
        return None
    data = r.json()
    return data if isinstance(data, dict) else None


def _manifest_status(manifest: Optional[dict[str, Any]]) -> str:
    if not manifest:
        return "missing"
    return (manifest.get("status") or "").strip().lower() or "missing"


async def _post_translate_job(
    client: httpx.AsyncClient,
    settings: Settings,
    token_box: list[Optional[str]],
    urn_b64: str,
    views: list[str],
) -> bool:
    url = f"{APS_MD_BASE}/designdata/job"
    body = {"input": {"urn": urn_b64}, "output": {"formats": [{"type": "svf2", "views": views}]}}
    try:
        r = await _aps_request(
            client,
            settings,
            token_box,
            "POST",
            url,
            headers={"Content-Type": "application/json", "x-ads-force": "true"},
            json_body=body,
            timeout=60.0,
        )
        if r.status_code not in (200, 201, 202):
            logger.warning("APS Model Derivative job: %s %s", r.status_code, r.text[:500])
            return False
        return True
    except Exception as exc:
        logger.warning("APS MD job exception: %s", exc)
        return False


def _manifest_failure_summary(data: dict[str, Any], max_len: int = 2400) -> str:
    out: dict[str, Any] = {
        "progress": data.get("progress"),
        "reason": data.get("reason"),
    }
    ders = data.get("derivatives")
    if isinstance(ders, list):
        slim: list[dict[str, Any]] = []
        for d in ders[:3]:
            if isinstance(d, dict):
                slim.append(
                    {
                        "name": d.get("name"),
                        "progress": d.get("progress"),
                        "messages": d.get("messages"),
                    }
                )
        out["derivatives"] = slim
    s = json.dumps(out, ensure_ascii=False, default=str)
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


async def _poll_manifest_until_success(
    client: httpx.AsyncClient,
    settings: Settings,
    token_box: list[Optional[str]],
    urn_b64: str,
) -> Optional[dict[str, Any]]:
    """
    Espera manifest success; ante failed aplica grace re-polls (manifest obsoleto).
    Devuelve None si timeout o failed definitivo.
    """
    interval = float(settings.aps_derivative_poll_interval_seconds)
    max_wait = float(settings.aps_derivative_max_wait_seconds)
    grace_polls = int(settings.aps_failed_manifest_grace_polls)
    grace_sleep = float(settings.aps_failed_manifest_grace_sleep_seconds)
    waited = 0.0

    while waited <= max_wait:
        try:
            data = await _fetch_manifest(client, settings, token_box, urn_b64)
            if data is None:
                await asyncio.sleep(interval)
                waited += interval
                continue
            status = (data.get("status") or "").lower()
            if status == "success":
                return data
            if status in ("pending", "inprogress"):
                await asyncio.sleep(interval)
                waited += interval
                continue
            if status in ("failed", "timeout"):
                logger.warning(
                    "APS manifest status=%s detail=%s",
                    status,
                    _manifest_failure_summary(data),
                )
                pending_after_grace = False
                for _ in range(max(0, grace_polls)):
                    await asyncio.sleep(grace_sleep)
                    waited += grace_sleep
                    if waited > max_wait:
                        return None
                    recovered = await _fetch_manifest(client, settings, token_box, urn_b64)
                    if recovered is None:
                        continue
                    st2 = (recovered.get("status") or "").lower()
                    if st2 == "success":
                        return recovered
                    if st2 in ("pending", "inprogress"):
                        pending_after_grace = True
                        break
                else:
                    return None
                if pending_after_grace:
                    await asyncio.sleep(interval)
                    waited += interval
                    continue
                return None
        except Exception as exc:
            logger.warning("APS manifest poll: %s", exc)
            await asyncio.sleep(interval)
            waited += interval
    logger.warning("APS manifest poll timeout after %ss", max_wait)
    return None


def build_manifest_summary(manifest: dict[str, Any], max_chars: int) -> str:
    """Recorta el manifest a señales útiles (nombres, roles, tipos) sin exceder max_chars."""

    def walk(node: Any, out: list[dict[str, str]], depth: int) -> None:
        if depth > 12 or len(out) > 400:
            return
        if isinstance(node, dict):
            name = node.get("name")
            role = node.get("role")
            typ = node.get("type")
            if isinstance(name, str) and name.strip():
                row: dict[str, str] = {"name": name[:200]}
                if isinstance(role, str):
                    row["role"] = role[:80]
                if isinstance(typ, str):
                    row["type"] = typ[:80]
                out.append(row)
            for ch in node.get("children") or []:
                walk(ch, out, depth + 1)
        elif isinstance(node, list):
            for ch in node[:50]:
                walk(ch, out, depth)

    roots: list[dict[str, str]] = []
    for d in manifest.get("derivatives") or []:
        walk(d, roots, 0)
    payload = {
        "manifest_version": manifest.get("version"),
        "progress": manifest.get("progress"),
        "nodes_sample": roots[:350],
    }
    s = json.dumps(payload, ensure_ascii=False)
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 3] + "..."


async def run_aps_derivative_context(
    settings: Settings,
    file_path: Path,
    bucket_key_raw: str,
    object_key: str,
    mime: Optional[str],
) -> str:
    """
    Sube a OSS, asegura traducción SVF2 para las vistas configuradas, devuelve JSON resumido
    o la cadena 'unavailable'. No lanza: el caller registra y sigue sin APS.
    """
    if not file_path.is_file():
        return "unavailable"
    bucket_key = _normalize_bucket_key(bucket_key_raw)
    views = _translation_views_list(settings)

    async with httpx.AsyncClient() as client:
        token0 = await _aps_token(client, settings)
        if not token0:
            return "unavailable"
        token_box: list[Optional[str]] = [token0]

        if not await _ensure_bucket(client, settings, token_box, bucket_key):
            return "unavailable"
        if not await _oss_upload_file(client, settings, token_box, bucket_key, object_key, file_path, mime):
            return "unavailable"
        if not await _oss_wait_object_readable(client, settings, token_box, bucket_key, object_key):
            return "unavailable"
        await asyncio.sleep(_PRE_TRANSLATE_SETTLE_S)

        urn_b64 = _urn_for_model_derivative(bucket_key, object_key)
        manifest = await _fetch_manifest(client, settings, token_box, urn_b64)
        st = _manifest_status(manifest)

        if st == "success" and manifest and _manifest_covers_views(manifest, views):
            logger.info("APS reusing existing manifest for urn (views satisfied)")
            return build_manifest_summary(manifest, settings.ga_fo_aps_context_max_chars)

        if st in ("pending", "inprogress"):
            logger.info("APS manifest in progress, waiting (no new job)")
            manifest = await _poll_manifest_until_success(client, settings, token_box, urn_b64)
            if manifest and _manifest_status(manifest) == "success":
                if _manifest_covers_views(manifest, views):
                    return build_manifest_summary(manifest, settings.ga_fo_aps_context_max_chars)
                logger.info("APS success after wait but views %s not satisfied, submitting job", views)
                if not await _post_translate_job(client, settings, token_box, urn_b64, views):
                    return "unavailable"
                manifest = await _poll_manifest_until_success(client, settings, token_box, urn_b64)
                if manifest and _manifest_status(manifest) == "success" and _manifest_covers_views(manifest, views):
                    return build_manifest_summary(manifest, settings.ga_fo_aps_context_max_chars)
            return "unavailable"

        if st in ("failed", "timeout") and manifest:
            for _ in range(max(0, int(settings.aps_failed_manifest_grace_polls))):
                await asyncio.sleep(float(settings.aps_failed_manifest_grace_sleep_seconds))
                manifest = await _fetch_manifest(client, settings, token_box, urn_b64)
                st = _manifest_status(manifest)
                if st == "success" and manifest:
                    if _manifest_covers_views(manifest, views):
                        return build_manifest_summary(manifest, settings.ga_fo_aps_context_max_chars)
                    break
                if st in ("pending", "inprogress"):
                    manifest = await _poll_manifest_until_success(client, settings, token_box, urn_b64)
                    if manifest and _manifest_status(manifest) == "success" and _manifest_covers_views(
                        manifest, views
                    ):
                        return build_manifest_summary(manifest, settings.ga_fo_aps_context_max_chars)
                    return "unavailable"
            logger.info("APS manifest still failed after grace, forcing new translation job")

        need_translation_job = (
            st == "missing"
            or st in ("failed", "timeout")
            or (bool(manifest) and st == "success" and not _manifest_covers_views(manifest, views))
        )
        if need_translation_job:
            logger.info("APS submitting translation job (manifest_status=%s views=%s)", st, views)
            if not await _post_translate_job(client, settings, token_box, urn_b64, views):
                return "unavailable"
            manifest = await _poll_manifest_until_success(client, settings, token_box, urn_b64)
            if manifest and _manifest_status(manifest) == "success" and _manifest_covers_views(manifest, views):
                return build_manifest_summary(manifest, settings.ga_fo_aps_context_max_chars)
            return "unavailable"

    return "unavailable"
