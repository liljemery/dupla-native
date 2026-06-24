#!/usr/bin/env python3
"""Infer file discipline from content; JSON stdout for backend subprocess."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coordination.extraction.cad_cache import file_cache_key, save_cached_json
from coordination.selection.file_discipline_inference import (
    infer_discipline_from_file,
    motor_discipline_to_bucket_value,
)


def _cache_root_from_env() -> Path | None:
    raw = (os.getenv("COORDINATION_CACHE_ROOT") or "").strip()
    return Path(raw) if raw else None


def build_payload(
    path: Path,
    *,
    rel_posix: str | None,
    cache_root: Path | None,
) -> dict[str, Any]:
    path = path.resolve()
    cache_key = file_cache_key(path)
    result = infer_discipline_from_file(
        path,
        rel_posix=rel_posix,
        cache_root=cache_root,
    )
    bucket_value = motor_discipline_to_bucket_value(result.discipline)
    classified_at = datetime.now(timezone.utc).isoformat()

    snapshot: dict[str, Any] = {
        "classified_at": classified_at,
        "discipline_method": result.method,
        "confidence": result.confidence,
        "cad_cache_key": result.cad_cache_key or cache_key,
        "layer_histogram": result.layer_histogram or {},
        "dominant_layers": list(result.dominant_layers),
        "entities_sampled": result.entities_sampled,
        "geometry_quality": result.geometry_quality,
        "level_hint": result.level_hint,
        "pdf_text_snippet_chars": result.pdf_text_snippet_chars,
        "pdf_text_snippet_sha256": result.pdf_text_snippet_sha256,
        "extraction_diagnostics": result.extraction_diagnostics or {},
    }

    return {
        "discipline": bucket_value,
        "motor_discipline": result.discipline.value if result.discipline else None,
        "method": result.method,
        "confidence": result.confidence,
        "snapshot": snapshot,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Infer discipline from file content")
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--rel-posix", type=str, default=None)
    parser.add_argument("--cache-root", type=Path, default=None)
    parser.add_argument("--bucket", type=str, default=None)
    parser.add_argument("--object-key", type=str, default=None)
    args = parser.parse_args()

    if not args.path.is_file():
        print(json.dumps({"error": "file_not_found", "path": str(args.path)}))
        return 1

    cache_root = args.cache_root or _cache_root_from_env()
    payload = build_payload(
        args.path,
        rel_posix=args.rel_posix,
        cache_root=cache_root,
    )
    if cache_root is not None:
        save_cached_json(cache_root, key=file_cache_key(args.path), suffix="diagnostics", payload={"result": "local_ezdxf"})
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
