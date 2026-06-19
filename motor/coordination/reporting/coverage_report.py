"""Coverage and exclusion telemetry for a coordination pipeline run.

Answers the full Section 25 checklist from the requirements document:
  - How many DWG were analysed?
  - How many pairs were scheduled / blocked?
  - How many entities were extracted / suppressed / reached primary?
  - Why were entities suppressed?
  - What tolerances were used?
  - What alignments were applied?
  - Which layers generated the most signal?
  - Which layers were ignored?
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def build_coverage_report(
    *,
    candidate_audits: list[Any],
    profiled_payloads: dict[str, dict[str, Any]],
    pair_schedule: list[Any],
    all_elements: list[Any],
    suppressed_elements: list[Any],
    primary_conflicts: list[Any],
    role_suppressed_count: int = 0,
    run_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the coverage and exclusion telemetry block for one pipeline run.

    All parameters are the objects already available in run_clash_pipeline().
    Returns a JSON-serialisable dict — also written to coverage_report.json.
    """
    # ------------------------------------------------------------------
    # Files section
    # ------------------------------------------------------------------
    file_rows: list[dict[str, Any]] = []
    for audit in candidate_audits:
        rel_path = str(getattr(audit, "rel_path", ""))
        profiled = profiled_payloads.get(rel_path, {})
        profile = profiled.get("profile") or {}
        cache_hit = bool(profiled.get("cache_hit", False))

        raw_total = int(getattr(audit, "raw_entity_count", 0) or profile.get("raw_entity_count") or 0)
        raw_primary = int(
            getattr(audit, "raw_primary_candidate_count", 0)
            or profile.get("raw_primary_candidate_count")
            or 0
        )
        raw_annotation = int(
            getattr(audit, "raw_annotation_count", 0)
            or profile.get("raw_annotation_count")
            or 0
        )
        raw_layers = list(profile.get("raw_layers_detected") or [])
        dom_types = list(getattr(audit, "dominant_entity_types", []) or profile.get("dominant_entity_types") or [])

        file_rows.append({
            "rel_path": rel_path,
            "file_name": str(getattr(audit, "file_name", "")),
            "discipline": str(getattr(audit, "discipline", "")),
            "level_id": str(getattr(audit, "level_id", "")),
            "audit_status": str(getattr(audit, "audit_status", "")),
            "detail_only": bool(getattr(audit, "detail_only", False)),
            "coordinate_band": getattr(audit, "coordinate_band", None),
            "accore_cache_hit": cache_hit,
            "entity_count_total": raw_total,
            "entity_count_primary": raw_primary,
            "entity_count_annotation": raw_annotation,
            "entity_count_suppressed": max(raw_total - raw_primary - raw_annotation, 0),
            "dominant_entity_types": dom_types,
            "raw_layers_detected": raw_layers,
        })

    # ------------------------------------------------------------------
    # Pair schedule section
    # ------------------------------------------------------------------
    scheduled_count = 0
    blocked_by_reason: Counter[str] = Counter()
    for item in pair_schedule:
        if getattr(item, "scheduled", False):
            scheduled_count += 1
        else:
            reason = str(getattr(item, "block_reason", None) or "unknown")
            blocked_by_reason[reason] += 1

    pair_section: dict[str, Any] = {
        "total_pairs_evaluated": len(pair_schedule),
        "scheduled": scheduled_count,
        "blocked": len(pair_schedule) - scheduled_count,
        "blocked_by_reason": dict(sorted(blocked_by_reason.items())),
    }

    # ------------------------------------------------------------------
    # Entity section
    # ------------------------------------------------------------------
    total_extracted = len(all_elements)
    total_suppressed = len(suppressed_elements)

    suppression_reasons: Counter[str] = Counter()
    for element in suppressed_elements:
        reason = str(
            element.metadata.get("suppression_reason")
            or element.metadata.get("geometry_role")
            or "unknown"
        ) if hasattr(element, "metadata") else "unknown"
        suppression_reasons[reason] += 1

    # Layer signal: count elements per layer
    layer_signal: Counter[str] = Counter()
    layer_suppressed: Counter[str] = Counter()
    for element in all_elements:
        layer = str(getattr(element, "layer", None) or element.metadata.get("layer") or "unknown") if hasattr(element, "metadata") else str(getattr(element, "layer", "unknown"))
        layer_signal[layer] += 1
    for element in suppressed_elements:
        layer = str(getattr(element, "layer", None) or element.metadata.get("layer") or "unknown") if hasattr(element, "metadata") else str(getattr(element, "layer", "unknown"))
        layer_suppressed[layer] += 1

    entity_section: dict[str, Any] = {
        "total_extracted": total_extracted,
        "total_primary": total_extracted - total_suppressed,
        "total_suppressed": total_suppressed,
        "suppressed_by_reason": dict(sorted(suppression_reasons.items())),
    }

    # ------------------------------------------------------------------
    # Clash section
    # ------------------------------------------------------------------
    clash_section: dict[str, Any] = {
        "conflicts_detected": len(primary_conflicts),
        "conflicts_role_suppressed": role_suppressed_count,
        "conflicts_passed": len(primary_conflicts),
    }

    # ------------------------------------------------------------------
    # Layer section (top 20 signal / top 20 suppressed)
    # ------------------------------------------------------------------
    layer_section: dict[str, Any] = {
        "top_signal_layers": [
            {"layer": layer, "count": count}
            for layer, count in layer_signal.most_common(20)
        ],
        "top_suppressed_layers": [
            {"layer": layer, "count": count}
            for layer, count in layer_suppressed.most_common(20)
        ],
    }

    return {
        "schema_version": "coverage_report.v1",
        "files": file_rows,
        "pairs": pair_section,
        "entities": entity_section,
        "clashes": clash_section,
        "layers": layer_section,
        "tolerances": run_config or {},
    }


