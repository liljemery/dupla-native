"""Generate Dupla coordination markdown artifacts for clash jobs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_dupla_reporting():
    try:
        from coordination.reporting.reporting import (
            build_coordination_report_context,
            render_coordination_human_report_markdown,
            render_coordination_report_markdown,
        )
        from coordination.reporting.revision_report import (
            render_revision_report,
            revision_report_filename,
        )

        return {
            "build_coordination_report_context": build_coordination_report_context,
            "render_coordination_human_report_markdown": render_coordination_human_report_markdown,
            "render_coordination_report_markdown": render_coordination_report_markdown,
            "render_revision_report": render_revision_report,
            "revision_report_filename": revision_report_filename,
        }
    except ImportError as exc:
        logger.warning("Dupla reporting modules unavailable: %s", exc)
        return None


def _cad_entries(file_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        e
        for e in file_entries
        if str(e.get("original_name", "")).lower().endswith((".dwg", ".dxf"))
    ]


def adapt_smoke_primary(primary: dict[str, Any], file_entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Rewrite smoke fixture file pairs to match the real folder inventory."""
    data = dict(primary)
    cad = _cad_entries(file_entries)
    by_bucket: dict[str, list[str]] = {}
    for entry in cad:
        bucket = str(entry.get("discipline_bucket") or "sin_clasificar")
        by_bucket.setdefault(bucket, []).append(str(entry.get("original_name")))

    arq = by_bucket.get("arquitectura", [])
    est = by_bucket.get("estructura", [])
    elc = by_bucket.get("electrica", [])
    mec = by_bucket.get("mecanica", [])

    pair_names: list[tuple[str, str]] = []
    if arq and est:
        pair_names.append((arq[0], est[0]))
    if len(arq) > 1 and est:
        pair_names.append((arq[1], est[0]))
    if arq and elc:
        pair_names.append((arq[0], elc[0]))
    if arq and mec:
        pair_names.append((arq[0], mec[0]))
    if not pair_names and len(cad) >= 2:
        pair_names.append((str(cad[0].get("original_name")), str(cad[1].get("original_name"))))

    templates = list(data.get("incidents") or [{}])
    incidents: list[dict[str, Any]] = []
    for idx, (file_a, file_b) in enumerate(pair_names or [("", "")], start=1):
        template = dict(templates[min(idx - 1, len(templates) - 1)] if templates else {})
        template["incident_id"] = template.get("incident_id") or f"incident_smoke_{idx:04d}"
        template["file_pair"] = [file_a, file_b]
        incidents.append(template)

    data["incidents"] = incidents
    data["incident_count"] = len(incidents)
    data["incident_conflict_count"] = sum(int(inc.get("member_count") or 1) for inc in incidents)
    return data


def _smoke_summary_payload(file_entries: list[dict[str, Any]], primary: dict[str, Any]) -> dict[str, Any]:
    cad = _cad_entries(file_entries)
    pair_count = max(len(primary.get("incidents") or []), 1)
    return {
        "project_name": primary.get("project_name"),
        "status": "completed",
        "analysis_profile": primary.get("analysis_profile", "fast_compare"),
        "generated_at": primary.get("generated_at"),
        "scheduled_pair_count": pair_count,
        "scheduled_file_count": len(cad),
        "element_count": 0,
        "selected_candidate_count": pair_count,
    }


def _smoke_pair_schedule(primary: dict[str, Any]) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    for inc in primary.get("incidents") or []:
        file_pair = inc.get("file_pair") or []
        if len(file_pair) < 2:
            continue
        conflict = inc.get("representative_conflict") or {}
        pairs.append(
            {
                "file_a": file_pair[0],
                "file_b": file_pair[1],
                "scheduled": True,
                "discipline_a": conflict.get("discipline_a", ""),
                "discipline_b": conflict.get("discipline_b", ""),
                "level_id": inc.get("level_id"),
            }
        )
    return {"pairs": pairs}


def _fallback_revision_md(project_name: str, primary: dict[str, Any]) -> str:
    count = len(primary.get("incidents") or [])
    return (
        f"# Guía de Revisión Manual de Clashes — {project_name}\n\n"
        f"## Estado — {count} incidencia(s) primaria(s)\n\n"
        f"_Reporte generado en modo fallback (Dupla reporting no disponible)._\n"
    )


def _fallback_technical_md(project_name: str, context: dict[str, Any]) -> str:
    counts = context.get("counts") or {}
    return (
        f"# Technical Coordination Report - {project_name}\n\n"
        f"- Scheduled pairs: {counts.get('scheduled_pairs', 0)}\n"
        f"- Primary incidents: {counts.get('primary_incidents', 0)}\n"
    )


