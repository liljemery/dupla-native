"""
Model Derivative API helpers for DWG extraction via REST.

Flow:
    Upload DWG -> Translate to SVF2 -> Read metadata -> Read properties

Everything stays REST-based. No COM or local Autodesk automation is used.
"""

from __future__ import annotations

import base64
import os
import random
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

import requests
from dotenv import load_dotenv

from aps_integration.aps_auth import get_aps_token

load_dotenv()

BASE_URL = "https://developer.api.autodesk.com"
MD_URL = f"{BASE_URL}/modelderivative/v2/designdata"

DEFAULT_VIEWS = ("2d",)
DEFAULT_TRANSLATION_TIMEOUT_SECONDS = 3600
DEFAULT_POLL_INTERVAL_SECONDS = 10
DEFAULT_MAX_PROPERTY_WAIT_SECONDS = 3600
DEFAULT_FAILED_MANIFEST_GRACE_POLLS = 3
DEFAULT_FAILED_MANIFEST_GRACE_SLEEP_SECONDS = 20
REQUEST_TIMEOUT_SECONDS = 60
DEFAULT_SHALLOW_PROPERTY_THRESHOLD = 20
DEFAULT_PROPERTY_QUERY_BATCH_SIZE = 100


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


# Concurrencia intra-archivo: cuántas vistas se extraen en paralelo por DWG.
APS_VIEW_WORKERS = _env_int("APS_VIEW_WORKERS", 5)
# Tope global de llamadas simultáneas a metadata/propiedades (varios DWG x varias vistas).
APS_METADATA_CONCURRENCY = _env_int("APS_METADATA_CONCURRENCY", 8)
# Presupuesto de objetos-con-área tras el cual se deja de pedir más vistas (modo agresivo).
APS_VIEW_OBJECT_BUDGET = _env_int("APS_VIEW_OBJECT_BUDGET", 1600)
# Mínimo de vistas a procesar siempre, aunque el presupuesto ya esté cubierto.
APS_MIN_VIEWS = _env_int("APS_MIN_VIEWS", 3)
# Polling de propiedades arranca más corto que el de traducción.
DEFAULT_PROPERTY_POLL_START_SECONDS = _env_int("APS_PROPERTY_POLL_START_SECONDS", 4)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_HTTP_RETRIES = _env_int("APS_HTTP_MAX_RETRIES", 5)

# Limita el total de peticiones HTTP concurrentes contra APS para no gatillar 429.
_METADATA_SEMAPHORE = threading.BoundedSemaphore(APS_METADATA_CONCURRENCY)
# Evita que varios hilos refresquen el token a la vez.
_TOKEN_REFRESH_LOCK = threading.Lock()


class ApsCapacityError(RuntimeError):
    """Raised when APS denies a rated API (Model Derivative) due to account quota.

    This is an account/billing condition (HTTP 403 'ProductAccessRequiresCapacity'),
    NOT a corrupt file or a code defect. Callers should fall back to local/PDF
    extraction and surface a clear, actionable message instead of mislabeling the
    DWG as invalid.
    """


def is_capacity_denied(status_code: int, body: str) -> bool:
    text = (body or "").lower()
    return status_code == 403 and (
        "productaccessrequirescapacity" in text
        or "token exchange denied" in text
        or "token exchange access denied" in text
    )


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


def _refresh_token(token_state: dict[str, object]) -> None:
    """Refresca el token bajo lock para que hilos concurrentes no lo dupliquen."""
    current = str(token_state["access_token"])
    with _TOKEN_REFRESH_LOCK:
        # Otro hilo pudo refrescar mientras esperábamos el lock.
        if str(token_state["access_token"]) != current:
            return
        token_state["access_token"] = get_aps_token()
        token_state["refresh_count"] = int(token_state.get("refresh_count", 0)) + 1