def render_coverage_report_markdown(report: dict[str, Any]) -> str:
    """Render the coverage report as human-readable Markdown."""
    lines: list[str] = ["# Coverage & Exclusion Report", ""]

    pairs = report.get("pairs") or {}
    entities = report.get("entities") or {}
    clashes = report.get("clashes") or {}
    tolerances = report.get("tolerances") or {}

    lines += [
        "## Resumen",
        "",
        f"| Métrica | Valor |",
        f"| --- | ---: |",
        f"| Archivos evaluados | {len(report.get('files') or [])} |",
        f"| Pares evaluados | {pairs.get('total_pairs_evaluated', 0)} |",
        f"| Pares programados | {pairs.get('scheduled', 0)} |",
        f"| Pares bloqueados | {pairs.get('blocked', 0)} |",
        f"| Entidades extraídas | {entities.get('total_extracted', 0)} |",
        f"| Entidades primary | {entities.get('total_primary', 0)} |",
        f"| Entidades suprimidas | {entities.get('total_suppressed', 0)} |",
        f"| Conflictos detectados | {clashes.get('conflicts_detected', 0)} |",
        f"| Conflictos suprimidos (rol) | {clashes.get('conflicts_role_suppressed', 0)} |",
        "",
    ]

    # Files table
    lines += [
        "## Archivos",
        "",
        "| Archivo | Disciplina | Nivel | Estado | Cache | Total | Primary | Suprimidas |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in report.get("files") or []:
        cache_str = "hit" if row.get("accore_cache_hit") else "miss"
        lines.append(
            "| {f} | {d} | {l} | `{s}` | {c} | {tot} | {pri} | {sup} |".format(
                f=row.get("file_name", ""),
                d=row.get("discipline", ""),
                l=row.get("level_id", ""),
                s=row.get("audit_status", ""),
                c=cache_str,
                tot=row.get("entity_count_total", 0),
                pri=row.get("entity_count_primary", 0),
                sup=row.get("entity_count_suppressed", 0),
            )
        )

    # Blocked pairs
    blocked_by_reason = pairs.get("blocked_by_reason") or {}
    if blocked_by_reason:
        lines += [
            "",
            "## Pares bloqueados — razón",
            "",
            "| Razón | Count |",
            "| --- | ---: |",
        ]
        for reason, count in sorted(blocked_by_reason.items(), key=lambda kv: -kv[1]):
            lines.append(f"| `{reason}` | {count} |")

    # Suppressed entities
    suppressed_by_reason = entities.get("suppressed_by_reason") or {}
    if suppressed_by_reason:
        lines += [
            "",
            "## Entidades suprimidas — razón",
            "",
            "| Razón | Count |",
            "| --- | ---: |",
        ]
        for reason, count in sorted(suppressed_by_reason.items(), key=lambda kv: -kv[1]):
            lines.append(f"| `{reason}` | {count} |")

    # Top signal layers
    top_layers = (report.get("layers") or {}).get("top_signal_layers") or []
    if top_layers:
        lines += ["", "## Capas con más señal (top 20)", "", "| Capa | Entidades |", "| --- | ---: |"]
        for entry in top_layers:
            lines.append(f"| {entry['layer']} | {entry['count']} |")

    # Tolerances
    if tolerances:
        lines += ["", "## Tolerancias usadas", ""]
        for key, value in tolerances.items():
            lines.append(f"- `{key}`: {value}")

    return "\n".join(lines) + "\n"
