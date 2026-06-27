"""Bridge to Dupla coordination runner (Option B from integration instructive)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from adapters.dupla_reports import adapt_smoke_primary, generate_report_artifacts
from adapters.manifest import stage_project_inputs
from adapters.report_mapper import load_json_if_exists, map_to_structural_analysis_report
from runtime_paths import coordination_cache_root, coordination_output_root, load_project_env

logger = logging.getLogger(__name__)

_MAC_ODA_CONVERTER = Path("/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter")

FAST_COMPARE_PROFILE = "fast_compare"
FAST_COMPARE_LOCAL_PROFILE = "fast_compare_local"
FAST_COMPARE_APS_PROFILE = "fast_compare_aps"

load_project_env()


def _shared_cache_root() -> Path:
    """Persistent CAD extraction cache shared across clash jobs."""
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
        / "coordination"
        / "tools"
        / "DuplaExtractor"
        / "bin"
        / "Release"
        / "net10.0-windows"
        / "DuplaExtractor.dll"
    )
    return accore.is_file() and dll.is_file()


def _resolve_analysis_profile(*, budget_scope: bool = False) -> str:
    """Pick the fast clash profile consistently on Windows, macOS and Linux."""
    override = (os.getenv("COORDINATION_ANALYSIS_PROFILE") or "").strip()
    if override:
        return override
    if budget_scope and _aps_configured():
        return FAST_COMPARE_APS_PROFILE
    if _accore_available():
        return FAST_COMPARE_PROFILE
    return FAST_COMPARE_LOCAL_PROFILE


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

        rep = max(
            members,
            key=lambda c: (
                c.get("plan_intersection_area_mm2") or 0,
                c.get("overlap_depth_z_mm") or 0,
            ),
        )
        rep_centroid = rep.get("plan_intersection_centroid_mm") or [0, 0]
        level_ids = rep.get("level_ids") or []
        level_id = level_ids[0] if level_ids else None

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


def _discipline_from_bucket(bucket: str) -> str:
    mapping = {
        "arquitectura": "ARQUITECTURA",
        "estructura": "ESTRUCTURA",
        "electrica": "ELECTRICIDAD",
        "mecanica": "CLIMATIZACION",
        "plomeria": "FONTANERIA",
    }
    return mapping.get(str(bucket or "").strip().lower(), "ARQUITECTURA")


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


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using %d", name, raw, default)
        return default


def _invoke_runner(
    *,
    inputs_dir: Path,
    registry_path: Path,
    output_dir: Path,
    include_disciplines: list[str] | None = None,
    control_points_path: Path | None = None,
    budget_scope: bool = False,
) -> int:
    script = _runner_script()
    if not script.is_file():
        raise FileNotFoundError(
            f"Dupla runner not found at {script}. Set DUPLA_ROOT or COORDINATION_SMOKE_MODE=true."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    clash_report = output_dir / "clash_project_report.json"

    analysis_profile = _resolve_analysis_profile(budget_scope=budget_scope)
    runner_profile = "standard" if analysis_profile == FAST_COMPARE_APS_PROFILE else analysis_profile
    logger.info(
        "Clash analysis profile=%s runner_profile=%s aps=%s budget_scope=%s accore=%s workers=%d",
        analysis_profile,
        runner_profile,
        _aps_configured(),
        budget_scope,
        _accore_available(),
        _max_workers(),
    )

    cmd = [
        sys.executable,
        str(script),
        "--analysis-profile",
        runner_profile,
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

    max_entities = int(os.getenv("COORDINATION_MAX_DWG_ENTITIES", "800"))
    cmd.extend(["--max-dwg-entities", str(max_entities)])

    # For folder-driven runs, files often have mismatched dates → generate a
    # cohort manifest so the motor treats them as a single comparable set.
    cohort_manifest = _generate_cohort_manifest(inputs_dir, output_dir)
    if cohort_manifest:
        cmd.extend(["--cohort-manifest", str(cohort_manifest)])

    if include_disciplines:
        cmd.extend(["--include-disciplines", ",".join(include_disciplines)])

    if control_points_path and control_points_path.is_file():
        cmd.extend(["--control-points", str(control_points_path)])

    logger.info("Running coordination: %s", " ".join(cmd))
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{_dupla_root()}:{env.get('PYTHONPATH', '')}"

    proc = subprocess.run(
        cmd,
        cwd=str(_dupla_root()),
        env=env,
        capture_output=True,
        text=True,
        timeout=_env_int("COORDINATION_JOB_TIMEOUT_SECONDS", 3600),
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


def _oda_converter_path() -> Path | None:
    configured = os.getenv("ODA_FILE_CONVERTER", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.append(_MAC_ODA_CONVERTER)
    path_name = shutil.which("ODAFileConverter")
    if path_name:
        candidates.append(Path(path_name))
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    return None


def _convert_dwg_inputs_to_dxf(inputs_dir: Path, output_dir: Path) -> Path | None:
    dwg_files = sorted(Path(inputs_dir).rglob("*.dwg"))
    if not dwg_files:
        return None

    dupla_root = _dupla_root()
    if str(dupla_root) not in sys.path:
        sys.path.insert(0, str(dupla_root))

    try:
        from coordination.extraction.cad_cache import file_cache_key
        from coordination.extraction.libredwg_convert import convert_dwg_to_dxf, dwg2dxf_available, is_binary_dwg
    except Exception as exc:
        logger.info("Hybrid geometry DWG→DXF skipped: %s", exc)
        return None

    if not dwg2dxf_available():
        logger.info("Hybrid geometry DWG→DXF skipped: dwg2dxf not available")
        return None

    dxf_dir = Path(output_dir) / "hybrid_geometry" / "dxf_inputs"
    dxf_dir.mkdir(parents=True, exist_ok=True)
    converted = 0
    for dwg_path in dwg_files:
        if not is_binary_dwg(dwg_path):
            continue
        try:
            convert_dwg_to_dxf(dwg_path, output_dir=dxf_dir / file_cache_key(dwg_path))
            converted += 1
        except Exception as exc:
            logger.warning("LibreDWG convert failed for %s: %s", dwg_path.name, exc)
    if converted == 0:
        return None
    return dxf_dir


def _staged_index(staged_files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in staged_files:
        raw_path = item.get("path")
        if raw_path:
            path = Path(str(raw_path))
            out[str(path.resolve())] = item
            out[path.name.lower()] = item
            out[path.stem.lower()] = item
    return out


def _build_hybrid_geometry_artifacts(
    *,
    inputs_dir: Path,
    output_dir: Path,
    staged_files: list[dict[str, Any]],
) -> dict[str, Any] | None:
    enabled = os.getenv("COORDINATION_HYBRID_GEOMETRY", "true").lower() not in ("0", "false", "no")
    if not enabled:
        logger.info("Hybrid geometry artifact generation disabled by COORDINATION_HYBRID_GEOMETRY")
        return None

    dupla_root = _dupla_root()
    root_text = str(dupla_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    try:
        from coordination.extraction.hybrid_orchestrator import (
            build_dxf_only_audit_artifacts,
            build_hybrid_artifacts,
            discover_dxf_only_sources,
            discover_hybrid_sources,
        )
    except Exception as exc:
        logger.warning("Hybrid geometry modules unavailable: %s", exc)
        return None

    staged_by_path = _staged_index(staged_files)

    def discipline_for_path(path: Path) -> str:
        staged = (
            staged_by_path.get(str(path.resolve()))
            or staged_by_path.get(path.name.lower())
            or staged_by_path.get(path.stem.lower())
            or {}
        )
        return _discipline_from_bucket(str(staged.get("discipline_bucket") or ""))

    cache_dir = output_dir / "cache"
    sources = discover_hybrid_sources(inputs_dir=inputs_dir, cache_dir=cache_dir, discipline_for_path=discipline_for_path)
    if not sources:
        converted_dir = _convert_dwg_inputs_to_dxf(inputs_dir, output_dir)
        search_dir = converted_dir if converted_dir is not None else inputs_dir
        dxf_only = discover_dxf_only_sources(inputs_dir=search_dir, discipline_for_path=discipline_for_path)
        if dxf_only:
            logger.info("Hybrid geometry: DXF-only audit for %d source(s)", len(dxf_only))
            return build_dxf_only_audit_artifacts(dxf_only, output_dir / "hybrid_geometry")
        if converted_dir is not None:
            sources = discover_hybrid_sources(inputs_dir=converted_dir, cache_dir=cache_dir, discipline_for_path=discipline_for_path)
    if not sources:
        logger.info("Hybrid geometry skipped: no DXF sources discovered")
        return None

    try:
        bundle = build_hybrid_artifacts(sources, output_dir / "hybrid_geometry")
    except Exception as exc:
        logger.warning("Hybrid geometry artifact generation failed: %s", exc, exc_info=True)
        return None

    summary = bundle.to_dict()
    logger.info(
        "Hybrid geometry artifacts generated: sources=%d plan=%s",
        len(bundle.results),
        bundle.plan_geometry_path,
    )
    return summary


def _hybrid_geometry_audit_status(summary: dict[str, Any] | None) -> str | None:
    if not isinstance(summary, dict):
        return None
    audit = summary.get("audit")
    if not isinstance(audit, dict):
        return None
    status = str(audit.get("status") or "").strip().lower()
    return status or None


def _hybrid_geometry_audit_gate(summary: dict[str, Any] | None) -> dict[str, Any]:
    """Apply the optional production gate for hybrid geometry quality."""
    status = _hybrid_geometry_audit_status(summary) or "missing"
    mode = os.getenv("COORDINATION_HYBRID_GEOMETRY_AUDIT_GATE", "report_only").strip().lower()
    if mode in {"", "0", "false", "no", "off", "report", "report_only"}:
        return {"mode": "report_only", "status": status, "blocked": False}
    if mode == "fail":
        blocked = status in {"fail", "missing"}
    elif mode == "strict":
        blocked = status in {"warn", "fail", "missing"}
    else:
        logger.warning(
            "Unknown COORDINATION_HYBRID_GEOMETRY_AUDIT_GATE=%s; using report_only",
            mode,
        )
        return {"mode": "report_only", "status": status, "blocked": False}

    result = {"mode": mode, "status": status, "blocked": blocked}
    if blocked:
        raise RuntimeError(
            f"Hybrid geometry audit gate blocked the run: mode={mode}, status={status}. "
            "Review hybrid_geometry/hybrid_geometry_audit.md for details."
        )
    return result


def _enrich_analyzed_documents(
    analyzed_documents: list[dict[str, Any]],
    *,
    output_dir: Path,
    clash_report: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    element_counts: dict[str, int] = {}
    for plan_path in (
        output_dir / "plan_geometry.json",
        output_dir / "hybrid_geometry" / "plan_geometry.hybrid.json",
    ):
        plan_geometry = load_json_if_exists(plan_path)
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

    enriched: list[dict[str, Any]] = []
    for doc in analyzed_documents:
        if not isinstance(doc, dict):
            continue
        file_name = str(doc.get("file_name") or doc.get("original_name") or "")
        element_count = int(doc.get("element_count") or element_counts.get(file_name) or 0)
        status = str(doc.get("status") or "ok")
        if element_count <= 0 and status == "ok":
            status = "warning"

        enriched.append(
            {
                **doc,
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
    control_points: list[dict[str, Any]] | None = None,
    reanalysis_clash_code: str | None = None,
    budget_scope: bool = False,
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
        control_points_path: Path | None = None
        if control_points:
            control_points_path = output_dir / "control_points.json"
            control_points_path.write_text(
                json.dumps(control_points, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        _invoke_runner(
            inputs_dir=inputs_dir,
            registry_path=Path(staging["registry_path"]),
            output_dir=output_dir,
            include_disciplines=staging.get("include_disciplines") or None,
            control_points_path=control_points_path,
            budget_scope=budget_scope,
        )
        hybrid_geometry_summary = _build_hybrid_geometry_artifacts(
            inputs_dir=inputs_dir,
            output_dir=output_dir,
            staged_files=staging.get("staged_files") or [],
        )
        hybrid_geometry_gate = _hybrid_geometry_audit_gate(hybrid_geometry_summary)
        # If the runner used the standard profile (non-Windows), convert its
        # clash_project_report.json (conflicts) → primary_incidents format.
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
        if hybrid_geometry_summary and isinstance(context, dict):
            context["hybrid_geometry"] = hybrid_geometry_summary
            context["hybrid_geometry_audit_gate"] = hybrid_geometry_gate

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
    hybrid_dir = output_dir / "hybrid_geometry"
    hybrid_plan = hybrid_dir / "plan_geometry.hybrid.json"
    hybrid_manifest = hybrid_dir / "hybrid_geometry_manifest.json"
    hybrid_audit = hybrid_dir / "hybrid_geometry_audit.json"
    hybrid_audit_md = hybrid_dir / "hybrid_geometry_audit.md"
    if hybrid_plan.is_file():
        artifacts["plan_geometry_hybrid"] = str(hybrid_plan)
    if hybrid_manifest.is_file():
        artifacts["hybrid_geometry_manifest"] = str(hybrid_manifest)
    if hybrid_audit.is_file():
        artifacts["hybrid_geometry_audit"] = str(hybrid_audit)
    if hybrid_audit_md.is_file():
        artifacts["hybrid_geometry_audit_md"] = str(hybrid_audit_md)
    if not smoke_mode and "hybrid_geometry_summary" in locals() and hybrid_geometry_summary:
        artifacts["hybrid_geometry"] = json.dumps(hybrid_geometry_summary, ensure_ascii=False)
        audit_status = _hybrid_geometry_audit_status(hybrid_geometry_summary)
        if audit_status:
            artifacts["hybrid_geometry_audit_status"] = audit_status
        if "hybrid_geometry_gate" in locals():
            artifacts["hybrid_geometry_audit_gate"] = json.dumps(hybrid_geometry_gate, ensure_ascii=False)

    return {
        "report": report,
        "artifacts": artifacts,
    }
