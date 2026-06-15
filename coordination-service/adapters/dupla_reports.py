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


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _esc(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _render_placeholder_tile_svg(incident: dict[str, Any], *, annotated: bool) -> str:
    """Render a plan-view SVG tile from incident bounds/centroid (smoke mode).

    Mirrors the layout of the real Dupla annotated tiles closely enough for the
    UI preview: white canvas, intersection bbox for each DWG, the clash polygon
    highlighted, and a centroid marker. When ``annotated`` is True, a legend with
    incident metadata is overlaid.
    """
    rep = incident.get("representative_conflict") or {}
    bounds = incident.get("plan_bounds_mm") or rep.get("plan_intersection_bounds_mm") or []
    centroid = incident.get("plan_centroid_mm") or rep.get("plan_intersection_centroid_mm") or []

    if len(bounds) == 4:
        minx, miny, maxx, maxy = (_f(b) for b in bounds)
    else:
        minx, miny, maxx, maxy = 0.0, 0.0, 1000.0, 1000.0
    if maxx <= minx:
        maxx = minx + 1000.0
    if maxy <= miny:
        maxy = miny + 1000.0
    if len(centroid) == 2:
        cx, cy = _f(centroid[0]), _f(centroid[1])
    else:
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    # Smoke fixtures can carry a centroid inconsistent with the bbox; fall back
    # to the bbox center so the marker stays inside the conflict zone.
    if not (minx <= cx <= maxx and miny <= cy <= maxy):
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0

    width, height = 800.0, 586.0
    margin = 70.0
    world_w = maxx - minx
    world_h = maxy - miny
    # Pad the world box so the clash polygon does not touch the canvas edges.
    pad = max(world_w, world_h) * 0.45
    wx0, wy0, wx1, wy1 = minx - pad, miny - pad, maxx + pad, maxy + pad
    scale = min((width - 2 * margin) / (wx1 - wx0), (height - 2 * margin) / (wy1 - wy0))

    def mx(x: float) -> float:
        return margin + (x - wx0) * scale

    def my(y: float) -> float:
        # SVG y grows downward; world y grows upward.
        return height - (margin + (y - wy0) * scale)

    def rect_points(x0: float, y0: float, x1: float, y1: float) -> str:
        pts = [(mx(x0), my(y0)), (mx(x1), my(y0)), (mx(x1), my(y1)), (mx(x0), my(y1))]
        return " ".join(f"{px:.2f},{py:.2f}" for px, py in pts)

    # Two offset bounding boxes to represent each DWG element around the clash.
    off = max(world_w, world_h) * 0.18
    a_box = rect_points(minx - off, miny - off, maxx + off * 0.3, maxy + off * 0.3)
    b_box = rect_points(minx - off * 0.3, miny - off * 0.3, maxx + off, maxy + off)
    clash_box = rect_points(minx, miny, maxx, maxy)
    ccx, ccy = mx(cx), my(cy)

    disc_a = _esc(rep.get("discipline_a") or "DWG A")
    disc_b = _esc(rep.get("discipline_b") or "DWG B")
    incident_id = _esc(incident.get("incident_id") or "incident")
    level_id = _esc(incident.get("level_id") or "—")
    area = _f(rep.get("plan_intersection_area_mm2"))
    depth = rep.get("overlap_depth_z_mm")
    depth_txt = f"{_f(depth):.0f} mm" if depth is not None else "—"

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}">',
        f'<rect width="100%" height="100%" fill="#FFFFFF"/>',
    ]

    # Light grid for spatial reference.
    grid = ['<g stroke="#E5E7EB" stroke-width="0.6">']
    for i in range(1, 8):
        gx = margin + (width - 2 * margin) * i / 8
        gy = margin + (height - 2 * margin) * i / 8
        grid.append(f'<line x1="{gx:.1f}" y1="{margin:.1f}" x2="{gx:.1f}" y2="{height - margin:.1f}"/>')
        grid.append(f'<line x1="{margin:.1f}" y1="{gy:.1f}" x2="{width - margin:.1f}" y2="{gy:.1f}"/>')
    grid.append("</g>")
    parts.extend(grid)

    # DWG A (blue) and DWG B (amber) footprints, clash polygon (red) on top.
    parts.append(f'<polygon points="{a_box}" fill="#3B82F622" stroke="#3B82F6" stroke-width="1.4"/>')
    parts.append(f'<polygon points="{b_box}" fill="#F59E0B22" stroke="#F59E0B" stroke-width="1.4"/>')
    parts.append(f'<polygon points="{clash_box}" fill="#EF444433" stroke="#EF4444" stroke-width="2.4"/>')
    # Centroid marker.
    parts.append(f'<circle cx="{ccx:.2f}" cy="{ccy:.2f}" r="5" fill="#EF4444"/>')
    parts.append(
        f'<line x1="{ccx - 11:.2f}" y1="{ccy:.2f}" x2="{ccx + 11:.2f}" y2="{ccy:.2f}" '
        f'stroke="#991B1B" stroke-width="1.2"/>'
    )
    parts.append(
        f'<line x1="{ccx:.2f}" y1="{ccy - 11:.2f}" x2="{ccx:.2f}" y2="{ccy + 11:.2f}" '
        f'stroke="#991B1B" stroke-width="1.2"/>'
    )

    if annotated:
        parts.append(
            '<g font-family="Helvetica, Arial, sans-serif">'
            f'<text x="16" y="28" font-size="15" font-weight="bold" fill="#111827">{incident_id}</text>'
            f'<text x="16" y="48" font-size="12" fill="#374151">Nivel {level_id} · '
            f'área {area:,.0f} mm² · solape {depth_txt}</text>'
            '</g>'
        )
        # Legend box bottom-left.
        ly = height - 64
        parts.append(
            f'<g font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#374151">'
            f'<rect x="14" y="{ly - 16:.0f}" width="14" height="10" fill="#3B82F622" stroke="#3B82F6"/>'
            f'<text x="34" y="{ly - 7:.0f}">{disc_a}</text>'
            f'<rect x="14" y="{ly + 2:.0f}" width="14" height="10" fill="#F59E0B22" stroke="#F59E0B"/>'
            f'<text x="34" y="{ly + 11:.0f}">{disc_b}</text>'
            f'<rect x="14" y="{ly + 20:.0f}" width="14" height="10" fill="#EF444433" stroke="#EF4444"/>'
            f'<text x="34" y="{ly + 29:.0f}">Zona de conflicto</text>'
            f'</g>'
        )
        parts.append(
            f'<text x="{width - 14:.0f}" y="{height - 14:.0f}" text-anchor="end" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="9" fill="#9CA3AF">'
            f'DUPLA · vista de planta (smoke)</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _write_smoke_tiles(output_dir: Path, primary_payload: dict[str, Any]) -> list[str]:
    """Generate placeholder plan-view tiles per incident for smoke runs."""
    tiles_dir = output_dir / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for inc in primary_payload.get("incidents") or []:
        if not isinstance(inc, dict):
            continue
        incident_id = str(inc.get("incident_id") or "").strip()
        if not incident_id:
            continue
        annotated_path = tiles_dir / f"{incident_id}_annotated.svg"
        plain_path = tiles_dir / f"{incident_id}.svg"
        annotated_path.write_text(_render_placeholder_tile_svg(inc, annotated=True), encoding="utf-8")
        plain_path.write_text(_render_placeholder_tile_svg(inc, annotated=False), encoding="utf-8")
        written.extend([str(annotated_path), str(plain_path)])
    return written


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

    tile_paths: list[str] = []
    if smoke_mode:
        # Smoke runs never reach the Dupla CAD pipeline, so no real tiles are
        # produced. Generate plan-view placeholders so the UI preview resolves.
        tile_paths = _write_smoke_tiles(output_dir, primary_payload)

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
            "tiles": tile_paths,
        },
    }
