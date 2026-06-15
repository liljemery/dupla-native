#!/usr/bin/env python3
"""Render a final run summary and a ChatGPT-ready prompt from a coordination run folder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Render coordination delivery pack from an existing run folder.")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--run-label", type=str, required=True, help="Label shown in final markdown files. Example: Analysis 06")
    parser.add_argument("--date-label", type=str, required=True, help="Date prefix for the generated markdown files. Example: 2026-05-02")
    parser.add_argument("--project-short-name", type=str, default="SERENA 18")
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    summary = _load_json(run_dir / "summary.json")
    readiness = _load_optional_json(run_dir / "comparison_readiness_report.json")
    audit = _load_optional_json(run_dir / "coordinate_audit.json")
    schedule = _load_optional_json(run_dir / "pair_schedule.json")
    context = _load_json(run_dir / "coordination_report_context.json")
    bot_context = _load_optional_json(run_dir / "analysis_bot_context.json")

    result_path = run_dir / f"{args.date_label}_{_slug(args.run_label)}_resultado.md"
    prompt_path = run_dir / f"{args.date_label}_{_slug(args.run_label)}_chatgpt_prompt.md"

    result_path.write_text(
        _render_result_markdown(
            run_label=args.run_label,
            date_label=args.date_label,
            project_short_name=args.project_short_name,
            run_dir=run_dir,
            summary=summary,
            readiness=readiness,
            audit=audit,
            schedule=schedule,
            context=context,
            bot_context=bot_context,
        ),
        encoding="utf-8",
    )
    prompt_path.write_text(
        _render_chatgpt_prompt_markdown(
            run_label=args.run_label,
            date_label=args.date_label,
            project_short_name=args.project_short_name,
            context=context,
            bot_context=bot_context,
            summary=summary,
        ),
        encoding="utf-8",
    )
    return 0


def _render_result_markdown(
    *,
    run_label: str,
    date_label: str,
    project_short_name: str,
    run_dir: Path,
    summary: dict[str, Any],
    readiness: dict[str, Any] | None,
    audit: dict[str, Any] | None,
    schedule: dict[str, Any] | None,
    context: dict[str, Any],
    bot_context: dict[str, Any] | None,
) -> str:
    counts = context.get("counts") or {}
    pair_rollups = context.get("pair_rollups") or []
    defendable = context.get("defendable_incidents") or []
    validation = context.get("validation_incidents") or []
    reader_sections = context.get("reader_sections") or {}
    noise = context.get("noise_summary") or {}
    comparable_issue_keys = (readiness or {}).get("comparable_issue_keys") or []
    audit_statuses = {}
    for item in (audit or {}).get("audits") or []:
        key = str(item.get("audit_status") or "unknown")
        audit_statuses[key] = audit_statuses.get(key, 0) + 1

    lines = [
        f"# {run_label} - {project_short_name}",
        "",
        f"- Fecha: `{date_label}`",
        f"- Perfil: `{summary.get('analysis_profile') or 'fast_compare'}`",
        f"- Estado: `{summary.get('status') or 'unknown'}`",
        f"- Carpeta: `{run_dir.as_posix()}`",
        "",
        "## Resultado ejecutivo",
        f"- `{counts.get('selected_candidates', 0)}` archivos seleccionados",
        f"- `{counts.get('scheduled_pairs', 0)}` pares programados",
        f"- `{counts.get('elements', 0)}` elementos 2.5D",
        f"- `{counts.get('primary_incidents', 0)}` incidencias primarias",
        f"- `{len(defendable)}` hallazgos defendibles",
        f"- `{len(validation)}` incidencias que requieren validacion manual",
        f"- `{counts.get('debug_conflicts', 0)}` conflictos debug",
        f"- `{counts.get('suppressed_elements', 0)}` elementos suprimidos",
        "",
        "## Lectura corta",
        f"- Readiness automatico comparable: `{'si' if comparable_issue_keys else 'no'}`.",
        f"- Mix de audit: `{_counter_label(audit_statuses) or 'none'}`.",
        f"- Mix de confianza del primario: `{_counter_label(context.get('confidence_mix') or {}) or 'none'}`.",
        f"- Mix de severidad del primario: `{_counter_label(context.get('severity_mix') or {}) or 'none'}`.",
        "",
        "## Pares principales",
    ]
    for pair in pair_rollups:
        lines.append(
            f"- `{pair['pair_label']}`"
            f"\n  incidencias: `{pair['incident_count']}`"
            f"\n  miembros: `{pair['member_count']}`"
            f"\n  prioridad dominante: `{pair['top_priority']}`"
            f"\n  confianza: `{pair['confidence_mix_label']}`"
        )

    lines.extend(
        [
            "",
            "## Hallazgos defendibles mas fuertes",
        ]
    )
    for item in defendable[:8]:
        lines.append(
            f"- `{item['incident_id']}` | `{item['priority']}` | `{item['severity']}` | `{item['report_confidence']}`"
            f"\n  nivel: `{item['level_id']}`"
            f"\n  par: `{item['pair_label']}`"
            f"\n  ubicacion: `{item['location_short']}`"
            f"\n  accion: {item['recommended_action']}"
        )
    if not defendable:
        lines.append("- No hubo hallazgos defendibles en esta corrida.")

    lines.extend(
        [
            "",
            "## Vista por perfil",
            f"- Arquitectura: `{reader_sections.get('arquitectura', {}).get('coverage', 'not_in_run')}`",
            f"- Electrico: `{reader_sections.get('electrico', {}).get('coverage', 'not_in_run')}`",
            f"- Sanitario: `{reader_sections.get('sanitario', {}).get('coverage', 'not_in_run')}`",
            "",
            "## Ruido tecnico separado",
            f"- Debug conflicts: `{noise.get('debug_conflict_count', 0)}`",
            f"- Suppression reasons: `{noise.get('suppression_reasons_label', 'none')}`",
            f"- Blocked pairs: `{noise.get('blocked_pair_count', 0)}`",
            f"- Block reasons: `{noise.get('blocked_reasons_label', 'none')}`",
            f"- Hotspots agrupados: `{noise.get('hotspot_incident_count', 0)}`",
            "",
            "## Archivos principales",
            f"- Resumen: [summary.json]({run_dir.as_posix()}/summary.json:1)",
            f"- Informe tecnico: [technical_coordination_report.md]({run_dir.as_posix()}/technical_coordination_report.md:1)",
            f"- Contexto bot: [analysis_bot_context.json]({run_dir.as_posix()}/analysis_bot_context.json:1)",
            f"- Reporte humano: [coordination_report_human.md]({run_dir.as_posix()}/coordination_report_human.md:1)",
            f"- Registro primario: [primary_incidents.md]({run_dir.as_posix()}/primary_incidents.md:1)",
            f"- Audit: [coordinate_audit.md]({run_dir.as_posix()}/coordinate_audit.md:1)",
            f"- Hotspots: [hotspot_incidents.md]({run_dir.as_posix()}/hotspot_incidents.md:1)",
            f"- Prompt ChatGPT: [{prompt_path_name(date_label, run_label)}]({run_dir.as_posix()}/{prompt_path_name(date_label, run_label)}:1)",
        ]
    )
    if (summary.get("elements_by_dwg_json") or "").strip():
        lines.append(
            f"- Elementos por DWG: [elements_by_dwg.json]({run_dir.as_posix()}/elements_by_dwg.json:1)"
        )
    if (summary.get("clash_element_links_json") or "").strip():
        lines.append(
            f"- Links clash-element: [clash_element_links.json]({run_dir.as_posix()}/clash_element_links.json:1)"
        )
    lines.append("")
    return "\n".join(lines)


def _render_chatgpt_prompt_markdown(
    *,
    run_label: str,
    date_label: str,
    project_short_name: str,
    context: dict[str, Any],
    bot_context: dict[str, Any] | None,
    summary: dict[str, Any],
) -> str:
    counts = context.get("counts") or {}
    defendable = context.get("defendable_incidents") or []
    validation = context.get("validation_incidents") or []
    pair_rollups = context.get("pair_rollups") or []
    noise = context.get("noise_summary") or {}
    bot_summary = (bot_context or {}).get("run_summary") or {}

    lines = [
        f"# Prompt para ChatGPT - {run_label} - {project_short_name}",
        "",
        "Copia y pega el siguiente prompt en ChatGPT para que te devuelva un informe mas humano, legible y orientado a revision interdisciplinaria.",
        "",
        "```text",
        "Actua como un coordinador tecnico senior de proyectos AEC.",
        "Quiero que redactes un informe profesional, natural y humano, en espanol neutro, a partir de los datos estructurados de una corrida de coordinacion 2.5D.",
        "",
        "Objetivo del informe:",
        "- que sea facil de leer por arquitectura, estructura y, cuando aplique, especialidades MEP",
        "- que separe claramente hallazgos defendibles vs ruido tecnico",
        "- que priorice accionabilidad y lectura ejecutiva antes que detalle crudo",
        "- que no suene a salida automatica ni a log tecnico",
        "",
        "Reglas de redaccion:",
        "- no inventes datos, recintos, ejes, habitaciones ni decisiones que no aparezcan en la informacion",
        "- cuando la confianza sea baja o el caso requiera validacion manual, dilo explicitamente",
        "- no presentes hotspots ni debug como si fueran clashes finales",
        "- usa lenguaje profesional y claro, no marketing, no exageraciones",
        "- si hay hallazgos defendibles, abre con ellos",
        "- si no hay cobertura real para electrico o sanitario, dilo en vez de forzar una lectura",
        "",
        "Estructura requerida:",
        "1. Resumen ejecutivo",
        "2. Hallazgos defendibles prioritarios",
        "3. Hallazgos que requieren validacion manual",
        "4. Lectura por perfil de revisor",
        "5. Ruido tecnico y limites del run",
        "6. Recomendaciones para la siguiente ronda de coordinacion",
        "",
        "Datos del run:",
        f"- run_label: {run_label}",
        f"- generated_at: {summary.get('generated_at') or date_label}",
        f"- analysis_profile: {summary.get('analysis_profile') or 'fast_compare'}",
        f"- status: {summary.get('status') or 'unknown'}",
        f"- selected_candidates: {bot_summary.get('selected_candidates', counts.get('selected_candidates', 0))}",
        f"- audited_files: {bot_summary.get('audited_files', counts.get('audited_files', 0))}",
        f"- eligible_files: {bot_summary.get('eligible_files', counts.get('eligible_files', 0))}",
        f"- scheduled_pairs: {bot_summary.get('scheduled_pairs', counts.get('scheduled_pairs', 0))}",
        f"- elements: {bot_summary.get('elements', counts.get('elements', 0))}",
        f"- primary_incidents: {bot_summary.get('primary_incidents', counts.get('primary_incidents', 0))}",
        f"- defendable_incidents: {bot_summary.get('defendable_incidents', len(defendable))}",
        f"- validation_incidents: {bot_summary.get('validation_incidents', len(validation))}",
        f"- debug_conflicts: {bot_summary.get('debug_conflicts', counts.get('debug_conflicts', 0))}",
        f"- suppressed_elements: {bot_summary.get('suppressed_elements', counts.get('suppressed_elements', 0))}",
        f"- confidence_mix: {_counter_label(context.get('confidence_mix') or {}) or 'none'}",
        f"- severity_mix: {_counter_label(context.get('severity_mix') or {}) or 'none'}",
        "",
        "Contexto estructurado adicional:",
        "- Usa `analysis_bot_context.json` como fuente factual primaria para conteos, cobertura, pares y limitaciones.",
        "- Si el readiness documental contradice el run final, explica que el coordinate audit promovio la comparabilidad real.",
        "- No conviertas layers en nombres de elementos constructivos reales si no existe mapeo semantico.",
        "- Solo usa nombres de elementos si el contexto estructurado indica `mapping_confidence` medium o high.",
        "",
        "Resumen por pares:",
    ]
    for pair in pair_rollups[:8]:
        lines.append(
            f"- {pair['pair_label']} | incidents={pair['incident_count']} | members={pair['member_count']} | "
            f"top_priority={pair['top_priority']} | confidence_mix={pair['confidence_mix_label']} | severity_mix={pair['severity_mix_label']}"
        )

    lines.extend(
        [
            "",
            "Hallazgos defendibles top:",
        ]
    )
    for item in defendable[:12]:
        lines.append(
            f"- {item['incident_id']} | priority={item['priority']} | severity={item['severity']} | confidence={item['report_confidence']} | "
            f"level={item['level_id']} | pair={item['pair_label']} | location={item['location_short']} | "
            f"layers={item['layer_pair']} | action={item['recommended_action']}"
        )

    lines.extend(
        [
            "",
            "Casos con validacion manual top:",
        ]
    )
    for item in validation[:10]:
        lines.append(
            f"- {item['incident_id']} | reason={item['validation_reason']} | level={item['level_id']} | "
            f"pair={item['pair_label']} | layers={item['layer_pair']}"
        )

    lines.extend(
        [
            "",
            "Ruido tecnico y limites:",
            f"- noise_debug_conflicts={noise.get('debug_conflict_count', 0)}",
            f"- noise_suppression_reasons={noise.get('suppression_reasons_label', 'none')}",
            f"- noise_audit_status={noise.get('audit_status_label', 'none')}",
            f"- noise_blocked_pairs={noise.get('blocked_pair_count', 0)}",
            f"- noise_block_reasons={noise.get('blocked_reasons_label', 'none')}",
            f"- hotspots_grouped={noise.get('hotspot_incident_count', 0)}",
            "",
            "Devuelveme solo el informe final en markdown, no expliques tu proceso.",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def prompt_path_name(date_label: str, run_label: str) -> str:
    return f"{date_label}_{_slug(run_label)}_chatgpt_prompt.md"


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _counter_label(counter: dict[str, int]) -> str:
    if not counter:
        return ""
    ordered = sorted(counter.items(), key=lambda item: (-int(item[1]), item[0]))
    return ", ".join(f"{label}={count}" for label, count in ordered)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