def _request_with_token_refresh(
    method: str,
    url: str,
    token: str | dict[str, object],
    *,
    headers: dict[str, str] | None = None,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
    max_retries: int = _MAX_HTTP_RETRIES,
    **request_kwargs,
) -> requests.Response:
    token_state = _coerce_token_state(token)
    request_method = getattr(requests, method.lower())

    def do_request() -> requests.Response:
        resolved_headers = dict(headers or {})
        resolved_headers.update(_get_headers(str(token_state["access_token"])))
        # El semáforo acota cuántas peticiones golpean APS a la vez (anti-429).
        with _METADATA_SEMAPHORE:
            return request_method(
                url,
                headers=resolved_headers,
                timeout=timeout,
                **request_kwargs,
            )

    refreshed = False
    response = do_request()
    for attempt in range(1, max_retries + 1):
        status = response.status_code

        if status == 401 and not refreshed:
            print(
                f"[AUTH] APS token expired during {method.upper()} request. "
                "Refreshing token and retrying once."
            )
            _refresh_token(token_state)
            refreshed = True
            response = do_request()
            continue

        if status in _RETRYABLE_STATUS and attempt < max_retries:
            # Respeta Retry-After si APS lo envía; si no, backoff exponencial con jitter.
            retry_after = response.headers.get("Retry-After")
            if retry_after and str(retry_after).strip().isdigit():
                wait_seconds = float(retry_after)
            else:
                wait_seconds = min(2 ** attempt, 30) + random.uniform(0, 1.5)
            print(
                f"[WARN] APS {method.upper()} {status} (intento {attempt}/{max_retries}). "
                f"Reintentando en {wait_seconds:.1f}s..."
            )
            time.sleep(wait_seconds)
            response = do_request()
            continue

        break

    return response


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


def translate_to_svf1(
    token: str | dict[str, object],
    urn: str,
    *,
    max_retries: int = 3,
    views: Iterable[str] = DEFAULT_VIEWS,
) -> dict:
    """Submit SVF v1 translation (necesario para volcado de geometría 2D real vía Viewer)."""
    normalized_views = _normalize_views(views)
    print(
        f"\n[MODEL DERIVATIVE] Submitting SVF1 translation | "
        f"URN={_short_urn(urn)} | views={normalized_views}"
    )
    url = f"{MD_URL}/job"
    payload = {
        "input": {"urn": urn},
        "output": {"formats": [{"type": "svf", "views": normalized_views}]},
    }
    last_response: requests.Response | None = None
    for attempt in range(1, max_retries + 1):
        response = _request_with_token_refresh("post", url, token, json=payload)
        last_response = response
        if response.status_code in {200, 201, 202}:
            print("[OK] SVF1 translation job accepted.")
            return response.json()
        if is_capacity_denied(response.status_code, response.text):
            raise ApsCapacityError(
                f"APS capacity denied for SVF1 translation URN={_short_urn(urn)}: {response.text[:500]}"
            )
        if attempt < max_retries:
            time.sleep(min(2**attempt, 30))
    raise RuntimeError(
        f"SVF1 translation failed for URN={_short_urn(urn)}: "
        f"{last_response.status_code if last_response else 'no response'} "
        f"{last_response.text[:300] if last_response else ''}"
    )


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
        if is_capacity_denied(response.status_code, response.text):
            raise ApsCapacityError(
                "APS Model Derivative denegado por cuota de cuenta "
                "(403 ProductAccessRequiresCapacity). El plan Free agotó su cupo "
                "mensual de traducción o requiere Flex tokens. "
                "Revisa https://manage.autodesk.com/feature-usage/. "
                f"Respuesta: {response.text[:200]}"
            )
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


def flatten_model_tree(tree_payload: dict | list | None) -> list[int]:
    """Collect all object IDs from an APS model tree (recursive)."""
    object_ids: list[int] = []
    seen: set[int] = set()

    def walk(node: dict | list | None) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        for key in ("objectid", "objectId"):
            raw_id = node.get(key)
            if raw_id is not None:
                try:
                    oid = int(raw_id)
                except (TypeError, ValueError):
                    oid = None
                if oid is not None and oid not in seen:
                    seen.add(oid)
                    object_ids.append(oid)
        for child in node.get("objects") or []:
            walk(child)
        for child in node.get("children") or []:
            walk(child)

    if isinstance(tree_payload, dict):
        data = tree_payload.get("data") or tree_payload
        if isinstance(data, dict):
            collection = data.get("collection") or data.get("objects")
            if collection is not None:
                walk(collection)
            else:
                walk(data)
        else:
            walk(data)
    else:
        walk(tree_payload)
    return object_ids


