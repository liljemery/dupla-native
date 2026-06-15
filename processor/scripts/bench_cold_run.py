"""Cold-run benchmark helper for Dupla processor.

Run from the processor package root:

    python -m scripts.bench_cold_run --dwg nasas9.dwg --pdf nasas9.pdf \
        --discipline arquitectura --clear-cache
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))

from core.stage_cache import get_stats, reset_stats  # noqa: E402
from tasks import (  # noqa: E402
    _artifact_dir,
    _build_artifact_key,
    _env_int,
    run_dupla_pipeline,
)


def _safe_rmtree(path: Path) -> None:
    resolved = path.resolve()
    if not resolved.exists():
        return
    anchor = Path(resolved.anchor)
    if resolved == anchor or str(resolved) in {"\\", "/"}:
        raise RuntimeError(f"Refusing to remove unsafe path: {resolved}")
    shutil.rmtree(resolved)


def _load_upload(path: Path) -> tuple[str, bytes]:
    if not path.exists():
        raise FileNotFoundError(path)
    return path.name, path.read_bytes()


def _stage_seconds(stats: dict[str, dict[str, Any]], *stage_names: str) -> float:
    return round(
        sum(float(stats.get(stage, {}).get("seconds_saved_estimate", 0.0)) for stage in stage_names),
        3,
    )


def _print_timings(timings: dict[str, float]) -> None:
    print(json.dumps({"stage_timings_seconds": timings}, indent=2, sort_keys=True))
    print("\n| stage | after (cold) |")
    print("|---|---:|")
    for key in (
        "aps_extract_total",
        "pdf_render_total",
        "vision_total",
        "partida_total",
        "build_hybrid_total",
        "export_total",
        "wall_total",
    ):
        print(f"| {key} | {timings.get(key, 0.0):.3f}s |")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a cold Dupla processor benchmark.")
    parser.add_argument("--dwg", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--discipline", default="arquitectura")
    parser.add_argument("--project-name", default="bench_cold_run")
    parser.add_argument("--clear-cache", action="store_true")
    parser.add_argument(
        "--budget-seconds",
        type=float,
        default=float(os.getenv("BENCH_BUDGET_SECONDS", "360") or 360),
    )
    args = parser.parse_args()

    if not args.dwg.exists():
        parser.error(f"--dwg not found: {args.dwg}")
    if not args.pdf.exists():
        parser.error(f"--pdf not found: {args.pdf}")

    dwg_files = [_load_upload(args.dwg)]
    pdf_files = [_load_upload(args.pdf)]
    pdf_dpi = _env_int("DUPLA_PDF_DPI", 200, minimum=72)
    artifact_key = _build_artifact_key(dwg_files, pdf_files, pdf_dpi=pdf_dpi)

    if args.clear_cache:
        cache_dirs = {
            Path("/var/cache/dupla"),
            Path(os.getenv("DUPLA_CACHE_DIR") or "/app/cache"),
        }
        for cache_dir in cache_dirs:
            _safe_rmtree(cache_dir)
        _safe_rmtree(_artifact_dir(artifact_key))

    reset_stats()
    started = time.monotonic()
    run_dupla_pipeline(
        dwg_files,
        pdf_files=pdf_files,
        discipline_id=args.discipline,
        project_name=args.project_name,
        correlation_id="bench-cold-run",
    )
    wall_total = round(time.monotonic() - started, 3)
    stats = get_stats()

    timings = {
        "aps_extract_total": _stage_seconds(stats, "aps_extract"),
        "pdf_render_total": _stage_seconds(stats, "pdf_render"),
        "vision_total": _stage_seconds(stats, "vision_analyze_plan"),
        "partida_total": _stage_seconds(stats, "partida_generate_batch"),
        "build_hybrid_total": _stage_seconds(stats, "build_hybrid_exp"),
        "export_total": _stage_seconds(stats, "export_total"),
        "wall_total": wall_total,
    }
    _print_timings(timings)

    if wall_total > args.budget_seconds:
        print(
            f"FAIL: wall_total={wall_total:.3f}s exceeds budget={args.budget_seconds:.3f}s",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
