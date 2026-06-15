"""Bridge to Dupla coordination runner (Option B from integration instructive)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from adapters.dupla_reports import adapt_smoke_primary, generate_report_artifacts
from adapters.manifest import stage_project_inputs
from adapters.report_mapper import load_json_if_exists, map_to_structural_analysis_report

logger = logging.getLogger(__name__)


def _dupla_root() -> Path:
    return Path(os.getenv("DUPLA_ROOT", "/dupla"))


def _runner_script() -> Path:
    return _dupla_root() / "coordination" / "scripts" / "run_nasas09_project_coordination.py"


def _smoke_primary_incidents(
    profile_slug: str,
    project_name: str,
    file_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "smoke_primary_incidents.json"
    if fixture.is_file():
        data = json.loads(fixture.read_text(encoding="utf-8"))
        data["project_name"] = project_name
        return adapt_smoke_primary(data, file_entries)
    fallback = {
        "generated_at": "2026-05-22T00:00:00+00:00",
        "project_name": project_name,
        "analysis_profile": "fast_compare",
        "incident_count": 1,
        "incident_conflict_count": 1,
        "incidents": [
            {
                "incident_id": "incident_smoke_0001",
                "file_pair": ["ARQ-PLANTA.dwg", "EST-LOSAS.dwg"],
                "level_id": "NPT_P1",
                "member_count": 1,
                "representative_conflict": {
                    "discipline_a": "ARQUITECTURA",
                    "discipline_b": "ESTRUCTURA",
                    "clash_type": "HARD",
                    "overlap_depth_z_mm": 150.0,
                    "plan_intersection_area_mm2": 120_000.0,
                },
                "confidence": "high",
            }
        ],
    }
    return adapt_smoke_primary(fallback, file_entries)


def _invoke_runner(
    *,
    inputs_dir: Path,
    registry_path: Path,
    output_dir: Path,
    include_disciplines: list[str] | None = None,
) -> int:
    script = _runner_script()
    if not script.is_file():
        raise FileNotFoundError(
            f"Dupla runner not found at {script}. Mount DUPLA_ROOT or set COORDINATION_SMOKE_MODE=true."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    clash_report = output_dir / "clash_project_report.json"

    cmd = [
        sys.executable,
        str(script),
        "--analysis-profile",
        "fast_compare",
        "--stage",
        "full",
        "--nasas-root",
        str(inputs_dir),
        "--registry",
        str(registry_path),
        "--output",
        str(clash_report),
        "--dwg-via-aps",
        "--shared-site-origin",
    ]

    cache_root = output_dir / "cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    cmd.extend(["--cache-root", str(cache_root)])

    if include_disciplines:
        cmd.extend(["--include-disciplines", ",".join(include_disciplines)])

    logger.info("Running coordination: %s", " ".join(cmd))
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{_dupla_root()}:{env.get('PYTHONPATH', '')}"

    proc = subprocess.run(
        cmd,
        cwd=str(_dupla_root()),
        env=env,
        capture_output=True,
        text=True,
        timeout=int(os.getenv("COORDINATION_JOB_TIMEOUT_SECONDS", "3600")),
    )
    if proc.stdout:
        logger.info("Runner stdout (tail): %s", proc.stdout[-4000:])
    if proc.stderr:
        logger.warning("Runner stderr (tail): %s", proc.stderr[-4000:])
    if proc.returncode != 0:
        raise RuntimeError(
            f"Coordination runner exited {proc.returncode}: {(proc.stderr or proc.stdout or '')[-800]}"
        )
    return proc.returncode


def run_clash_analysis(
    *,
    file_entries: list[dict[str, Any]],
    profile_slug: str,
    project_name: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Run clash detection and return StructuralAnalysisReport-shaped dict."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    staging = stage_project_inputs(
        file_entries=file_entries,
        output_dir=output_dir,
        profile_slug=profile_slug,
        project_name=project_name,
    )
    analyzed_documents = staging["analyzed_documents"]
    inputs_dir = Path(staging["inputs_dir"])

    smoke_mode = os.getenv("COORDINATION_SMOKE_MODE", "").lower() in ("1", "true", "yes")
    analysis_mode = "smoke" if smoke_mode else "real"
    logger.info("Clash analysis starting: mode=%s profile=%s project=%s", analysis_mode, profile_slug, project_name)
    summary_payload: dict[str, Any] | None = None
    pair_schedule_payload: dict[str, Any] | None = None

    if smoke_mode:
        primary = _smoke_primary_incidents(profile_slug, project_name, file_entries)
        context = None
    else:
        _invoke_runner(
            inputs_dir=inputs_dir,
            registry_path=Path(staging["registry_path"]),
            output_dir=output_dir,
            include_disciplines=staging.get("include_disciplines") or None,
        )
        primary = load_json_if_exists(output_dir / "primary_incidents.json") or {
            "incidents": [],
            "incident_count": 0,
            "generated_at": None,
            "project_name": project_name,
            "analysis_profile": "fast_compare",
        }
        context = load_json_if_exists(output_dir / "coordination_report_context.json")
        summary_payload = load_json_if_exists(output_dir / "clash_project_report.json")
        pair_schedule_payload = load_json_if_exists(output_dir / "pair_schedule.json")

    artifact_bundle = generate_report_artifacts(
        output_dir=output_dir,
        project_name=project_name,
        primary_payload=primary,
        file_entries=file_entries,
        analyzed_documents=analyzed_documents,
        coordination_context=context,
        summary_payload=summary_payload,
        pair_schedule_payload=pair_schedule_payload,
        inputs_dir=inputs_dir,
        smoke_mode=smoke_mode,
    )

    if context is None:
        context = json.loads(artifact_bundle["coordination_context"])

    report = map_to_structural_analysis_report(
        run_status="completed",
        project_name=project_name,
        profile_slug=profile_slug,
        primary_incidents=primary,
        coordination_context=context,
        analyzed_documents=analyzed_documents,
        analysis_mode=analysis_mode,
    )

    report_path = output_dir / "structural_analysis_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    artifacts = {
        "revision_md": artifact_bundle["revision_md"],
        "technical_md": artifact_bundle["technical_md"],
        "human_md": artifact_bundle["human_md"],
        "primary_incidents": artifact_bundle["primary_incidents"],
        "coordination_context": artifact_bundle["coordination_context"],
        "pair_schedule": artifact_bundle["pair_schedule"],
        "analyzed_documents": artifact_bundle["analyzed_documents"],
        "output_dir": artifact_bundle["paths"]["output_dir"],
    }

    return {
        "report": report,
        "artifacts": artifacts,
    }
