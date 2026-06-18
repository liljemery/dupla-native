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
from runtime_paths import coordination_cache_root, coordination_output_root, load_project_env

logger = logging.getLogger(__name__)

FAST_COMPARE_APS_PROFILE = "fast_compare_aps"
FAST_COMPARE_PROFILE = "fast_compare"

load_project_env()


def _shared_cache_root() -> Path:
    """Persistent APS/accore cache shared across clash jobs."""
    return coordination_cache_root()


def _max_workers() -> int:
    return max(1, int(os.getenv("COORDINATION_MAX_WORKERS", "6")))


def _aps_configured() -> bool:
    return bool((os.getenv("CLIENT_ID") or "").strip() and (os.getenv("CLIENT_SECRET") or "").strip())


def _accore_available() -> bool:
    import platform

    if platform.system() != "Windows":
        return False
    accore = Path(
        os.getenv(
            "ACCORECONSOLE_PATH",
            r"C:\Program Files\Autodesk\AutoCAD 2027\accoreconsole.exe",
        )
    )
    dll = (
        _dupla_root()
        / "aps_integration"
        / "DuplaExtractor"
        / "bin"
        / "Release"
        / "net10.0-windows"
        / "DuplaExtractor.dll"
    )
    return accore.is_file() and dll.is_file()


def _resolve_analysis_profile() -> str:
    """Pick the fast clash profile consistently on Windows, macOS and Linux."""
    override = (os.getenv("COORDINATION_ANALYSIS_PROFILE") or "").strip()
    if override:
        return override
    # Preferred: scheduling + parallel APS on every OS when credentials exist.
    if _aps_configured():
        return FAST_COMPARE_APS_PROFILE
    # Windows without APS: local accore (still parallel via fast_compare).
    if _accore_available():
        return FAST_COMPARE_PROFILE
    return FAST_COMPARE_APS_PROFILE


def _extract_filename_from_source_ref(ref: str) -> str:
    """Extract just the basename from a source_ref path like '/tmp/.../inputs/PLANOS/.../file.dwg|...'."""
    path_part = ref.split("|")[0]
    return Path(path_part).name


def _conflicts_to_primary_incidents(report: dict[str, Any]) -> dict[str, Any]:
    """Convert clash_project_report (standard profile) conflicts → primary_incidents format."""
    from collections import defaultdict
    import math

    conflicts: list[dict[str, Any]] = report.get("conflicts") or []

    # Group conflicts by (file_a, file_b) pair — file names extracted from source_refs
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for c in conflicts:
        refs = c.get("source_refs") or []
        file_a = _extract_filename_from_source_ref(refs[0]) if len(refs) > 0 else c.get("discipline_a", "?")
        file_b = _extract_filename_from_source_ref(refs[1]) if len(refs) > 1 else c.get("discipline_b", "?")
        key = (file_a, file_b) if file_a <= file_b else (file_b, file_a)
        groups[key].append(c)

    incidents: list[dict[str, Any]] = []
    for idx, ((file_a, file_b), members) in enumerate(
        sorted(groups.items(), key=lambda kv: -sum(c.get("plan_intersection_area_mm2", 0) for c in kv[1])),
        start=1,
    ):
        max_area = max((c.get("plan_intersection_area_mm2", 0) for c in members), default=0)
        max_depth = max((c.get("overlap_depth_z_mm", 0) for c in members), default=0)
        disciplines = {c.get("discipline_a") for c in members} | {c.get("discipline_b") for c in members}

        # Priority: critical if large overlap, high otherwise (all are HARD clashes)
        # Using 1m² = 1_000_000 mm² as threshold for critical
        priority = "critical" if max_area >= 1_000_000 else "high"

        rep = members[0]
        rep_centroid = rep.get("plan_intersection_centroid_mm") or [0, 0]
        level_id = (rep.get("level_ids") or ["NASAS_ARQ_P1_NPT"])[0]

        incidents.append({
            "incident_id": f"incident_{idx:04d}",
            "file_pair": [file_a, file_b],
            "disciplines": sorted(disciplines),
            "level_id": level_id,
            "priority": priority,
            "member_count": len(members),
            "max_area_mm2": round(max_area),
            "max_overlap_depth_z_mm": round(max_depth),
            "centroid_mm": [round(rep_centroid[0]), round(rep_centroid[1])],
            "description": (
                f"HARD: {' vs '.join(sorted(disciplines))} ({level_id}). "
                f"Solapamiento vertical: {round(max_depth)} mm. "
                f"Área en planta: {round(max_area):,} mm². "
                f"Archivos: {file_a} ↔ {file_b}"
            ),
            "representative_conflict": {
                "clash_type": rep.get("clash_type", "HARD"),
                "discipline_a": rep.get("discipline_a"),
                "discipline_b": rep.get("discipline_b"),
                "overlap_depth_z_mm": rep.get("overlap_depth_z_mm"),
                "plan_intersection_area_mm2": rep.get("plan_intersection_area_mm2"),
                "plan_intersection_bounds_mm": rep.get("plan_intersection_bounds_mm"),
                "plan_intersection_centroid_mm": rep.get("plan_intersection_centroid_mm"),
                "confidence": rep.get("confidence"),
            },
        })

    return {
        "incidents": incidents,
        "incident_count": len(incidents),
        "incident_conflict_count": len(conflicts),
        "generated_at": report.get("generated_at"),
        "project_name": report.get("project_name"),
        "analysis_profile": "standard",
    }


