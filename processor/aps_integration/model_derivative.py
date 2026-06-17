"""
Model Derivative API helpers for DWG extraction via REST.

Flow:
    Upload DWG -> Translate to SVF2 -> Read metadata -> Read properties

Everything stays REST-based. No COM or local Autodesk automation is used.
"""

from __future__ import annotations

import asyncio
import base64
import os
import random
import time
from collections.abc import Iterable

import httpx
import requests
from dotenv import load_dotenv

from aps_integration.aps_auth import get_aps_token

load_dotenv()

BASE_URL = "https://developer.api.autodesk.com"
MD_URL = f"{BASE_URL}/modelderivative/v2/designdata"

DEFAULT_VIEWS = ("2d",)
DEFAULT_TRANSLATION_TIMEOUT_SECONDS = 3600
DEFAULT_POLL_INTERVAL_SECONDS = int(os.getenv("APS_POLL_INTERVAL_SECONDS", "3") or 3)
DEFAULT_MAX_PROPERTY_WAIT_SECONDS = 3600
DEFAULT_FAILED_MANIFEST_GRACE_POLLS = 3
DEFAULT_FAILED_MANIFEST_GRACE_SLEEP_SECONDS = 20
REQUEST_TIMEOUT_SECONDS = 60
APS_PROPERTY_CONCURRENCY = 30
APS_ASYNC_MAX_RETRIES = 4
APS_RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


def _get_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _coerce_token_state(token: str | dict[str, object]) -> dict[str, object]:
    if isinstance(token, dict):
        if "access_token" not in token:
            token["access_token"] = str(token.get("token") or "")
        token["refresh_count"] = int(token.get("refresh_count", 0))
        return token
    return {"access_token": token, "refresh_count": 0}


