"""Map Dupla coordination artifacts to the frontend StructuralAnalysisReport contract."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_DISCIPLINE_LABELS = {
    "ARQUITECTURA": "Arquitectura",
    "ESTRUCTURA": "Estructura",
    "ELECTRICIDAD": "Eléctrica",
    "ELECTRICA": "Eléctrica",
    "MECANICA": "Mecánica",
    "CLIMATIZACION": "Mecánica",
    "FONTANERIA": "Plomería",
    "PLOMERIA": "Plomería",
}


def _format_discipline_label(raw: str) -> str:
    key = str(raw or "").strip().upper()
    if not key:
        return "Coordinación"
    return _DISCIPLINE_LABELS.get(key, raw.strip().title())


def _priority_from_incident(incident: dict[str, Any]) -> str:
    explicit = str(incident.get("priority") or "").lower()
    if explicit in {"critical", "high", "warning", "info"}:
        return explicit

    rep = incident.get("representative_conflict") or {}
    clash_type = str(rep.get("clash_type") or "").upper()
    overlap = float(rep.get("overlap_depth_z_mm") or incident.get("max_overlap_depth_z_mm") or 0)
    area = float(rep.get("plan_intersection_area_mm2") or incident.get("max_area_mm2") or 0)

    if clash_type == "HARD" and area >= 1_000_000:
        return "critical"
    if clash_type == "HARD" or overlap >= 100:
        return "high"
    if area >= 50_000 or overlap >= 50:
        return "warning"
    return "info"


def _disciplines_from_incident(incident: dict[str, Any]) -> list[str]:
    explicit = incident.get("disciplines")
    if isinstance(explicit, list) and explicit:
        out: list[str] = []
        for item in explicit:
            label = _format_discipline_label(str(item))
            if label not in out:
                out.append(label)
        if out:
            return out

    rep = incident.get("representative_conflict") or {}
    out = []
    for key in ("discipline_a", "discipline_b"):
        val = str(rep.get(key) or "").strip()
        if val:
            label = _format_discipline_label(val)
            if label not in out:
                out.append(label)
    return out or ["Coordinación"]


def _title_from_incident(incident: dict[str, Any]) -> str:
    rep = incident.get("representative_conflict") or {}
    level = str(incident.get("level_id") or "—")
    disciplines = _disciplines_from_incident(incident)
    if len(disciplines) >= 2:
        da, db = disciplines[0], disciplines[1]
    else:
        da = _format_discipline_label(str(rep.get("discipline_a") or "?"))
        db = _format_discipline_label(str(rep.get("discipline_b") or "?"))
    clash_type = str(rep.get("clash_type") or "CLASH")
    return f"{clash_type}: {da} vs {db} ({level})"


def _description_from_incident(incident: dict[str, Any]) -> str:
    explicit = str(incident.get("description") or "").strip()
    if explicit:
        return explicit

    rep = incident.get("representative_conflict") or {}
    parts: list[str] = []
    overlap = rep.get("overlap_depth_z_mm") or incident.get("max_overlap_depth_z_mm")
    if overlap is not None:
        parts.append(f"Solapamiento vertical: {overlap} mm")
    area = rep.get("plan_intersection_area_mm2") or incident.get("max_area_mm2")
    if area is not None:
        parts.append(f"Área en planta: {float(area):,.0f} mm²")
    pair = incident.get("file_pair") or []
    if isinstance(pair, list) and len(pair) >= 2:
        a = Path(str(pair[0])).name
        b = Path(str(pair[1])).name
        parts.append(f"Archivos: {a} ↔ {b}")
    notes = rep.get("notes") or []
    if isinstance(notes, list):
        for n in notes[:3]:
            if n:
                parts.append(str(n))
    return ". ".join(parts) if parts else "Conflicto de coordinación detectado entre disciplinas."


def _summary_from_clashes(clashes: list[dict[str, Any]], doc_count: int) -> dict[str, int]:
    errors = sum(1 for c in clashes if c.get("priority") == "critical")
    warnings = sum(1 for c in clashes if c.get("priority") in ("high", "warning"))
    ok = sum(1 for c in clashes if c.get("priority") == "info")
    return {
        "errors": errors,
        "warnings": warnings,
        "ok": ok,
        "total_clashes": len(clashes),
        "critical": errors,
        "non_critical": warnings + ok,
    }


def _analysis_mode_from_env() -> str:
    smoke = os.getenv("COORDINATION_SMOKE_MODE", "").lower() in ("1", "true", "yes")
    return "smoke" if smoke else "real"


def _ai_insight_from_context(context: dict[str, Any] | None, incident_count: int) -> str:
    if not context:
        if incident_count == 0:
            return (
                "No se detectaron incidencias primarias de coordinación en esta corrida. "
                "Revise que los planos comparables estén cargados y alineados."
            )
        return f"Se detectaron {incident_count} incidencias primarias. Revise los conflictos listados."

    for key in ("executive_summary", "summary", "overview", "headline"):
        val = context.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    stats = context.get("statistics") or context.get("stats") or {}
    if isinstance(stats, dict) and stats:
        parts = [f"{k}: {v}" for k, v in list(stats.items())[:5]]
        return "Resumen técnico: " + "; ".join(parts)

    return f"Análisis completado con {incident_count} incidencias primarias."


def _geometry_audit_from_context(context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(context, dict):
        return None
    hybrid = context.get("hybrid_geometry")
    if not isinstance(hybrid, dict):
        return None
    audit = hybrid.get("audit")
    if not isinstance(audit, dict):
        return None
    status = str(audit.get("status") or "").strip().lower()
    if not status:
        return None
    gate = context.get("hybrid_geometry_audit_gate")
    return {
        "status": status,
        "summary": audit.get("summary") if isinstance(audit.get("summary"), dict) else {},
        "gate": gate if isinstance(gate, dict) else {},
    }


def map_to_structural_analysis_report(
    *,
    run_status: str,
    project_name: str,
    profile_slug: str,
    primary_incidents: dict[str, Any],
    coordination_context: dict[str, Any] | None,
    analyzed_documents: list[dict[str, Any]],
    analysis_mode: str | None = None,
) -> dict[str, Any]:
    incidents = primary_incidents.get("incidents") or []
    if not isinstance(incidents, list):
        incidents = []

    clashes: list[dict[str, Any]] = []
    for idx, inc in enumerate(incidents):
        if not isinstance(inc, dict):
            continue
        iid = str(inc.get("incident_id") or f"clash-{idx + 1}")
        priority = _priority_from_incident(inc)
        rep = inc.get("representative_conflict") or {}
        geo_sources = rep.get("geometry_sources") or inc.get("geometry_sources") or []
        if isinstance(geo_sources, (list, tuple)):
            geo_label = " / ".join(str(s) for s in geo_sources if s)
        else:
            geo_label = str(geo_sources) if geo_sources else ""
        confidence = str(rep.get("confidence") or inc.get("confidence") or "")
        clashes.append(
            {
                "id": iid,
                "title": _title_from_incident(inc),
                "description": _description_from_incident(inc),
                "priority": priority,
                "location_label": str(inc.get("level_id") or None) or None,
                "disciplines": _disciplines_from_incident(inc),
                "thumbnail_url": None,
                "confidence": confidence or None,
                "geometry_sources": geo_label or None,
            }
        )

    summary = _summary_from_clashes(clashes, len(analyzed_documents))
    incident_count = int(primary_incidents.get("incident_count") or len(clashes))

    return {
        "run_status": run_status,
        "analysis_mode": analysis_mode or _analysis_mode_from_env(),
        "title": f"Informe de coordinación — {project_name}",
        "subtitle": f"{project_name} · {incident_count} incidencia(s) primaria(s)",
        "summary": summary,
        "clashes": clashes,
        "clash_relationships": [],
        "analyzed_documents": analyzed_documents,
        "geometry_audit": _geometry_audit_from_context(coordination_context),
        "ai_insight": _ai_insight_from_context(coordination_context, incident_count),
        "zoning_rows": [],
        "footer_status_message": (
            f"Última corrida: {primary_incidents.get('generated_at', '—')} · "
            f"{len(analyzed_documents)} documento(s) analizado(s)"
        ),
    }


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