def _dupla_root() -> Path:
    env_val = os.getenv("DUPLA_ROOT", "").strip()
    if env_val:
        return Path(env_val)
    # Auto-detect motor bundled inside the repo (local dev without env var)
    bundled = Path(__file__).resolve().parents[2] / "motor"
    if bundled.is_dir():
        return bundled
    raise FileNotFoundError(
        "Motor Dupla no encontrado. Define DUPLA_ROOT o ejecuta desde el monorepo (motor/ en la raíz)."
    )


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


def _generate_cohort_manifest(inputs_dir: Path, output_dir: Path) -> Path | None:
    """Generate a cohort manifest with all DWG/DXF files in the inputs dir.

    Required when files come from different date-based cohorts (different filenames
    with no shared issue_key). The manifest forces the motor to treat them as a
    single comparable set.
    """
    dwg_files = sorted(inputs_dir.rglob("*.dwg")) + sorted(inputs_dir.rglob("*.dxf"))
    if not dwg_files:
        return None

    source_files = [str(p.relative_to(inputs_dir)) for p in dwg_files]
    manifest = {
        "cohort_name": "folder_run",
        "source_files": source_files,
    }
    manifest_path = output_dir / "cohort_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Cohort manifest generado: %d archivos → %s", len(source_files), manifest_path)
    return manifest_path


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
            f"Dupla runner not found at {script}. Set DUPLA_ROOT or COORDINATION_SMOKE_MODE=true."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    clash_report = output_dir / "clash_project_report.json"

    analysis_profile = _resolve_analysis_profile()
    logger.info(
        "Clash analysis profile=%s aps=%s accore=%s workers=%d",
        analysis_profile,
        _aps_configured(),
        _accore_available(),
        _max_workers(),
    )

    cmd = [
        sys.executable,
        str(script),
        "--analysis-profile",
        analysis_profile,
        "--nasas-root",
        str(inputs_dir),
        "--registry",
        str(registry_path),
        "--output",
        str(clash_report),
        "--shared-site-origin",
        "--stage",
        "full",
    ]

    if analysis_profile == FAST_COMPARE_APS_PROFILE:
        cmd.append("--dwg-via-aps")

    cache_root = _shared_cache_root()
    cmd.extend(["--cache-root", str(cache_root), "--max-workers", str(_max_workers())])

    # For folder-driven runs, files often have mismatched dates → generate a
    # cohort manifest so the motor treats them as a single comparable set.
    cohort_manifest = _generate_cohort_manifest(inputs_dir, output_dir)
    if cohort_manifest:
        cmd.extend(["--cohort-manifest", str(cohort_manifest)])

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
            f"Coordination runner exited {proc.returncode}: {(proc.stderr or proc.stdout or '')[-800:]}"
        )
    return proc.returncode


def _aps_diag_by_file() -> dict[str, dict[str, Any]]:
    """Map file name -> APS diagnostics (result/aps_error) from the shared cache."""
    out: dict[str, dict[str, Any]] = {}
    try:
        cache_root = _shared_cache_root()
    except Exception:
        return out
    if not cache_root.is_dir():
        return out
    for diag_path in cache_root.glob("*.diagnostics.json"):
        diag = load_json_if_exists(diag_path)
        if isinstance(diag, dict) and diag.get("path"):
            out[str(diag["path"])] = diag
    return out