def _request_with_token_refresh(
    method: str,
    url: str,
    token: str | dict[str, object],
    *,
    headers: dict[str, str] | None = None,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
    **request_kwargs,
) -> requests.Response:
    token_state = _coerce_token_state(token)
    request_method = getattr(requests, method.lower())

    def do_request() -> requests.Response:
        resolved_headers = dict(headers or {})
        resolved_headers.update(_get_headers(str(token_state["access_token"])))
        # Retry transient connection / DNS failures (e.g. getaddrinfo / WinError
        # 10054 / 11001). Manifest polling runs for minutes on cold translations,
        # so a single DNS blip must not abort the whole extraction job.
        last_exc: Exception | None = None
        for attempt in range(1, APS_ASYNC_MAX_RETRIES + 1):
            try:
                return request_method(
                    url,
                    headers=resolved_headers,
                    timeout=timeout,
                    **request_kwargs,
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                last_exc = exc
                if attempt >= APS_ASYNC_MAX_RETRIES:
                    raise
                delay = min(20.0, (2 ** (attempt - 1)) + random.random())
                print(
                    f"[APS] {method.upper()} network error ({type(exc).__name__}); "
                    f"retry {attempt}/{APS_ASYNC_MAX_RETRIES} in {delay:.1f}s"
                )
                time.sleep(delay)
        raise last_exc  # pragma: no cover - loop always returns or raises

    response = do_request()
    if response.status_code != 401:
        return response

    print(
        f"[AUTH] APS token expired during {method.upper()} request. "
        "Refreshing token and retrying once."
    )
    token_state["access_token"] = get_aps_token()
    token_state["refresh_count"] = int(token_state.get("refresh_count", 0)) + 1
    retry_response = do_request()
    if retry_response.status_code == 401:
        print("[AUTH] Retry after token refresh still returned 401.")
    else:
        print(
            f"[AUTH] Retry after token refresh succeeded with status "
            f"{retry_response.status_code}."
        )
    return retry_response


async def _async_request_with_token_refresh(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    token: str | dict[str, object],
    *,
    headers: dict[str, str] | None = None,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
    refresh_lock: asyncio.Lock | None = None,
    **request_kwargs,
) -> httpx.Response:
    token_state = _coerce_token_state(token)

    async def do_request() -> httpx.Response:
        resolved_headers = dict(headers or {})
        resolved_headers.update(_get_headers(str(token_state["access_token"])))
        return await client.request(
            method.upper(),
            url,
            headers=resolved_headers,
            timeout=timeout,
            **request_kwargs,
        )

    response = await do_request()
    if response.status_code != 401:
        return response

    old_token = str(token_state["access_token"])
    print(
        f"[AUTH] APS token expired during async {method.upper()} request. "
        "Refreshing token and retrying once."
    )
    if refresh_lock is None:
        token_state["access_token"] = get_aps_token()
        token_state["refresh_count"] = int(token_state.get("refresh_count", 0)) + 1
    else:
        async with refresh_lock:
            if str(token_state["access_token"]) == old_token:
                token_state["access_token"] = get_aps_token()
                token_state["refresh_count"] = int(token_state.get("refresh_count", 0)) + 1

    retry_response = await do_request()
    if retry_response.status_code == 401:
        print("[AUTH] Async retry after token refresh still returned 401.")
    else:
        print(
            f"[AUTH] Async retry after token refresh succeeded with status "
            f"{retry_response.status_code}."
        )
    return retry_response


def _normalize_views(views: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    for view in views or DEFAULT_VIEWS:
        lowered = str(view).strip().lower()
        if lowered not in {"2d", "3d"}:
            raise ValueError(f"Invalid view '{view}'. Expected '2d' and/or '3d'.")
        if lowered not in normalized:
            normalized.append(lowered)
    return normalized or list(DEFAULT_VIEWS)


def _short_urn(urn: str) -> str:
    return urn if len(urn) <= 24 else f"{urn[:24]}..."


def _manifest_status_and_progress(manifest: dict | None) -> tuple[str, str]:
    if not manifest:
        return "missing", "0%"
    return (
        str(manifest.get("status") or "unknown").lower(),
        str(manifest.get("progress") or "0%"),
    )


def _iter_manifest_nodes(node: dict | list | None):
    if isinstance(node, dict):
        yield node
        for child in node.get("children", []) or []:
            yield from _iter_manifest_nodes(child)
        for child in node.get("derivatives", []) or []:
            yield from _iter_manifest_nodes(child)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_manifest_nodes(item)


def _manifest_roles(manifest: dict | None) -> set[str]:
    roles: set[str] = set()
    for node in _iter_manifest_nodes(manifest):
        role = node.get("role")
        if role:
            roles.add(str(role).lower())
    return roles


def _node_markers(node: dict | None) -> list[str]:
    if not isinstance(node, dict):
        return []
    markers: list[str] = []
    for key in ("role", "type", "mime", "name", "urn"):
        value = node.get(key)
        if value:
            markers.append(str(value).lower())
    return markers


def _is_property_database_node(node: dict | None) -> bool:
    markers = _node_markers(node)
    return any(
        "autodesk.cloudplatform.propertydatabase" in marker
        or "propertydatabase" in marker
        or "autodesk-db" in marker
        for marker in markers
    )


def inspect_manifest_derivatives(manifest: dict | None) -> dict[str, object]:
    status, progress = _manifest_status_and_progress(manifest)
    property_database_statuses: list[str] = []
    for node in _iter_manifest_nodes(manifest):
        if _is_property_database_node(node):
            property_database_statuses.append(
                str(node.get("status") or "unknown").lower()
            )

    return {
        "manifest_status": status,
        "manifest_progress": progress,
        "manifest_failed": status == "failed",
        "roles": sorted(_manifest_roles(manifest)),
        "property_database_exists": bool(property_database_statuses),
        "property_database_success": any(
            node_status == "success" for node_status in property_database_statuses
        ),
        "property_database_statuses": property_database_statuses,
    }


def _manifest_satisfies_views(manifest: dict | None, views: Iterable[str]) -> bool:
    requested = set(_normalize_views(views))
    if not requested:
        return False
    roles = _manifest_roles(manifest)
    return requested.issubset(roles)


def get_manifest(token: str | dict[str, object], urn: str) -> dict | None:
    url = f"{MD_URL}/{urn}/manifest"
    response = _request_with_token_refresh(
        "get",
        url,
        token,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def urn_from_object_id(bucket_key: str, object_name: str) -> str:
    """
    Generate the base64 URN from bucket + object name.
    """
    object_id = f"urn:adsk.objects:os.object:{bucket_key}/{object_name}"
    return base64.urlsafe_b64encode(object_id.encode()).decode().rstrip("=")


def translate_to_svf2(
    token: str | dict[str, object],
    urn: str,
    max_retries: int = 3,
    views: Iterable[str] = DEFAULT_VIEWS,
) -> dict:
    """
    Submit an SVF2 translation job for the requested views.

    By default the budgeting pipeline asks for 2D only because it is
    significantly cheaper than translating both 2D and 3D for large DWGs.
    """
    normalized_views = _normalize_views(views)
    print(
        f"\n[MODEL DERIVATIVE] Submitting translation job | "
        f"URN={_short_urn(urn)} | views={normalized_views}"
    )
    url = f"{MD_URL}/job"
    payload = {
        "input": {"urn": urn},
        "output": {
            "formats": [
                {
                    "type": "svf2",
                    "views": normalized_views,
                }
            ]
        },
    }

    last_response: requests.Response | None = None
    for attempt in range(1, max_retries + 1):
        response = _request_with_token_refresh(
            "post",
            url,
            token,
            json=payload,
        )
        last_response = response

        if response.status_code == 200:
            print("[OK] Translation job accepted; manifest may already exist.")
            return response.json()
        if response.status_code in {201, 202}:
            print("[OK] Translation job started.")
            return response.json()
        if response.status_code in {429} or response.status_code >= 500:
            wait_seconds = 10 * attempt
            print(
                f"[WARN] Autodesk returned {response.status_code} on translation attempt "
                f"{attempt}/{max_retries}. Retrying in {wait_seconds}s..."
            )
            time.sleep(wait_seconds)
            continue

        print(f"[ERROR] Translation request failed: {response.status_code}: {response.text}")
        response.raise_for_status()

    if last_response is not None:
        print(
            f"[ERROR] Translation failed after {max_retries} retries: "
            f"{last_response.status_code}: {last_response.text}"
        )
        last_response.raise_for_status()
    raise RuntimeError(
        f"Translation failed after {max_retries} retries for URN {_short_urn(urn)}."
    )


def wait_for_translation(
    token: str | dict[str, object],
    urn: str,
    timeout: int = DEFAULT_TRANSLATION_TIMEOUT_SECONDS,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    failed_manifest_grace_polls: int = 0,
    failed_manifest_grace_sleep_seconds: int = DEFAULT_FAILED_MANIFEST_GRACE_SLEEP_SECONDS,
) -> str:
    """
    Poll the manifest until translation succeeds, fails, or times out.

    Returns:
        'success', 'failed', or 'timeout'
    """
    print(
        f"[MODEL DERIVATIVE] Waiting for translation | "
        f"URN={_short_urn(urn)} | timeout={timeout}s | poll={poll_interval_seconds}s | "
        f"failed_manifest_grace_polls={failed_manifest_grace_polls}"
    )
    token_state = _coerce_token_state(token)
    start = time.monotonic()
    sleep_seconds = max(int(poll_interval_seconds), 1)
    grace_polls_remaining = max(int(failed_manifest_grace_polls), 0)
    grace_sleep_seconds = max(int(failed_manifest_grace_sleep_seconds), 1)

    while True:
        elapsed = int(time.monotonic() - start)
        manifest = get_manifest(token_state, urn)
        manifest_info = inspect_manifest_derivatives(manifest)
        status = str(manifest_info["manifest_status"])
        progress = str(manifest_info["manifest_progress"])
        print(
            f"   URN={_short_urn(urn)} | status={status} | progress={progress} | "
            f"property_database_success={manifest_info['property_database_success']} | "
            f"elapsed={elapsed}s | token_refreshes={token_state['refresh_count']}"
        )

        if status == "success":
            return "success"
        if status == "failed":
            if grace_polls_remaining > 0:
                print(
                    f"[WARN] Failed manifest seen for URN={_short_urn(urn)} but grace is active. "
                    f"Assuming Autodesk may still be surfacing a stale failed manifest. "
                    f"Remaining grace polls: {grace_polls_remaining}."
                )
                grace_polls_remaining -= 1
                remaining = max(timeout - elapsed, 1)
                time.sleep(min(grace_sleep_seconds, remaining))
                continue
            print(f"[ERROR] Translation failed for URN={_short_urn(urn)}: {manifest}")
            return "failed"
        if elapsed >= timeout:
            print(
                f"[ERROR] Translation timeout reached for URN={_short_urn(urn)} "
                f"after {elapsed}s."
            )
            return "timeout"

        remaining = max(timeout - elapsed, 1)
        time.sleep(min(sleep_seconds, remaining))
        sleep_seconds = min(max(int(poll_interval_seconds), 1), sleep_seconds + 2, 30)


def _filter_requested_views(views_payload: list[dict], normalized_views: list[str]) -> list[dict]:
    requested_view_set = set(normalized_views)
    filtered_views = [
        view
        for view in views_payload
        if str(view.get("role", "")).lower() in requested_view_set
    ]
    if filtered_views:
        print(
            f"[MODEL DERIVATIVE] Using {len(filtered_views)} filtered views "
            f"matching requested roles {normalized_views}."
        )
        return filtered_views

    print(
        "[WARN] No view role matched the requested set exactly. "
        "Proceeding with all available views."
    )
    return views_payload


async def get_all_properties_async(
    client: httpx.AsyncClient,
    token: str | dict[str, object],
    urn: str,
    guid: str,
    *,
    max_wait_seconds: int = DEFAULT_MAX_PROPERTY_WAIT_SECONDS,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    refresh_lock: asyncio.Lock | None = None,
) -> dict:
    print(
        f"\n[MODEL DERIVATIVE] Async fetching all properties | "
        f"URN={_short_urn(urn)} | guid={guid[:8]}... | "
        f"timeout={max_wait_seconds}s | poll={poll_interval_seconds}s"
    )
    url = f"{MD_URL}/{urn}/metadata/{guid}/properties"
    start = time.monotonic()
    sleep_seconds = max(int(poll_interval_seconds), 1)

    while True:
        elapsed = int(time.monotonic() - start)
        try:
            response = await _async_request_with_token_refresh(
                client,
                "get",
                url,
                token,
                refresh_lock=refresh_lock,
            )
        except httpx.HTTPError as exc:
            if elapsed >= max_wait_seconds:
                raise TimeoutError(
                    f"Timed out waiting for properties for URN={urn} guid={guid}; "
                    f"last network error: {exc}"
                ) from exc
            delay = min(sleep_seconds + random.random(), max(max_wait_seconds - elapsed, 1))
            print(
                f"   APS async network retry | URN={_short_urn(urn)} | "
                f"guid={guid[:8]}... | elapsed={elapsed}s | sleep={delay:.1f}s | error={exc}"
            )
            await asyncio.sleep(delay)
            sleep_seconds = min(max(int(poll_interval_seconds), 1), sleep_seconds + 2, 30)
            continue

        if response.status_code == 200:
            data = response.json()
            collection = data.get("data", {}).get("collection", [])
            print(
                f"[OK] Async extracted properties for {len(collection)} objects | "
                f"URN={_short_urn(urn)} | guid={guid[:8]}..."
            )
            return data

        if response.status_code in {202, 404} | APS_RETRYABLE_STATUS_CODES:
            print(
                f"   Properties still processing/retrying | URN={_short_urn(urn)} | "
                f"guid={guid[:8]}... | status={response.status_code} | elapsed={elapsed}s"
            )
            if elapsed >= max_wait_seconds:
                raise TimeoutError(
                    f"Timed out waiting for properties for URN={urn} guid={guid}. "
                    f"Last APS status={response.status_code}. "
                    "Property indexing may still be processing remotely in Autodesk."
                )
            retry_multiplier = 2 if response.status_code in APS_RETRYABLE_STATUS_CODES else 1
            remaining = max(max_wait_seconds - elapsed, 1)
            delay = min((sleep_seconds * retry_multiplier) + random.random(), remaining, 45)
            await asyncio.sleep(delay)
            sleep_seconds = min(max(int(poll_interval_seconds), 1), sleep_seconds + 2, 30)
            continue

        print(
            f"[ERROR] Async property request failed | URN={_short_urn(urn)} | "
            f"guid={guid[:8]}... | status={response.status_code}: {response.text}"
        )
        response.raise_for_status()


async def _extract_single_view_result_async(
    client: httpx.AsyncClient,
    token: str | dict[str, object],
    urn: str,
    view: dict,
    *,
    semaphore: asyncio.Semaphore,
    refresh_lock: asyncio.Lock,
    max_property_wait_seconds: int,
    poll_interval_seconds: int,
) -> dict:
    guid = view.get("guid", "")
    view_name = view.get("name", "Unknown")
    role = view.get("role", "")
    print(f"\n--- Async processing view: {view_name} ({role}) | guid={guid[:8]}... ---")
    async with semaphore:
        try:
            properties = await get_all_properties_async(
                client,
                token,
                urn,
                guid,
                max_wait_seconds=max_property_wait_seconds,
                poll_interval_seconds=poll_interval_seconds,
                refresh_lock=refresh_lock,
            )
            collection = properties.get("data", {}).get("collection", [])
            return {
                "name": view_name,
                "guid": guid,
                "role": role,
                "object_count": len(collection),
                "objects": collection,
            }
        except Exception as exc:
            print(f"[WARN] Failed async extracting view {view_name}: {exc}")
            return {
                "name": view_name,
                "guid": guid,
                "role": role,
                "error": str(exc),
            }


async def _extract_view_results_async(
    token: str | dict[str, object],
    urn: str,
    filtered_views: list[dict],
    *,
    max_property_wait_seconds: int,
    poll_interval_seconds: int,
) -> tuple[list[dict], int]:
    limits = httpx.Limits(
        max_connections=APS_PROPERTY_CONCURRENCY,
        max_keepalive_connections=APS_PROPERTY_CONCURRENCY,
    )
    timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
    semaphore = asyncio.Semaphore(APS_PROPERTY_CONCURRENCY)
    refresh_lock = asyncio.Lock()
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        tasks = [
            _extract_single_view_result_async(
                client,
                token,
                urn,
                view,
                semaphore=semaphore,
                refresh_lock=refresh_lock,
                max_property_wait_seconds=max_property_wait_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
            for view in filtered_views
        ]
        extracted_views = await asyncio.gather(*tasks)

    successful_view_count = sum(1 for view in extracted_views if "error" not in view)
    return list(extracted_views), successful_view_count


def _extract_view_results(
    token: str | dict[str, object],
    urn: str,
    views_payload: list[dict],
    normalized_views: list[str],
    *,
    max_property_wait_seconds: int,
    poll_interval_seconds: int,
) -> tuple[list[dict], int]:
    filtered_views = _filter_requested_views(views_payload, normalized_views)
    if not filtered_views:
        return [], 0
    print(
        f"[MODEL DERIVATIVE] Fetching properties concurrently | "
        f"views={len(filtered_views)} | concurrency={APS_PROPERTY_CONCURRENCY}"
    )
    return asyncio.run(
        _extract_view_results_async(
            token,
            urn,
            filtered_views,
            max_property_wait_seconds=max_property_wait_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
    )


def _build_failed_translation_message(
    *,
    urn: str,
    object_name: str,
    manifest_strategy: str,
    property_database_exists: bool,
    property_database_success: bool,
    salvage_attempted: bool,
    token_refresh_happened: bool,
) -> str:
    return (
        f"Translation failed for URN={urn}. "
        f"object_name={object_name}. "
        f"manifest_strategy={manifest_strategy}. "
        f"property_database_exists={property_database_exists}. "
        f"property_database_success={property_database_success}. "
        f"salvage_attempted={salvage_attempted}. "
        f"token_refresh_happened={token_refresh_happened}."
    )


def get_model_views(token: str | dict[str, object], urn: str) -> list[dict]:
    """
    Get model views (metadata). Each view includes the GUID needed to request
    properties.
    """
    print(f"\n[MODEL DERIVATIVE] Fetching model views | URN={_short_urn(urn)}")
    url = f"{MD_URL}/{urn}/metadata"
    response = _request_with_token_refresh(
        "get",
        url,
        token,
    )
    response.raise_for_status()
    data = response.json()

    views = data.get("data", {}).get("metadata", [])
    for view in views:
        print(
            f"   View: {view.get('name', '?')} | GUID: {view.get('guid', '?')} | "
            f"role: {view.get('role', '?')}"
        )
    return views


def get_model_tree(token: str | dict[str, object], urn: str, guid: str) -> dict:
    """
    Get the hierarchical object tree for a model view.
    """
    print(
        f"\n[MODEL DERIVATIVE] Fetching object tree | URN={_short_urn(urn)} | guid={guid[:8]}..."
    )
    url = f"{MD_URL}/{urn}/metadata/{guid}"
    for _ in range(30):
        response = _request_with_token_refresh(
            "get",
            url,
            token,
        )
        if response.status_code == 200:
            return response.json()
        if response.status_code == 202:
            print("   Object tree still processing, waiting...")
            time.sleep(3)
            continue
        response.raise_for_status()
    raise TimeoutError(
        f"Timeout fetching model tree for URN={_short_urn(urn)} guid={guid[:8]}..."
    )


def get_all_properties(
    token: str | dict[str, object],
    urn: str,
    guid: str,
    max_wait_seconds: int = DEFAULT_MAX_PROPERTY_WAIT_SECONDS,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict:
    """
    Fetch all properties for a model view.

    Property indexing can take a long time on large DWGs, so this waits based
    on elapsed time rather than a fragile fixed-attempt loop.
    """
    print(
        f"\n[MODEL DERIVATIVE] Fetching all properties | "
        f"URN={_short_urn(urn)} | guid={guid[:8]}... | "
        f"timeout={max_wait_seconds}s | poll={poll_interval_seconds}s"
    )
    url = f"{MD_URL}/{urn}/metadata/{guid}/properties"
    start = time.monotonic()
    sleep_seconds = max(int(poll_interval_seconds), 1)

    while True:
        elapsed = int(time.monotonic() - start)
        response = _request_with_token_refresh(
            "get",
            url,
            token,
        )

        if response.status_code == 200:
            data = response.json()
            collection = data.get("data", {}).get("collection", [])
            print(
                f"[OK] Extracted properties for {len(collection)} objects | "
                f"URN={_short_urn(urn)} | guid={guid[:8]}..."
            )
            return data

        if response.status_code in {202, 404}:
            print(
                f"   Properties still processing | URN={_short_urn(urn)} | "
                f"guid={guid[:8]}... | status={response.status_code} | elapsed={elapsed}s"
            )
            if elapsed >= max_wait_seconds:
                raise TimeoutError(
                    f"Timed out waiting for properties for URN={urn} guid={guid}. "
                    "Property indexing may still be processing remotely in Autodesk."
                )
            remaining = max(max_wait_seconds - elapsed, 1)
            time.sleep(min(sleep_seconds, remaining))
            sleep_seconds = min(max(int(poll_interval_seconds), 1), sleep_seconds + 2, 30)
            continue

        print(
            f"[ERROR] Property request failed | URN={_short_urn(urn)} | "
            f"guid={guid[:8]}... | status={response.status_code}: {response.text}"
        )
        response.raise_for_status()


def query_specific_properties(
    token: str | dict[str, object],
    urn: str,
    guid: str,
    object_ids: list[int],
) -> dict:
    """
    Query properties for a specific object ID list.
    """
    print(
        f"\n[MODEL DERIVATIVE] Querying properties for {len(object_ids)} objects | "
        f"URN={_short_urn(urn)} | guid={guid[:8]}..."
    )
    url = f"{MD_URL}/{urn}/metadata/{guid}/properties:query"
    payload = {
        "pagination": {"limit": len(object_ids)},
        "query": {"$in": ["objectid"] + object_ids},
    }
    response = _request_with_token_refresh(
        "post",
        url,
        token,
        json=payload,
    )
    response.raise_for_status()
    return response.json()


def extract_dwg_data(
    token: str | dict[str, object],
    bucket_key: str,
    object_name: str,
    *,
    views: Iterable[str] = DEFAULT_VIEWS,
    translation_timeout_seconds: int = DEFAULT_TRANSLATION_TIMEOUT_SECONDS,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    max_property_wait_seconds: int = DEFAULT_MAX_PROPERTY_WAIT_SECONDS,
    failed_manifest_grace_polls: int = DEFAULT_FAILED_MANIFEST_GRACE_POLLS,
    failed_manifest_grace_sleep_seconds: int = DEFAULT_FAILED_MANIFEST_GRACE_SLEEP_SECONDS,
) -> dict:
    """
    Full pipeline: translate a DWG and extract all available properties.

    The budgeting workflow defaults to 2D-only translation because large DWGs
    are much faster and cheaper to process that way.

    Token refresh flow:
        The token can be passed as a plain string or a mutable dict.
        When passed as a dict, any mid-run refresh is visible to the caller::

            token_state = {"access_token": get_aps_token(), "refresh_count": 0}
            result = extract_dwg_data(token_state, bucket_key, object_name)
            # If the token expired mid-run, token_state["access_token"] now
            # holds the refreshed token and result["token_refresh_count"] > 0.
    """
    token_state = _coerce_token_state(token)
    normalized_views = _normalize_views(views)
    urn = urn_from_object_id(bucket_key, object_name)
    print(f"\n{'=' * 60}")
    print("MODEL DERIVATIVE EXTRACTION")
    print(f"Bucket: {bucket_key}")
    print(f"Object: {object_name}")
    print(f"URN: {_short_urn(urn)}")
    print(f"Views: {normalized_views}")
    print(f"Translation timeout: {translation_timeout_seconds}s")
    print(f"Property timeout: {max_property_wait_seconds}s")
    print(f"Failed-manifest grace polls: {failed_manifest_grace_polls}")
    print(f"Failed-manifest grace sleep: {failed_manifest_grace_sleep_seconds}s")
    print(f"{'=' * 60}")

    manifest = get_manifest(token_state, urn)
    manifest_info = inspect_manifest_derivatives(manifest)
    manifest_status = str(manifest_info["manifest_status"])
    manifest_progress = str(manifest_info["manifest_progress"])
    manifest_reused = False
    should_submit_translation = True
    translation_submitted = False
    resubmitted_after_failed_manifest = False
    manifest_strategy = "fresh_submission"

    if manifest is None:
        print(f"[MODEL DERIVATIVE] No existing manifest found | URN={_short_urn(urn)}")
    else:
        print(
            f"[MODEL DERIVATIVE] Existing manifest found | URN={_short_urn(urn)} | "
            f"status={manifest_status} | progress={manifest_progress} | "
            f"roles={manifest_info['roles']} | "
            f"property_database_exists={manifest_info['property_database_exists']} | "
            f"property_database_success={manifest_info['property_database_success']}"
        )
        if manifest_status == "success" and _manifest_satisfies_views(manifest, normalized_views):
            manifest_reused = True
            should_submit_translation = False
            manifest_strategy = "reused_success_manifest"
            print("[MODEL DERIVATIVE] Reusing successful manifest for requested views.")
        elif manifest_status in {"inprogress", "pending"}:
            manifest_reused = True
            should_submit_translation = False
            manifest_strategy = "reused_in_progress_manifest"
            print("[MODEL DERIVATIVE] Reusing in-progress manifest and continuing to poll.")
        elif manifest_status == "success":
            manifest_strategy = "resubmitted_for_view_mismatch"
            print(
                "[MODEL DERIVATIVE] Existing manifest does not clearly cover the requested views. "
                "Submitting a new translation job."
            )
        elif manifest_status == "failed":
            manifest_strategy = "resubmitted_after_failed_manifest"
            resubmitted_after_failed_manifest = True
            print("[MODEL DERIVATIVE] Existing manifest failed previously. Resubmitting translation.")

    if should_submit_translation:
        translate_to_svf2(token_state, urn, views=normalized_views)
        translation_submitted = True

    status = manifest_status
    if not (
        manifest_reused
        and manifest_status == "success"
        and _manifest_satisfies_views(manifest, normalized_views)
    ):
        status = wait_for_translation(
            token_state,
            urn,
            timeout=translation_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            failed_manifest_grace_polls=(
                failed_manifest_grace_polls if resubmitted_after_failed_manifest else 0
            ),
            failed_manifest_grace_sleep_seconds=failed_manifest_grace_sleep_seconds,
        )
        if status == "timeout":
            raise TimeoutError(
                f"Translation did not finish within {translation_timeout_seconds}s for URN={urn}. "
                f"manifest_strategy={manifest_strategy}. "
                "Autodesk may still be processing the file remotely. Re-run later to reuse the same manifest."
            )

    latest_manifest = get_manifest(token_state, urn)
    latest_manifest_info = inspect_manifest_derivatives(latest_manifest)
    print(
        f"[MODEL DERIVATIVE] Final manifest snapshot | URN={_short_urn(urn)} | "
        f"status={latest_manifest_info['manifest_status']} | "
        f"progress={latest_manifest_info['manifest_progress']} | "
        f"property_database_exists={latest_manifest_info['property_database_exists']} | "
        f"property_database_success={latest_manifest_info['property_database_success']}"
    )

    salvage_attempted = False
    salvage_succeeded = False
    views_results: list[dict] | None = None
    successful_view_count = 0

    if status != "success" and bool(latest_manifest_info["property_database_success"]):
        salvage_attempted = True
        print(
            f"[WARN] Manifest is not successful but PropertyDatabase is ready | "
            f"URN={_short_urn(urn)}. Attempting metadata/property salvage."
        )
        try:
            views_payload = get_model_views(token_state, urn)
            if views_payload:
                views_results, successful_view_count = _extract_view_results(
                    token_state,
                    urn,
                    views_payload,
                    normalized_views,
                    max_property_wait_seconds=max_property_wait_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                )
                salvage_succeeded = successful_view_count > 0
        except Exception as exc:
            print(f"[WARN] Salvage attempt failed for URN={_short_urn(urn)}: {exc}")

    if status != "success" and not salvage_succeeded:
        raise RuntimeError(
            _build_failed_translation_message(
                urn=urn,
                object_name=object_name,
                manifest_strategy=manifest_strategy,
                property_database_exists=bool(
                    latest_manifest_info["property_database_exists"]
                ),
                property_database_success=bool(
                    latest_manifest_info["property_database_success"]
                ),
                salvage_attempted=salvage_attempted,
                token_refresh_happened=int(token_state["refresh_count"]) > 0,
            )
        )

    if views_results is None:
        views_payload = get_model_views(token_state, urn)
        if not views_payload:
            raise RuntimeError(f"No views were found for translated model URN={urn}.")
        views_results, successful_view_count = _extract_view_results(
            token_state,
            urn,
            views_payload,
            normalized_views,
            max_property_wait_seconds=max_property_wait_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

    all_results = {
        "urn": urn,
        "object_name": object_name,
        "views_requested": normalized_views,
        "manifest_reused": manifest_reused,
        "manifest_strategy": manifest_strategy,
        "translation_submitted": translation_submitted,
        "resubmitted_after_failed_manifest": resubmitted_after_failed_manifest,
        "manifest_status": str(latest_manifest_info["manifest_status"]),
        "manifest_progress": str(latest_manifest_info["manifest_progress"]),
        "property_database_exists": bool(latest_manifest_info["property_database_exists"]),
        "property_database_success": bool(
            latest_manifest_info["property_database_success"]
        ),
        "token_refresh_count": int(token_state["refresh_count"]),
        "salvage_attempted": salvage_attempted,
        "salvage_succeeded": salvage_succeeded,
        "views": views_results,
    }

    total_objects = sum(view.get("object_count", 0) for view in all_results["views"])
    print(f"\n{'=' * 60}")
    print(
        f"MODEL DERIVATIVE EXTRACTION COMPLETE | "
        f"URN={_short_urn(urn)} | objects={total_objects} | views={len(all_results['views'])} | "
        f"successful_views={successful_view_count} | salvage_attempted={salvage_attempted}"
    )
    print(f"{'=' * 60}")
    return all_results
