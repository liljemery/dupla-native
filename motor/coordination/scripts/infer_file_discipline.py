#!/usr/bin/env python3
"""Infer file discipline from content; JSON stdout for backend subprocess."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aps_integration.aps_auth import get_aps_token
from aps_integration.model_derivative import extract_dwg_data
from aps_integration.oss_manager import upload_file_to_bucket

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coordination.extraction.aps_cache import (  # noqa: E402
    file_cache_key,
    load_cached_json,
    save_cached_json,
)
from coordination.selection.file_discipline_inference import (  # noqa: E402
    CONFIDENCE_THRESHOLD,
    infer_discipline_from_file,
    motor_discipline_to_bucket_value,
    vote_discipline_from_autodesk_raw,
)


def _classification_aps_timeout_seconds() -> int:
    raw = (os.getenv("APS_CLASSIFICATION_TIMEOUT_SECONDS") or "180").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 180


def _cache_root_from_env() -> Path | None:
    raw = (os.getenv("COORDINATION_CACHE_ROOT") or "").strip()
    return Path(raw) if raw else None


def _aps_token() -> str | dict[str, Any] | None:
    cid = (os.getenv("CLIENT_ID") or os.getenv("APS_CLIENT_ID") or "").strip()
    secret = (os.getenv("CLIENT_SECRET") or os.getenv("APS_CLIENT_SECRET") or "").strip()
    if not cid or not secret:
        return None
    try:
        return {"access_token": get_aps_token(), "refresh_count": 0}
    except Exception:
        return None


def _compact_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "urn": raw.get("urn"),
        "manifest_status": raw.get("manifest_status"),
        "manifest_progress": raw.get("manifest_progress"),
        "views_requested": raw.get("views_requested"),
        "object_count": sum(int(v.get("object_count") or 0) for v in raw.get("views") or []),
    }


def _first_viewable_guid(raw: dict[str, Any]) -> str | None:
    for view in raw.get("views") or []:
        guid = view.get("guid") or view.get("viewableGUID")
        if isinstance(guid, str) and guid.strip():
            return guid.strip()
    return None


def _maybe_extract_aps_raw(
    path: Path,
    *,
    bucket_name: str,
    object_key: str | None,
    cache_root: Path | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    diagnostics: dict[str, Any] = {"result": None, "aps_error": None}
    cache_key = file_cache_key(path)
    cached = load_cached_json(cache_root, key=cache_key, suffix="raw")
    if isinstance(cached, dict) and cached.get("views"):
        diagnostics["result"] = "raw_cache"
        return cached, diagnostics

    token = _aps_token()
    if token is None or not bucket_name.strip():
        diagnostics["aps_error"] = "aps_not_configured"
        return None, diagnostics

    suffix = hashlib.sha256(object_key.encode("utf-8") if object_key else str(path.resolve()).encode()).hexdigest()[:12]
    uploaded_key = object_key or upload_file_to_bucket(token, bucket_name, str(path), unique_suffix=suffix)
    if not uploaded_key:
        diagnostics["aps_error"] = "upload_failed"
        return None, diagnostics
    timeout = _classification_aps_timeout_seconds()
    try:
        raw = extract_dwg_data(
            token,
            bucket_name,
            uploaded_key,
            views=("2d",),
            translation_timeout_seconds=timeout,
            max_property_wait_seconds=min(timeout, 300),
        )
    except Exception as exc:
        diagnostics["aps_error"] = str(exc)
        return None, diagnostics

    save_cached_json(cache_root, key=cache_key, suffix="raw", payload=raw)
    diagnostics["result"] = "aps_extract"
    diagnostics["object_key"] = uploaded_key
    diagnostics["urn"] = raw.get("urn")
    return raw, diagnostics


def build_payload(
    path: Path,
    *,
    rel_posix: str | None,
    bucket_name: str,
    object_key: str | None,
    cache_root: Path | None,
) -> dict[str, Any]:
    path = path.resolve()
    cache_key = file_cache_key(path)
    aps_raw: dict[str, Any] | None = None
    aps_meta: dict[str, Any] = {}
    diagnostics: dict[str, Any] | None = None

    # ponytail: ezdxf/path_hint first; APS only when still inconclusive (upgrade: async APS backfill)
    result = infer_discipline_from_file(
        path,
        rel_posix=rel_posix,
        cache_root=cache_root,
        aps_raw=None,
    )
    need_aps = path.suffix.lower() in (".dwg", ".dxf") and (
        result.discipline is None or result.confidence < CONFIDENCE_THRESHOLD
    )
    if need_aps:
        aps_raw, diagnostics = _maybe_extract_aps_raw(
            path,
            bucket_name=bucket_name,
            object_key=object_key,
            cache_root=cache_root,
        )
        if diagnostics:
            save_cached_json(cache_root, key=cache_key, suffix="diagnostics", payload=diagnostics)
        if aps_raw is not None:
            result = infer_discipline_from_file(
                path,
                rel_posix=rel_posix,
                cache_root=cache_root,
                aps_raw=aps_raw,
            )
    bucket_value = motor_discipline_to_bucket_value(result.discipline)
    classified_at = datetime.now(timezone.utc).isoformat()

    snapshot: dict[str, Any] = {
        "classified_at": classified_at,
        "discipline_method": result.method,
        "confidence": result.confidence,
        "aps_cache_key": result.aps_cache_key or cache_key,
        "layer_histogram": result.layer_histogram or {},
        "dominant_layers": list(result.dominant_layers),
        "entities_sampled": result.entities_sampled,
        "geometry_quality": result.geometry_quality,
        "level_hint": result.level_hint,
        "pdf_text_snippet_chars": result.pdf_text_snippet_chars,
        "pdf_text_snippet_sha256": result.pdf_text_snippet_sha256,
        "extraction_diagnostics": result.extraction_diagnostics or diagnostics,
    }

    if aps_raw is not None:
        aps_meta = {
            "bucket_key": bucket_name,
            "object_key": diagnostics.get("object_key") or object_key,
            "object_id": f"urn:adsk.objects:os.object:{bucket_name}/{diagnostics.get('object_key') or object_key}",
            "urn": aps_raw.get("urn"),
            "derivative_status": aps_raw.get("manifest_status"),
            "viewable_guid": _first_viewable_guid(aps_raw),
            "manifest_json": _compact_manifest(aps_raw),
            "last_translated_at": classified_at,
        }

    return {
        "discipline": bucket_value,
        "motor_discipline": result.discipline.value if result.discipline else None,
        "method": result.method,
        "confidence": result.confidence,
        "snapshot": snapshot,
        "aps": aps_meta or None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Infer discipline from file content")
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--rel-posix", type=str, default=None)
    parser.add_argument("--cache-root", type=Path, default=None)
    parser.add_argument("--bucket", type=str, default=os.getenv("APS_BUCKET_NAME", ""))
    parser.add_argument("--object-key", type=str, default=None)
    args = parser.parse_args()

    if not args.path.is_file():
        print(json.dumps({"error": "file_not_found", "path": str(args.path)}))
        return 1

    cache_root = args.cache_root or _cache_root_from_env()
    payload = build_payload(
        args.path,
        rel_posix=args.rel_posix,
        bucket_name=args.bucket or "",
        object_key=args.object_key,
        cache_root=cache_root,
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