def _enrich_analyzed_documents(
    analyzed_documents: list[dict[str, Any]],
    *,
    output_dir: Path,
    clash_report: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    element_counts: dict[str, int] = {}
    plan_geometry = load_json_if_exists(output_dir / "plan_geometry.json")
    if isinstance(plan_geometry, dict):
        for file_name, payload in (plan_geometry.get("files") or {}).items():
            if isinstance(payload, dict):
                element_counts[str(file_name)] = int(payload.get("element_count") or 0)

    if clash_report:
        for group in clash_report.get("issue_groups") or []:
            if not isinstance(group, dict):
                continue
            count = int(group.get("element_count") or 0)
            for source in group.get("source_files") or []:
                element_counts[Path(str(source)).name] = count

    aps_diags = _aps_diag_by_file()

    enriched: list[dict[str, Any]] = []
    for doc in analyzed_documents:
        if not isinstance(doc, dict):
            continue
        file_name = str(doc.get("file_name") or doc.get("original_name") or "")
        element_count = int(doc.get("element_count") or element_counts.get(file_name) or 0)
        status = str(doc.get("status") or "ok")
        if element_count <= 0 and status == "ok":
            status = "warning"

        extra: dict[str, Any] = {}
        diag = aps_diags.get(file_name)
        if isinstance(diag, dict):
            aps_result = str(diag.get("result") or "")
            extra["aps_result"] = aps_result
            viewer_count = int(diag.get("viewer_elements") or 0)
            if aps_result in {"viewer_geometry", "viewer_cache"}:
                extra["geometry_quality"] = "exact"
                extra["geometry_source"] = "dwg_aps_viewer_2d"
            elif aps_result == "proxy":
                extra["geometry_quality"] = "proxy"
                extra["geometry_source"] = "dwg_aps_properties_proxy"
            elif aps_result == "quota_exceeded":
                extra["aps_note"] = (
                    "APS Model Derivative sin cuota (plan Free agotado o requiere "
                    "Flex tokens). Se usó geometría de PDF/local como respaldo."
                )
            elif aps_result in {"invalid_file", "invalid_file_cached"}:
                extra["aps_note"] = (
                    "Autodesk no pudo traducir el DWG (archivo rechazado por el "
                    "extractor). Se usó geometría de PDF/local como respaldo."
                )
            elif aps_result == "viewer_empty" and viewer_count == 0:
                extra["aps_note"] = (
                    "Volcado Viewer presente pero sin elementos convertidos; "
                    "revise caché o re-ejecute extracción."
                )
            if viewer_count > 0:
                extra["viewer_elements"] = viewer_count

        enriched.append(
            {
                **doc,
                **extra,
                "element_count": element_count,
                "status": status,
                "retryable": status in {"error", "warning"},
            }
        )
    return enriched


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
        primary_payload = load_json_if_exists(output_dir / "primary_incidents.json")
        clash_report = load_json_if_exists(output_dir / "clash_project_report.json")
        if isinstance(primary_payload, dict) and primary_payload.get("incidents") is not None:
            primary = primary_payload
            logger.info(
                "Loaded %d primary incidents from fast_compare output",
                int(primary.get("incident_count") or len(primary.get("incidents") or [])),
            )
        elif clash_report and clash_report.get("conflict_count", 0) > 0:
            primary = _conflicts_to_primary_incidents(clash_report)
            logger.info(
                "Converted %d conflicts → %d primary incidents",
                clash_report["conflict_count"],
                primary["incident_count"],
            )
        else:
            report_source = clash_report if isinstance(clash_report, dict) else {}
            if not report_source and isinstance(primary_payload, dict):
                report_source = primary_payload
            primary = {
                "incidents": [],
                "incident_count": 0,
                "incident_conflict_count": int(report_source.get("conflict_count") or 0),
                "generated_at": report_source.get("generated_at"),
                "project_name": project_name,
                "analysis_profile": report_source.get("analysis_profile", "standard"),
            }
        (output_dir / "primary_incidents.json").write_text(
            json.dumps(primary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        analyzed_documents = _enrich_analyzed_documents(
            analyzed_documents,
            output_dir=output_dir,
            clash_report=clash_report,
        )
        context = load_json_if_exists(output_dir / "coordination_report_context.json")
        summary_payload = clash_report
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
        analysis_mode="smoke" if smoke_mode else "real",
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