def _count_objects_with_area(objects: list[dict]) -> int:
    count = 0
    for obj in objects:
        props = obj.get("properties")
        if not isinstance(props, dict):
            continue
        geo = props.get("Geometry") or {}
        area = geo.get("Area")
        if area is not None and str(area).strip() not in {"", "0", "0.0"}:
            count += 1
    return count


def _merge_property_collections(collections: list[list[dict]]) -> list[dict]:
    merged: dict[int, dict] = {}
    for collection in collections:
        for obj in collection:
            raw_id = obj.get("objectid")
            if raw_id is None:
                continue
            try:
                oid = int(raw_id)
            except (TypeError, ValueError):
                continue
            merged[oid] = obj
    return list(merged.values())


def _fetch_properties_for_view(
    token: str | dict[str, object],
    urn: str,
    guid: str,
    *,
    max_property_wait_seconds: int,
    poll_interval_seconds: int,
    shallow_threshold: int = DEFAULT_SHALLOW_PROPERTY_THRESHOLD,
    query_batch_size: int = DEFAULT_PROPERTY_QUERY_BATCH_SIZE,
) -> tuple[list[dict], dict[str, int]]:
    """Fetch properties for a view, deep-walking the object tree when shallow."""
    properties = get_all_properties(
        token,
        urn,
        guid,
        max_wait_seconds=max_property_wait_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    collection = properties.get("data", {}).get("collection", [])
    diagnostics: dict[str, int] = {
        "shallow_object_count": len(collection),
        "tree_object_count": 0,
        "properties_fetched": len(collection),
        "objects_with_area": _count_objects_with_area(collection),
        "deep_fetch_used": 0,
    }

    if len(collection) >= shallow_threshold:
        return collection, diagnostics

    try:
        tree_payload = get_model_tree(token, urn, guid)
        tree_ids = flatten_model_tree(tree_payload)
        diagnostics["tree_object_count"] = len(tree_ids)
        if not tree_ids:
            return collection, diagnostics

        missing_ids = [
            oid
            for oid in tree_ids
            if oid not in {int(o.get("objectid")) for o in collection if o.get("objectid") is not None}
        ]
        if not missing_ids and collection:
            return collection, diagnostics

        ids_to_query = missing_ids or tree_ids
        batch_size = max(int(query_batch_size), 1)
        deep_collections: list[list[dict]] = [collection] if collection else []
        for start in range(0, len(ids_to_query), batch_size):
            batch = ids_to_query[start : start + batch_size]
            try:
                batch_result = query_specific_properties(token, urn, guid, batch)
                batch_collection = batch_result.get("data", {}).get("collection", [])
                if batch_collection:
                    deep_collections.append(batch_collection)
            except Exception as exc:
                print(
                    f"[WARN] Property batch query failed | guid={guid[:8]}... | "
                    f"batch={start // batch_size + 1} | {exc}"
                )

        if deep_collections:
            merged = _merge_property_collections(deep_collections)
            diagnostics["deep_fetch_used"] = 1
            diagnostics["properties_fetched"] = len(merged)
            diagnostics["objects_with_area"] = _count_objects_with_area(merged)
            print(
                f"[MODEL DERIVATIVE] Deep property fetch | guid={guid[:8]}... | "
                f"tree={diagnostics['tree_object_count']} | fetched={diagnostics['properties_fetched']} | "
                f"with_area={diagnostics['objects_with_area']}"
            )
            return merged, diagnostics
    except Exception as exc:
        print(f"[WARN] Deep property fetch failed for guid={guid[:8]}...: {exc}")

    return collection, diagnostics


def _extract_view_results(
    token: str | dict[str, object],
    urn: str,
    views_payload: list[dict],
    normalized_views: list[str],
    *,
    max_property_wait_seconds: int,
    poll_interval_seconds: int,
    shallow_threshold: int = DEFAULT_SHALLOW_PROPERTY_THRESHOLD,
    query_batch_size: int = DEFAULT_PROPERTY_QUERY_BATCH_SIZE,
    view_workers: int = APS_VIEW_WORKERS,
    object_budget: int = APS_VIEW_OBJECT_BUDGET,
    min_views: int = APS_MIN_VIEWS,
    property_poll_start_seconds: int = DEFAULT_PROPERTY_POLL_START_SECONDS,
) -> tuple[list[dict], int]:
    """Extrae propiedades por vista en paralelo, preservando el orden original.

    Las vistas se procesan en oleadas (chunks) del tamaño de `view_workers`, en el
    mismo orden en que llegan de APS. Tras cada oleada se acumula `objects_with_area`;
    si ya se cubrió `object_budget` (y se procesó un mínimo de vistas) se omiten las
    vistas restantes. Esto es seguro porque el consumidor proxy corta en `max_entities`
    recorriendo las vistas en orden, así que las vistas tardías no aportarían elementos.
    """
    extracted_views: list[dict] = []
    successful_view_count = 0
    accumulated_area = 0
    filtered_views = _filter_requested_views(views_payload, normalized_views)
    if not filtered_views:
        return extracted_views, successful_view_count

    workers = max(1, min(int(view_workers), len(filtered_views)))

    def _process(view: dict) -> tuple[dict, bool, int]:
        guid = view.get("guid", "")
        view_name = view.get("name", "Unknown")
        role = view.get("role", "")
        print(f"\n--- Processing view: {view_name} ({role}) | guid={guid[:8]}... ---")
        try:
            collection, diagnostics = _fetch_properties_for_view(
                token,
                urn,
                guid,
                max_property_wait_seconds=max_property_wait_seconds,
                poll_interval_seconds=property_poll_start_seconds,
                shallow_threshold=shallow_threshold,
                query_batch_size=query_batch_size,
            )
            entry = {
                "name": view_name,
                "guid": guid,
                "role": role,
                "object_count": len(collection),
                "objects": collection,
                **diagnostics,
            }
            return entry, True, int(diagnostics.get("objects_with_area", 0) or 0)
        except Exception as exc:
            print(f"[WARN] Failed extracting view {view_name}: {exc}")
            return ({"name": view_name, "guid": guid, "role": role, "error": str(exc)}, False, 0)

    for start in range(0, len(filtered_views), workers):
        chunk = filtered_views[start : start + workers]
        if workers == 1:
            chunk_results = [_process(chunk[0])]
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                chunk_results = list(executor.map(_process, chunk))

        for entry, succeeded, area in chunk_results:
            extracted_views.append(entry)
            if succeeded:
                successful_view_count += 1
                accumulated_area += area

        if len(extracted_views) >= min_views and accumulated_area >= object_budget:
            remaining = len(filtered_views) - len(extracted_views)
            if remaining > 0:
                print(
                    f"[MODEL DERIVATIVE] Presupuesto de vistas cubierto: "
                    f"{accumulated_area} objetos-con-area en {len(extracted_views)} vistas "
                    f"(budget={object_budget}). Se omiten {remaining} vistas restantes."
                )
            break

    return extracted_views, successful_view_count


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


def _views_from_manifest_resources(manifest: dict | None) -> list[dict]:
    """Build pseudo-view entries from manifest resource nodes when /metadata is empty."""
    if not manifest:
        return []
    views: list[dict] = []
    seen: set[str] = set()
    for node in _iter_manifest_nodes(manifest):
        guid = node.get("guid")
        if not guid or guid in seen:
            continue
        role = str(node.get("role") or "").lower()
        name = str(node.get("name") or node.get("type") or "manifest-view")
        if "2d" in role or "3d" in role or "graphics" in role or "view" in role:
            seen.add(str(guid))
            views.append({"guid": guid, "name": name, "role": role})
    return views


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
    if not views:
        manifest = get_manifest(token, urn)
        views = _views_from_manifest_resources(manifest)
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
    view_workers: int = APS_VIEW_WORKERS,
    object_budget: int = APS_VIEW_OBJECT_BUDGET,
    min_views: int = APS_MIN_VIEWS,
    property_poll_start_seconds: int = DEFAULT_PROPERTY_POLL_START_SECONDS,
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
                    view_workers=view_workers,
                    object_budget=object_budget,
                    min_views=min_views,
                    property_poll_start_seconds=property_poll_start_seconds,
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
            view_workers=view_workers,
            object_budget=object_budget,
            min_views=min_views,
            property_poll_start_seconds=property_poll_start_seconds,
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