def _fallback_human_md(project_name: str, context: dict[str, Any]) -> str:
    counts = context.get("counts") or {}
    return (
        f"# Coordination Report Human - {project_name}\n\n"
        f"## Resumen ejecutivo\n\n"
        f"- Pares revisados: {counts.get('scheduled_pairs', 0)}\n"
        f"- Incidencias primarias: {counts.get('primary_incidents', 0)}\n"
    )


def generate_report_artifacts(
    *,
    output_dir: Path,
    project_name: str,
    primary_payload: dict[str, Any],
    file_entries: list[dict[str, Any]],
    analyzed_documents: list[dict[str, Any]],
    coordination_context: dict[str, Any] | None = None,
    summary_payload: dict[str, Any] | None = None,
    pair_schedule_payload: dict[str, Any] | None = None,
    inputs_dir: Path | None = None,
    smoke_mode: bool = False,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    primary_path = output_dir / "primary_incidents.json"
    primary_path.write_text(json.dumps(primary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    dupla = _load_dupla_reporting()
    project_root = inputs_dir or output_dir

    if smoke_mode or not summary_payload:
        summary_payload = summary_payload or _smoke_summary_payload(file_entries, primary_payload)
    if smoke_mode or not pair_schedule_payload:
        pair_schedule_payload = pair_schedule_payload or _smoke_pair_schedule(primary_payload)

    if coordination_context is None:
        if dupla:
            coordination_context = dupla["build_coordination_report_context"](
                summary_payload=summary_payload or {},
                primary_payload=primary_payload,
            )
        else:
            coordination_context = {
                "project_name": project_name,
                "counts": {
                    "scheduled_pairs": len(pair_schedule_payload.get("pairs") or []),
                    "scheduled_files": len(_cad_entries(file_entries)),
                    "primary_incidents": len(primary_payload.get("incidents") or []),
                    "primary_members": primary_payload.get("incident_conflict_count", 0),
                },
                "pair_rollups": [],
                "defendable_incidents": [],
                "validation_incidents": [],
                "reader_sections": {},
                "all_incidents": [],
            }

    context_path = output_dir / "coordination_report_context.json"
    context_path.write_text(json.dumps(coordination_context, ensure_ascii=False, indent=2), encoding="utf-8")

    pair_schedule_path = output_dir / "pair_schedule.json"
    pair_schedule_path.write_text(json.dumps(pair_schedule_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if dupla:
        revision_md = dupla["render_revision_report"](
            project_name=project_name,
            primary_payload=primary_payload,
            scheduled_pairs=pair_schedule_payload.get("pairs") or [],
            pair_rollups=coordination_context.get("pair_rollups"),
            nasas_root=project_root,
            generated_at=primary_payload.get("generated_at"),
        )
        revision_filename = dupla["revision_report_filename"](project_name)
        technical_md = dupla["render_coordination_report_markdown"](
            project_name=project_name,
            root=project_root,
            summary_payload=summary_payload or {},
            primary_payload=primary_payload,
            pair_schedule_payload=pair_schedule_payload,
        )
        human_md = dupla["render_coordination_human_report_markdown"](
            project_name=project_name,
            run_label=primary_payload.get("analysis_profile") or "fast_compare",
            summary_payload=summary_payload or {},
            readiness_payload={},
            coordinate_audit_payload={},
            pair_schedule_payload=pair_schedule_payload,
            report_context=coordination_context,
        )
    else:
        revision_filename = f"REVISION_CLASHES_ARQUITECTO_{project_name.split()[0].upper()}.md"
        revision_md = _fallback_revision_md(project_name, primary_payload)
        technical_md = _fallback_technical_md(project_name, coordination_context)
        human_md = _fallback_human_md(project_name, coordination_context)

    revision_path = output_dir / revision_filename
    technical_path = output_dir / "technical_coordination_report.md"
    human_path = output_dir / "coordination_report_human.md"
    revision_path.write_text(revision_md, encoding="utf-8")
    technical_path.write_text(technical_md, encoding="utf-8")
    human_path.write_text(human_md, encoding="utf-8")

    return {
        "revision_md": revision_md,
        "technical_md": technical_md,
        "human_md": human_md,
        "primary_incidents": json.dumps(primary_payload, ensure_ascii=False),
        "coordination_context": json.dumps(coordination_context, ensure_ascii=False),
        "pair_schedule": json.dumps(pair_schedule_payload, ensure_ascii=False),
        "analyzed_documents": analyzed_documents,
        "paths": {
            "output_dir": str(output_dir),
            "revision_md": str(revision_path),
            "technical_md": str(technical_path),
            "human_md": str(human_path),
            "primary_incidents": str(primary_path),
            "coordination_context": str(context_path),
            "pair_schedule": str(pair_schedule_path),
        },
    }
