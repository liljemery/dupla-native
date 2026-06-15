#!/usr/bin/env python3
"""Render a consolidated markdown summary and ChatGPT prompt for multiple coordination runs."""

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
    parser = argparse.ArgumentParser(description="Render a consolidated coordination portfolio pack.")
    parser.add_argument("--portfolio-dir", type=Path, required=True)
    parser.add_argument("--portfolio-label", type=str, required=True)
    parser.add_argument("--date-label", type=str, required=True)
    parser.add_argument("--project-short-name", type=str, default="SERENA 18")
    parser.add_argument("--run-dirs", nargs="+", required=True, help="Run subdirectories relative to portfolio-dir.")
    args = parser.parse_args()

    portfolio_dir = args.portfolio_dir.resolve()
    runs = [_load_run(portfolio_dir / run_dir) for run_dir in args.run_dirs]

    result_path = portfolio_dir / f"{args.date_label}_{_slug(args.portfolio_label)}_resultado.md"
    prompt_path = portfolio_dir / f"{args.date_label}_{_slug(args.portfolio_label)}_chatgpt_prompt.md"
    readme_path = portfolio_dir / "README.md"

    result_path.write_text(
        _render_portfolio_result(
            portfolio_label=args.portfolio_label,
            date_label=args.date_label,
            project_short_name=args.project_short_name,
            runs=runs,
        ),
        encoding="utf-8",
    )
    prompt_path.write_text(
        _render_portfolio_prompt(
            portfolio_label=args.portfolio_label,
            date_label=args.date_label,
            project_short_name=args.project_short_name,
            runs=runs,
        ),
        encoding="utf-8",
    )
    readme_path.write_text(
        _render_portfolio_readme(
            portfolio_label=args.portfolio_label,
            project_short_name=args.project_short_name,
            portfolio_dir=portfolio_dir,
            runs=runs,
            result_path=result_path,
            prompt_path=prompt_path,
        ),
        encoding="utf-8",
    )
    return 0


def _load_run(run_dir: Path) -> dict[str, Any]:
    summary = _load_json(run_dir / "summary.json")
    context = _load_json(run_dir / "coordination_report_context.json")
    return {
        "run_dir": run_dir,
        "name": run_dir.name,
        "summary": summary,
        "context": context,
    }


def _render_portfolio_result(
    *,
    portfolio_label: str,
    date_label: str,
    project_short_name: str,
    runs: list[dict[str, Any]],
) -> str:
    counts = _portfolio_counts(runs)
    lines = [
        f"# {portfolio_label} - {project_short_name}",
        "",
        f"- Fecha: `{date_label}`",
        f"- Proyecto: `{project_short_name}`",
        f"- Corridas incluidas: `{len(runs)}`",
        "",
        "## Resumen ejecutivo",
        f"- `{counts['scheduled_pairs']}` pares programados en total",
        f"- `{counts['primary_incidents']}` incidencias primarias agrupadas",
        f"- `{counts['defendable_incidents']}` hallazgos defendibles",
        f"- `{counts['validation_incidents']}` casos con validacion manual",
        f"- `{counts['debug_conflicts']}` debug conflicts",
        f"- `{counts['suppressed_elements']}` elementos suprimidos",
        "",
        "## Corridas incluidas",
    ]
    for run in runs:
        summary = run["summary"]
        context = run["context"]
        lines.append(
            f"- `{run['name']}`"
            f"\n  estado: `{summary.get('status')}`"
            f"\n  pares programados: `{summary.get('scheduled_pair_count', 0)}`"
            f"\n  incidencias primarias: `{summary.get('primary_incident_count', 0)}`"
            f"\n  defendibles: `{len(context.get('defendable_incidents') or [])}`"
            f"\n  ruta: [{run['name']}]({run['run_dir'].as_posix()}:1)"
        )

    lines.extend(
        [
            "",
            "## Hallazgos mas fuertes por corrida",
        ]
    )
    for run in runs:
        context = run["context"]
        defendable = context.get("defendable_incidents") or []
        if defendable:
            item = defendable[0]
            lines.append(
                f"- `{run['name']}` -> `{item['incident_id']}` | `{item['priority']}` | `{item['severity']}` | `{item['report_confidence']}`"
                f"\n  par: `{item['pair_label']}`"
                f"\n  nivel: `{item['level_id']}`"
                f"\n  ubicacion: `{item['location_short']}`"
            )
        else:
            lines.append(f"- `{run['name']}` -> sin hallazgos defendibles en esta corrida.")

    lines.extend(
        [
            "",
            "## Archivos finales",
            f"- Resumen consolidado: [README.md]({runs[0]['run_dir'].parent.as_posix()}/README.md:1)",
            f"- Resultado portfolio: [{date_label}_{_slug(portfolio_label)}_resultado.md]({runs[0]['run_dir'].parent.as_posix()}/{date_label}_{_slug(portfolio_label)}_resultado.md:1)",
            f"- Prompt GPT: [{date_label}_{_slug(portfolio_label)}_chatgpt_prompt.md]({runs[0]['run_dir'].parent.as_posix()}/{date_label}_{_slug(portfolio_label)}_chatgpt_prompt.md:1)",
        ]
    )
    lines.append("")
    return "\n".join(lines)


def _render_portfolio_prompt(
    *,
    portfolio_label: str,
    date_label: str,
    project_short_name: str,
    runs: list[dict[str, Any]],
) -> str:
    counts = _portfolio_counts(runs)
    lines = [
        f"# Prompt para ChatGPT - {portfolio_label} - {project_short_name}",
        "",
        "Copia y pega este prompt en ChatGPT para obtener un informe portfolio mas humano, ejecutivo y util para revision interdisciplinaria.",
        "",
        "```text",
        "Actua como un coordinador tecnico senior de proyectos AEC.",
        "Quiero que redactes un informe consolidado, humano y profesional, en espanol neutro, a partir de varias corridas de coordinacion 2.5D del mismo proyecto.",
        "",
        "Objetivo del informe:",
        "- resumir el estado general de coordinacion por alcance o nivel",
        "- separar claramente hallazgos defendibles vs ruido tecnico",
        "- identificar que corridas ya son presentables y cuales siguen en validacion",
        "- proponer un orden de revision interdisciplinaria",
        "",
        "Reglas:",
        "- no inventes informacion no presente en los datos",
        "- no conviertas debug o hotspots en hallazgos finales",
        "- cuando una corrida no tenga hallazgos defendibles, dilo claramente",
        "- si una disciplina no tiene cobertura real, dilo",
        "- escribe como un informe tecnico para equipo real, no como log ni como salida automatica",
        "",
        "Estructura requerida:",
        "1. Resumen ejecutivo consolidado",
        "2. Corridas ya presentables",
        "3. Corridas que siguen en validacion",
        "4. Hallazgos defendibles prioritarios por alcance",
        "5. Lectura por perfiles de revisor",
        "6. Limites tecnicos y ruido detectado",
        "7. Recomendaciones para la siguiente ronda",
        "",
        "Datos portfolio:",
        f"- portfolio_label: {portfolio_label}",
        f"- generated_at: {date_label}",
        f"- run_count: {len(runs)}",
        f"- scheduled_pairs_total: {counts['scheduled_pairs']}",
        f"- primary_incidents_total: {counts['primary_incidents']}",
        f"- defendable_incidents_total: {counts['defendable_incidents']}",
        f"- validation_incidents_total: {counts['validation_incidents']}",
        f"- debug_conflicts_total: {counts['debug_conflicts']}",
        f"- suppressed_elements_total: {counts['suppressed_elements']}",
        "",
        "Corridas incluidas:",
    ]
    for run in runs:
        summary = run["summary"]
        context = run["context"]
        lines.append(
            f"- {run['name']} | status={summary.get('status')} | scheduled_pairs={summary.get('scheduled_pair_count', 0)} | "
            f"primary_incidents={summary.get('primary_incident_count', 0)} | defendable_incidents={len(context.get('defendable_incidents') or [])} | "
            f"validation_incidents={len(context.get('validation_incidents') or [])} | debug_conflicts={summary.get('debug_conflict_count', 0)}"
        )
        for pair in (context.get("pair_rollups") or [])[:4]:
            lines.append(
                f"  - pair={pair['pair_label']} | incidents={pair['incident_count']} | members={pair['member_count']} | "
                f"top_priority={pair['top_priority']} | confidence_mix={pair['confidence_mix_label']} | severity_mix={pair['severity_mix_label']}"
            )
        for item in (context.get("defendable_incidents") or [])[:4]:
            lines.append(
                f"  - defendable={item['incident_id']} | priority={item['priority']} | severity={item['severity']} | "
                f"confidence={item['report_confidence']} | level={item['level_id']} | pair={item['pair_label']} | location={item['location_short']} | action={item['recommended_action']}"
            )
        for item in (context.get("validation_incidents") or [])[:3]:
            lines.append(
                f"  - validation={item['incident_id']} | reason={item['validation_reason']} | level={item['level_id']} | pair={item['pair_label']}"
            )

    lines.extend(
        [
            "",
            "Devuelveme solo el informe final en markdown, sin explicar tu proceso.",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _render_portfolio_readme(
    *,
    portfolio_label: str,
    project_short_name: str,
    portfolio_dir: Path,
    runs: list[dict[str, Any]],
    result_path: Path,
    prompt_path: Path,
) -> str:
    lines = [
        f"# {project_short_name} - {portfolio_label}",
        "",
        "## Corridas",
    ]
    for run in runs:
        lines.append(f"- `{run['name']}`")
        lines.append(f"  - carpeta: [{run['name']}]({run['run_dir'].as_posix()}:1)")
        lines.append(
            f"  - resumen: [summary.json]({run['run_dir'].as_posix()}/summary.json:1)"
        )
        lines.append(
            f"  - informe tecnico: [technical_coordination_report.md]({run['run_dir'].as_posix()}/technical_coordination_report.md:1)"
        )
        result_candidates = sorted(run["run_dir"].glob("*_resultado.md"))
        if result_candidates:
            result_file = result_candidates[0]
            lines.append(f"  - resultado: [{result_file.name}]({result_file.as_posix()}:1)")
    lines.extend(
        [
            "",
            "## Consolidados",
            f"- resultado consolidado: [{result_path.name}]({result_path.as_posix()}:1)",
            f"- prompt GPT: [{prompt_path.name}]({prompt_path.as_posix()}:1)",
        ]
    )
    lines.append("")
    return "\n".join(lines)


def _portfolio_counts(runs: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "scheduled_pairs": 0,
        "primary_incidents": 0,
        "defendable_incidents": 0,
        "validation_incidents": 0,
        "debug_conflicts": 0,
        "suppressed_elements": 0,
    }
    for run in runs:
        summary = run["summary"]
        context = run["context"]
        counts["scheduled_pairs"] += int(summary.get("scheduled_pair_count") or 0)
        counts["primary_incidents"] += int(summary.get("primary_incident_count") or 0)
        counts["defendable_incidents"] += len(context.get("defendable_incidents") or [])
        counts["validation_incidents"] += len(context.get("validation_incidents") or [])
        counts["debug_conflicts"] += int(summary.get("debug_conflict_count") or 0)
        counts["suppressed_elements"] += int(summary.get("suppressed_element_count") or 0)
    return counts


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


if __name__ == "__main__":
    raise SystemExit(main())
