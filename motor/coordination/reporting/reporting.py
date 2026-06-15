"""Presentation helpers for reusable technical coordination reports."""

from __future__ import annotations

from collections import Counter, defaultdict
from html import escape
from pathlib import Path
import re
from typing import Any


def build_coordination_report_context(
    *,
    summary_payload: dict[str, Any],
    primary_payload: dict[str, Any],
    debug_payload: dict[str, Any] | None = None,
    hotspot_payload: dict[str, Any] | None = None,
    coordinate_audit_payload: dict[str, Any] | None = None,
    pair_schedule_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    incident_cards = [_incident_card(incident) for incident in primary_payload.get("incidents") or []]
    incident_cards.sort(
        key=lambda item: (
            _priority_rank(item["priority"]),
            _severity_rank(item["severity"]),
            -item["member_count"],
            -item["area_mm2"],
        )
    )

    confidence_mix = Counter(card["report_confidence"] for card in incident_cards)
    severity_mix = Counter(card["severity"] for card in incident_cards)
    pair_rollups = _pair_rollups(incident_cards)
    reader_sections = _reader_sections(
        incident_cards,
        coordinate_audit_payload=coordinate_audit_payload or {},
    )
    noise_summary = _noise_summary(
        debug_payload=debug_payload or {},
        hotspot_payload=hotspot_payload or {},
        coordinate_audit_payload=coordinate_audit_payload or {},
        pair_schedule_payload=pair_schedule_payload or {},
    )

    defendable_incidents = [card for card in incident_cards if card["defensible"]]
    validation_incidents = [card for card in incident_cards if not card["defensible"]]

    counts = {
        "selected_candidates": int(summary_payload.get("selected_candidate_count") or 0),
        "scheduled_pairs": int(summary_payload.get("scheduled_pair_count") or 0),
        "scheduled_files": int(summary_payload.get("scheduled_file_count") or 0),
        "elements": int(summary_payload.get("element_count") or 0),
        "primary_incidents": int(primary_payload.get("incident_count") or len(incident_cards)),
        "primary_members": int(primary_payload.get("incident_conflict_count") or 0),
        "debug_conflicts": int((debug_payload or {}).get("debug_conflict_count") or 0),
        "suppressed_elements": int((debug_payload or {}).get("suppressed_element_count") or 0),
        "hotspot_incidents": int((hotspot_payload or {}).get("incident_count") or 0),
        "audited_files": int((coordinate_audit_payload or {}).get("audit_count") or 0),
        "eligible_files": sum(
            1
            for item in (coordinate_audit_payload or {}).get("audits") or []
            if str(item.get("audit_status") or "") == "eligible"
        ),
    }

    return {
        "project_name": primary_payload.get("project_name") or summary_payload.get("project_name") or "Proyecto",
        "status": str(summary_payload.get("status") or "unknown"),
        "analysis_profile": str(summary_payload.get("analysis_profile") or "fast_compare"),
        "generated_at": summary_payload.get("generated_at") or primary_payload.get("generated_at"),
        "counts": counts,
        "confidence_mix": dict(confidence_mix),
        "severity_mix": dict(severity_mix),
        "pair_rollups": pair_rollups,
        "defendable_incidents": defendable_incidents,
        "validation_incidents": validation_incidents,
        "reader_sections": reader_sections,
        "noise_summary": noise_summary,
        "all_incidents": incident_cards,
    }


def render_primary_incidents_markdown(
    *,
    project_name: str,
    root: Path,
    primary_payload: dict[str, Any],
) -> str:
    context = build_coordination_report_context(summary_payload={}, primary_payload=primary_payload)
    lines = [
        f"# Primary Incidents - {project_name}",
        "",
        f"- Root: `{root.as_posix()}`",
        f"- Incident count: {context['counts']['primary_incidents']}",
        f"- Grouped conflict members: {context['counts']['primary_members']}",
        "",
        "## Reading Guide",
        "- `Primary` means the pair passed comparability, level, and geometry gating.",
        "- `Priority` tells the order for coordination review; `Confidence` tells how defendable the finding is today.",
        "- Use `technical_coordination_report.md` for executive reading and audience-specific sections.",
        "",
        "## Pair Summary",
        "| Pair | Incidents | Members | Priority focus | Confidence mix |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for rollup in context["pair_rollups"]:
        lines.append(
            "| "
            f"`{rollup['pair_label']}` | "
            f"{rollup['incident_count']} | "
            f"{rollup['member_count']} | "
            f"{rollup['top_priority']} | "
            f"{rollup['confidence_mix_label']} |"
        )

    lines.extend(
        [
            "",
            "## Top Incidents",
            "| ID | Priority | Severity | Confidence | Level | Disciplines | Members | Location | Recommended action |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for card in context["all_incidents"][:20]:
        lines.append(
            "| "
            f"`{card['incident_id']}` | "
            f"{card['priority']} | "
            f"{card['severity']} | "
            f"{card['report_confidence']} | "
            f"`{card['level_id']}` | "
            f"{card['discipline_pair']} | "
            f"{card['member_count']} | "
            f"{card['location_short']} | "
            f"{card['recommended_action']} |"
        )

    grouped_cards: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in context["all_incidents"]:
        grouped_cards[card["pair_label"]].append(card)

    lines.append("")
    lines.append("## Detailed Incidents by Pair")
    for pair_label, cards in grouped_cards.items():
        lines.append("")
        lines.append(f"### `{pair_label}`")
        lines.append("| ID | Priority | Severity | Confidence | Members | Area m2 | Layers | Bounds |")
        lines.append("| --- | --- | --- | --- | ---: | ---: | --- | --- |")
        for card in cards[:15]:
            lines.append(
                "| "
                f"`{card['incident_id']}` | "
                f"{card['priority']} | "
                f"{card['severity']} | "
                f"{card['report_confidence']} | "
                f"{card['member_count']} | "
                f"{card['area_m2']:.2f} | "
                f"`{card['layer_pair']}` | "
                f"`{card['bounds_short']}` |"
            )
        if len(cards) > 15:
            lines.append("")
            lines.append(f"- {len(cards) - 15} incidencias adicionales de este par quedan resumidas en `primary_incidents.json`.")

    lines.append("")
    return "\n".join(lines)


def render_coordination_report_markdown(
    *,
    project_name: str,
    root: Path,
    summary_payload: dict[str, Any],
    primary_payload: dict[str, Any],
    debug_payload: dict[str, Any] | None = None,
    hotspot_payload: dict[str, Any] | None = None,
    coordinate_audit_payload: dict[str, Any] | None = None,
    pair_schedule_payload: dict[str, Any] | None = None,
) -> str:
    context = build_coordination_report_context(
        summary_payload=summary_payload,
        primary_payload=primary_payload,
        debug_payload=debug_payload,
        hotspot_payload=hotspot_payload,
        coordinate_audit_payload=coordinate_audit_payload,
        pair_schedule_payload=pair_schedule_payload,
    )
    counts = context["counts"]
    lines = [
        f"# Technical Coordination Report - {project_name}",
        "",
        f"- Root: `{root.as_posix()}`",
        f"- Profile: `{context['analysis_profile']}`",
        f"- Status: `{context['status']}`",
        f"- Generated: `{context['generated_at'] or 'unknown'}`",
        "",
        "## Executive Summary",
        f"- Scheduled pairs reviewed: `{counts['scheduled_pairs']}` across `{counts['scheduled_files']}` source files.",
        f"- Defendable findings today: `{len(context['defendable_incidents'])}` of `{counts['primary_incidents']}` primary incidents.",
        f"- Technical noise held outside the main report: `{counts['debug_conflicts']}` debug conflicts and `{counts['suppressed_elements']}` suppressed elements.",
        f"- Confidence mix on primary incidents: {_counter_label(context['confidence_mix']) or 'none'}.",
        "",
        "## Report Logic",
        "- `Defendable findings` come from `primary` incidents only; they already passed comparability, level, and geometry gating.",
        "- `Noise / technical signal` stays outside the executive list and is fed by debug conflicts, suppressed geometry, blocked pairs, or audit statuses.",
        "- `Severity` estimates coordination impact. `Priority` defines the recommended review order. `Confidence` estimates how defendable the finding is with the current extraction quality.",
        "",
        "## Severity and Priority Criteria",
        "| Label | Meaning |",
        "| --- | --- |",
        "| `critical` | Large or repeated conflict with strong geometry and high review urgency. |",
        "| `high` | Strong coordination issue that should enter the next interdisciplinary review round. |",
        "| `medium` | Usable finding, but likely needs scoped validation or pair-level discussion. |",
        "| `low` | Weak signal or isolated case; keep visible but do not sell as a final clash. |",
        "",
        "| Priority | Use |",
        "| --- | --- |",
        "| `P1` | Review immediately in the next coordination session. |",
        "| `P2` | Review after the main blockers, still within the current cycle. |",
        "| `P3` | Track as low urgency or manual validation only. |",
    ]

    lines.extend(
        [
            "",
            "## Defendable Findings",
            "| ID | Priority | Severity | Confidence | Level | Disciplines | Location | Action owner | Recommended action |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for card in context["defendable_incidents"][:12]:
        lines.append(
            "| "
            f"`{card['incident_id']}` | "
            f"{card['priority']} | "
            f"{card['severity']} | "
            f"{card['report_confidence']} | "
            f"`{card['level_id']}` | "
            f"{card['discipline_pair']} | "
            f"{card['location_short']} | "
            f"{card['action_owner']} | "
            f"{card['recommended_action']} |"
        )
    if not context["defendable_incidents"]:
        lines.append("| - | - | - | - | - | - | - | - | No defendable findings in this run. |")

    lines.extend(
        [
            "",
            "## Findings Requiring Manual Validation",
            "| ID | Reason | Level | Layers | Suggested handling |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for card in context["validation_incidents"][:12]:
        lines.append(
            "| "
            f"`{card['incident_id']}` | "
            f"{card['validation_reason']} | "
            f"`{card['level_id']}` | "
            f"`{card['layer_pair']}` | "
            f"{card['recommended_action']} |"
        )
    if not context["validation_incidents"]:
        lines.append("| - | No primary incidents fell into the manual-validation bucket. | - | - | - |")

    lines.append("")
    lines.append("## Reader Sections")
    for profile_key in ("arquitectura", "electrico", "sanitario"):
        section = context["reader_sections"][profile_key]
        lines.append("")
        lines.append(f"### {section['title']}")
        lines.append(f"- Coverage in this run: `{section['coverage']}`")
        lines.append(f"- Current focus: {section['focus_text']}")
        if section["incidents"]:
            lines.append("")
            lines.append("| ID | Priority | Level | Pair | Why this reader should care |")
            lines.append("| --- | --- | --- | --- | --- |")
            for card in section["incidents"][:8]:
                lines.append(
                    "| "
                    f"`{card['incident_id']}` | "
                    f"{card['priority']} | "
                    f"`{card['level_id']}` | "
                    f"`{card['pair_label']}` | "
                    f"{card['reader_reason'][profile_key]} |"
                )
        else:
            lines.append("- No direct incidents were mapped to this reader profile in the current run.")

    lines.extend(
        [
            "",
            "## Pair Summary",
            "| Pair | Incidents | Members | Priority focus | Severity mix | Confidence mix |",
            "| --- | ---: | ---: | --- | --- | --- |",
        ]
    )
    for rollup in context["pair_rollups"]:
        lines.append(
            "| "
            f"`{rollup['pair_label']}` | "
            f"{rollup['incident_count']} | "
            f"{rollup['member_count']} | "
            f"{rollup['top_priority']} | "
            f"{rollup['severity_mix_label']} | "
            f"{rollup['confidence_mix_label']} |"
        )

    noise = context["noise_summary"]
    lines.extend(
        [
            "",
            "## Noise and Technical Support",
            f"- Debug conflicts kept outside the executive list: `{noise['debug_conflict_count']}`.",
            f"- Suppressed geometry count: `{noise['suppressed_element_count']}`; main reasons: {noise['suppression_reasons_label']}.",
            f"- Audit status mix: {noise['audit_status_label']}.",
            f"- Unscheduled or blocked pairs: `{noise['blocked_pair_count']}`; main reasons: {noise['blocked_reasons_label']}.",
            f"- Hotspots are kept as concentration zones only: `{noise['hotspot_incident_count']}` grouped cases.",
            "",
            "## Output Files",
            "- `technical_coordination_report.md`: executive and interdisciplinary reading.",
            "- `primary_incidents.md`: defendable incident register with pair-level detail.",
            "- `hotspot_incidents.md`: concentration zones and technical clustering, not final verdicts.",
            "- `coordinate_audit.md`: source eligibility and extraction quality.",
            "- `debug_candidates.json`: suppressed geometry and debug-only clashes.",
        ]
    )
    lines.append("")
    return "\n".join(lines)


def build_analysis_bot_context(
    *,
    project_name: str,
    nasas_root: Path,
    run_label: str,
    summary_payload: dict[str, Any],
    readiness_payload: dict[str, Any],
    coordinate_audit_payload: dict[str, Any],
    pair_schedule_payload: dict[str, Any],
    report_context: dict[str, Any],
    semantic_elements_payload: dict[str, Any] | None = None,
    clash_element_links_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    counts = report_context.get("counts") or {}
    defendable = report_context.get("defendable_incidents") or []
    validation = report_context.get("validation_incidents") or []
    audits = coordinate_audit_payload.get("audits") or []
    scheduled_pairs = [item for item in pair_schedule_payload.get("pairs") or [] if bool(item.get("scheduled"))]
    coverage = {
        "arquitectura": _coverage_for_bot(audits, "ARQUITECTURA"),
        "estructura": _coverage_for_bot(audits, "ESTRUCTURA"),
        "electrico": _coverage_for_bot(audits, "ELECTRICO"),
        "sanitario": _coverage_for_bot(audits, "HIDROSANITARIO"),
        "mecanico": _coverage_for_bot(audits, "MECANICO"),
    }
    semantic_summary = semantic_elements_payload or {}
    mapping_summary = clash_element_links_payload or {}
    mapped_links = list(mapping_summary.get("mapped") or [])
    semantic_publishable_types = sum(
        1
        for item in mapped_links
        if _link_has_publishable_types(item)
    )
    return {
        "project": {
            "name": project_name,
            "root": str(nasas_root),
            "run_label": run_label,
            "generated_at": summary_payload.get("generated_at"),
            "analysis_profile": summary_payload.get("analysis_profile") or "fast_compare",
            "status": summary_payload.get("status") or "unknown",
        },
        "bot_contract": {
            "purpose": "Answer factual questions about coordination analysis, source files, incidents, missing documents, coordinate audit, and report limitations.",
            "answer_policy": [
                "Never invent rooms, axes, element names, or disciplines.",
                "Distinguish candidate files, audited files, eligible files, scheduled pairs, primary incidents, hotspots, debug conflicts, and suppressed elements.",
                "If an element-level clash name is unavailable, say that only layer and geometry evidence exists.",
                "Use exact counts from metrics, not approximations.",
            ],
        },
        "run_summary": {
            "candidate_files": int(readiness_payload.get("candidate_count") or 0),
            "selected_candidates": int(counts.get("selected_candidates") or 0),
            "audited_files": int(counts.get("audited_files") or len(audits)),
            "eligible_files": int(
                counts.get("eligible_files")
                or sum(1 for item in audits if str(item.get("audit_status") or "") == "eligible")
            ),
            "scheduled_pairs": int(counts.get("scheduled_pairs") or 0),
            "elements": int(counts.get("elements") or 0),
            "primary_incidents": int(counts.get("primary_incidents") or 0),
            "defendable_incidents": len(defendable),
            "validation_incidents": len(validation),
            "debug_conflicts": int(counts.get("debug_conflicts") or 0),
            "suppressed_elements": int(counts.get("suppressed_elements") or 0),
            "hotspots_grouped": int(counts.get("hotspot_incidents") or 0),
            "confidence_mix": report_context.get("confidence_mix") or {},
            "severity_mix": report_context.get("severity_mix") or {},
        },
        "source_files": [
            {
                "file_id": f"source_{index:03d}",
                "filename": item.get("file_name"),
                "rel_path": item.get("rel_path"),
                "discipline": item.get("discipline"),
                "level": item.get("level_id"),
                "drawing_type": item.get("drawing_type"),
                "status": item.get("audit_status"),
                "coordinate_band": {
                    "label": item.get("coordinate_band"),
                    "key": item.get("coordinate_band_key"),
                    "unit": "mm",
                },
                "raw_primary": int(item.get("raw_primary_candidate_count") or 0),
                "raw_annotation": int(item.get("raw_annotation_count") or 0),
            }
            for index, item in enumerate(audits, start=1)
        ],
        "scheduled_pairs": [
            {
                "pair_id": f"pair_{index:03d}",
                "file_a": Path(str(item.get("file_a") or "")).name,
                "file_b": Path(str(item.get("file_b") or "")).name,
                "level_ids": list(item.get("level_ids") or []),
                "coordinate_band": item.get("coordinate_band"),
                "selection_reason": item.get("selection_reason"),
                "score": item.get("score"),
                "reason_codes": item.get("reason_codes") or [],
                "documentary_cohort_relation": item.get("documentary_cohort_relation"),
            }
            for index, item in enumerate(scheduled_pairs, start=1)
        ],
        "defendable_incidents": defendable,
        "validation_incidents": validation,
        "coverage": coverage,
        "noise_summary": report_context.get("noise_summary") or {},
        "elements_by_dwg_summary": {
            "file_count": int(semantic_summary.get("file_count") or 0),
            "element_count": int(semantic_summary.get("element_count") or 0),
            "element_type_mix": semantic_summary.get("element_type_mix") or {},
            "semantic_type_confidence_mix": semantic_summary.get("semantic_type_confidence_mix") or {},
        },
        "clash_element_links_summary": {
            "mapped_incidents_count": int(mapping_summary.get("mapped_incidents_count") or 0),
            "unmapped_incidents_count": int(mapping_summary.get("unmapped_incidents_count") or 0),
            "mapping_confidence_mix": mapping_summary.get("mapping_confidence_mix") or {},
            "publishable_semantic_type_count": semantic_publishable_types,
        },
        "limitations": [
            "Element-level semantic clash names are not yet resolved.",
            "Layer names are available, but layers are not equivalent to real building elements.",
            "Hotspots are concentration zones, not final clashes.",
            "Debug conflicts are technical signal and must not be presented as final findings.",
        ],
        "element_mapping_limitations": [
            "The MVP mapper is bbox-first and centroid-distance-second.",
            "Annotation layers and title graphics never produce defendable semantic naming.",
            "Low-confidence mapping must not be verbalized as a real constructible element.",
        ],
        "exact_entity_links_summary": {
            "mapped_with_exact_entity_count": int(mapping_summary.get("mapped_incidents_count") or 0),
            "requires_exact_entity_fallback_count": sum(1 for item in mapped_links if not _link_has_publishable_types(item)),
        },
        "semantic_typing_summary": {
            "semantic_type_confidence_mix": semantic_summary.get("semantic_type_confidence_mix") or {},
            "publishable_semantic_type_count": semantic_publishable_types,
        },
        "publishability_rules": {
            "publish_semantic_type_if": "mapping_confidence>=medium and semantic_type_confidence>=medium",
            "publish_element_name_if": "mapping_confidence>=medium and name_confidence>=medium",
            "fallback_if_not_publishable": "exact CAD entity handle + entity_type + layer + coordinates",
        },
        "resolved_readiness_contradiction": {
            "documentary_readiness_found_pairs": len(readiness_payload.get("auto_pair_candidates") or []),
            "audit_promoted_pairs": len(readiness_payload.get("promoted_pair_candidates") or []),
            "scheduled_pairs": len(scheduled_pairs),
            "message": "Documentary readiness may fail to find same-cohort pairs, but coordinate audit can still promote eligible cross-cohort comparisons.",
        },
        "faq_answer_map": [
            {"question": "¿Cuántas inconsistencias hubo?", "answer_source": "run_summary.primary_incidents"},
            {"question": "¿Cuántas inconsistencias defendibles hay?", "answer_source": "run_summary.defendable_incidents"},
            {"question": "¿Qué archivos DWG se compararon?", "answer_source": "scheduled_pairs"},
            {"question": "¿Hay eléctrico o sanitario en este run?", "answer_source": "coverage"},
        ],
        "mapped_incidents_count": int(mapping_summary.get("mapped_incidents_count") or 0),
        "unmapped_incidents_count": int(mapping_summary.get("unmapped_incidents_count") or 0),
        "mapping_confidence_mix": mapping_summary.get("mapping_confidence_mix") or {},
        "clash_element_links": {
            "mapped": mapping_summary.get("mapped") or [],
            "unmapped": mapping_summary.get("unmapped") or [],
        },
        "future_elements_by_dwg_contract": {
            "expected_file": "elements_by_dwg.json",
            "required_fields": [
                "semantic_element_id",
                "source_element_id",
                "source_file",
                "cad_handle",
                "element_name",
                "element_type",
                "discipline",
                "layer",
                "level",
                "bbox_or_polygon",
                "centroid",
                "name_confidence",
                "geometry_confidence",
            ],
        },
    }


def render_coordination_human_report_markdown(
    *,
    project_name: str,
    run_label: str,
    summary_payload: dict[str, Any],
    readiness_payload: dict[str, Any],
    coordinate_audit_payload: dict[str, Any],
    pair_schedule_payload: dict[str, Any],
    report_context: dict[str, Any],
    clash_element_links_payload: dict[str, Any] | None = None,
) -> str:
    counts = report_context.get("counts") or {}
    defendable = report_context.get("defendable_incidents") or []
    validation = report_context.get("validation_incidents") or []
    reader_sections = report_context.get("reader_sections") or {}
    noise = report_context.get("noise_summary") or {}
    scheduled_pairs = [item for item in pair_schedule_payload.get("pairs") or [] if bool(item.get("scheduled"))]
    promoted_pairs = readiness_payload.get("promoted_pair_candidates") or []
    eligible_files = (readiness_payload.get("audit_promotion_summary") or {}).get("eligible_files") or []
    mapped_lookup = {
        str(item.get("incident_id") or ""): item
        for item in (clash_element_links_payload or {}).get("mapped") or []
    }

    lines = [
        f"# Coordination Report Human - {project_name}",
        "",
        f"- Run: `{run_label}`",
        f"- Generated: `{summary_payload.get('generated_at') or 'unknown'}`",
        f"- Status: `{summary_payload.get('status') or 'unknown'}`",
        "",
        "## Resumen ejecutivo",
        f"- Se revisaron `{counts.get('scheduled_pairs', 0)}` pares comparativos sobre `{counts.get('scheduled_files', 0)}` archivos fuente.",
        f"- El run consolidó `{len(defendable)}` hallazgos defendibles y `{len(validation)}` casos que requieren validación manual.",
        f"- La salida técnica separó `{counts.get('debug_conflicts', 0)}` conflictos debug y `{counts.get('suppressed_elements', 0)}` elementos suprimidos fuera del mensaje principal.",
        "",
        "## Que se comparó y por que si fue comparable",
        "- El readiness documental no fue suficiente por sí solo para explicar la comparabilidad real del run.",
        "- El coordinate audit confirmó archivos `eligible`, nivel canónico común y bandas de coordenadas compatibles, lo que habilitó pares útiles para clash 2.5D.",
    ]
    if promoted_pairs:
        lines.append("")
        lines.append("| Pair | Selection reason | Levels | Score |")
        lines.append("| --- | --- | --- | ---: |")
        for item in promoted_pairs:
            lines.append(
                "| "
                f"`{Path(item['file_a']).name} vs {Path(item['file_b']).name}` | "
                f"`{item.get('selection_reason') or 'promoted_from_coordinate_audit'}` | "
                f"`{' / '.join(item.get('level_ids') or [])}` | "
                f"{float(item.get('score') or 0.0):.3f} |"
            )
    elif scheduled_pairs:
        lines.append("")
        lines.append("| Pair | Selection reason | Levels | Score |")
        lines.append("| --- | --- | --- | ---: |")
        for item in scheduled_pairs:
            lines.append(
                "| "
                f"`{Path(str(item.get('file_a') or '')).name} vs {Path(str(item.get('file_b') or '')).name}` | "
                f"`{item.get('selection_reason') or 'documentary_auto_match'}` | "
                f"`{' / '.join(item.get('level_ids') or [])}` | "
                f"{float(item.get('score') or 0.0):.3f} |"
            )
    if eligible_files:
        lines.extend(
            [
                "",
                "| File | Discipline | Level | Status | Coordinate band |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in eligible_files:
            lines.append(
                "| "
                f"`{Path(str(item['file'])).name}` | "
                f"{item['discipline']} | "
                f"`{item['level_id']}` | "
                f"`{item['audit_status']}` | "
                f"`{item['coordinate_band'] or 'none'}` |"
            )

    lines.extend(
        [
            "",
            "## Hallazgos defendibles",
        ]
    )
    for card in defendable[:10]:
        mapped = mapped_lookup.get(card["incident_id"])
        evidence_text = f"`{card['layer_pair']}`"
        exact_entity_text = None
        if mapped:
            evidence_text = _report_evidence_text(mapped, fallback_layer_pair=card["layer_pair"])
            exact_entity_text = _exact_entity_text(mapped)
        line = (
            f"- `{card['incident_id']}` | `{card['priority']}` | `{card['severity']}` | `{card['report_confidence']}`"
            f"\n  nivel: `{card['level_id']}`"
            f"\n  disciplinas: `{card['discipline_pair']}`"
            f"\n  ubicacion: `{card['location_short']}`"
            f"\n  evidencia: {evidence_text}"
            f"\n  accion: {card['recommended_action']}"
        )
        if exact_entity_text:
            line = line.replace(f"\n  accion: {card['recommended_action']}", f"\n  entidades CAD: {exact_entity_text}\n  accion: {card['recommended_action']}")
        lines.append(line)
        lines.append(f"![Visualización del clash](tiles/{card['incident_id']}_annotated.svg)")
    if not defendable:
        lines.append("- No hubo hallazgos defendibles en esta corrida.")

    lines.extend(
        [
            "",
            "## Casos que requieren validacion manual",
        ]
    )
    for card in validation[:10]:
        mapped = mapped_lookup.get(card["incident_id"])
        line = (
            f"- `{card['incident_id']}` | razon: {card['validation_reason']}"
            f"\n  nivel: `{card['level_id']}`"
            f"\n  par: `{card['pair_label']}`"
            f"\n  layers: `{card['layer_pair']}`"
            f"\n  accion: {card['recommended_action']}"
        )
        exact_entity_text = _exact_entity_text(mapped) if mapped else None
        if exact_entity_text:
            line = line.replace(f"\n  accion: {card['recommended_action']}", f"\n  entidades CAD: {exact_entity_text}\n  accion: {card['recommended_action']}")
        lines.append(line)
        lines.append(f"![Visualización del clash](tiles/{card['incident_id']}_annotated.svg)")
    if not validation:
        lines.append("- No quedaron incidencias abiertas para validación manual.")

    lines.extend(
        [
            "",
            "## Lectura por perfil",
            f"- Arquitectura: `{reader_sections.get('arquitectura', {}).get('coverage', 'not_in_run')}`",
            f"- Electrico: `{reader_sections.get('electrico', {}).get('coverage', 'not_in_run')}`",
            f"- Sanitario: `{reader_sections.get('sanitario', {}).get('coverage', 'not_in_run')}`",
            "",
            "## Ruido tecnico y limites del run",
            f"- Debug conflicts: `{noise.get('debug_conflict_count', 0)}`",
            f"- Hotspots agrupados: `{noise.get('hotspot_incident_count', 0)}`",
            f"- Blocked pairs: `{noise.get('blocked_pair_count', 0)}`",
            "- Este reporte no eleva nombres de elementos constructivos reales si no existe mapeo semántico confiable.",
            "",
            "## Proximos pasos",
            "- Mantener el coordinate audit como criterio superior cuando la cohorte documental no capture comparabilidad real.",
            "- Priorizar revisión interdisciplinaria sobre los hallazgos defendibles antes de reinterpretar ruido técnico.",
            "- Preparar una fase posterior de `clash -> elemento semantico` si entra un inventario DWG con geometría utilizable.",
            "",
        ]
    )
    return "\n".join(lines)


def render_coordination_human_report_html(
    *,
    project_name: str,
    run_label: str,
    markdown: str,
) -> str:
    body = []
    table_rows: list[str] = []
    traffic_light = _traffic_light_html(markdown)

    def flush_table() -> None:
        if table_rows:
            body.append(_markdown_table_to_html(table_rows))
            table_rows.clear()

    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            flush_table()
            continue
        if stripped.startswith("|"):
            table_rows.append(stripped)
            continue
        flush_table()
        if stripped.startswith("# "):
            body.append(f"<h1>{escape(stripped[2:])}</h1>")
            if traffic_light:
                body.append(traffic_light)
        elif stripped.startswith("## "):
            body.append(f"<h2>{escape(stripped[3:])}</h2>")
        elif stripped.startswith("![") and "](" in stripped and stripped.endswith(")"):
            alt = stripped[2 : stripped.index("]")]
            src = stripped[stripped.index("](") + 2 : -1]
            fallback_src = src.replace("_annotated.svg", ".svg")
            body.append(
                '<div class="tile-container">'
                f'<img src="{escape(src)}" onerror="this.onerror=null;this.src=\'{escape(fallback_src)}\';" '
                f'alt="{escape(alt)}" class="tile-img" />'
                "</div>"
            )
        elif stripped.startswith("- "):
            body.append(f"<p>{_inline_markdown_to_html(stripped[2:])}</p>")
        else:
            body.append(f"<p>{_inline_markdown_to_html(stripped)}</p>")
    flush_table()
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{escape(project_name)} - {escape(run_label)}</title>"
        "<style>"
        "body{font-family:Segoe UI,Arial,sans-serif;max-width:900px;margin:32px auto;padding:0 20px;line-height:1.45;color:#1f2937;background:#fff}"
        "h1,h2{color:#111827} h1{font-size:28px} h2{font-size:20px;margin-top:28px;border-bottom:1px solid #e5e7eb;padding-bottom:6px}"
        "p{margin:10px 0} code{background:#f3f4f6;border-radius:4px;padding:1px 4px}"
        "table{border-collapse:collapse;width:100%;margin:14px 0;font-size:13px}th,td{border:1px solid #d1d5db;padding:7px;text-align:left;vertical-align:top}th{background:#f9fafb}"
        ".tile-container{margin:12px 0 22px;border:1px solid #d1d5db;border-radius:6px;overflow:hidden;background:#fff}"
        ".tile-img{display:block;max-width:100%;width:100%;height:auto}"
        ".traffic-light{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 20px}"
        ".badge{display:inline-block;padding:5px 9px;border-radius:999px;color:#fff;font-size:12px;font-weight:700}"
        ".severity-critical{background:#DC2626}.severity-major{background:#D97706}.severity-minor{background:#2563EB}.severity-noise{background:#6B7280}"
        "</style></head><body>"
        + "".join(body)
        + "</body></html>"
    )


def _link_has_publishable_types(link: dict[str, Any]) -> bool:
    if str(link.get("mapping_confidence") or "") not in {"medium", "high"}:
        return False
    left = link.get("file_a") or {}
    right = link.get("file_b") or {}
    return _publishable_type_from_side(left) is not None and _publishable_type_from_side(right) is not None


def _traffic_light_html(markdown: str) -> str:
    counts = Counter()
    for line in markdown.splitlines():
        match = re.match(r"- `[^`]+` \| `[^`]+` \| `([^`]+)` \|", line.strip())
        if match:
            counts[match.group(1)] += 1
    if not counts:
        return ""
    return (
        '<div class="traffic-light">'
        f'<span class="badge severity-critical">🔴 {counts.get("critical", 0)} críticos</span>'
        f'<span class="badge severity-major">🟡 {counts.get("major", 0)} mayores</span>'
        f'<span class="badge severity-minor">🔵 {counts.get("minor", 0)} menores</span>'
        f'<span class="badge severity-noise">⚪ {counts.get("noise", 0) + counts.get("low", 0)} ruido</span>'
        "</div>"
    )


def _markdown_table_to_html(rows: list[str]) -> str:
    if len(rows) < 2:
        return "<pre>" + escape("\n".join(rows)) + "</pre>"
    header = _split_markdown_table_row(rows[0])
    body_rows = [_split_markdown_table_row(row) for row in rows[2:]]
    html_rows = [
        "<table><thead><tr>"
        + "".join(f"<th>{_inline_markdown_to_html(cell)}</th>" for cell in header)
        + "</tr></thead><tbody>"
    ]
    for row in body_rows:
        html_rows.append(
            "<tr>" + "".join(f"<td>{_inline_markdown_to_html(cell)}</td>" for cell in row) + "</tr>"
        )
    html_rows.append("</tbody></table>")
    return "".join(html_rows)


def _split_markdown_table_row(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _inline_markdown_to_html(text: str) -> str:
    escaped = escape(text)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)


def _publishable_type_from_side(side: dict[str, Any]) -> str | None:
    confidence = str(side.get("semantic_type_confidence") or "unknown")
    element_type = str(side.get("element_type") or "")
    if confidence not in {"medium", "high"}:
        return None
    if not element_type or element_type.startswith("unknown_"):
        return None
    return element_type


def _publishable_name_from_side(side: dict[str, Any]) -> str | None:
    confidence = str(side.get("name_confidence") or "low")
    name = side.get("element_name")
    if confidence not in {"medium", "high"}:
        return None
    return str(name) if name else None


def _report_evidence_text(link: dict[str, Any], *, fallback_layer_pair: str) -> str:
    if str(link.get("mapping_confidence") or "") not in {"medium", "high"}:
        return f"`{fallback_layer_pair}`"
    left = link.get("file_a") or {}
    right = link.get("file_b") or {}
    left_name = _publishable_name_from_side(left)
    right_name = _publishable_name_from_side(right)
    if left_name and right_name:
        return f"`{left_name} / {right_name}`"
    left_type = _publishable_type_from_side(left)
    right_type = _publishable_type_from_side(right)
    if left_type and right_type:
        return f"`{left_type} / {right_type}`"
    return f"`{fallback_layer_pair}`"


def _exact_entity_text(link: dict[str, Any] | None) -> str | None:
    if not link:
        return None
    left = link.get("file_a") or {}
    right = link.get("file_b") or {}
    if not left and not right:
        return None
    left_label = _exact_entity_side_label(left)
    right_label = _exact_entity_side_label(right)
    return f"`{left_label}` vs `{right_label}`"


def _exact_entity_side_label(side: dict[str, Any]) -> str:
    handle = str(side.get("cad_handle") or "no_handle")
    entity_type = str(side.get("entity_type") or "unknown")
    layer = str(side.get("layer") or "0")
    source_id = str(side.get("source_element_id") or "unknown")
    return f"{handle}/{entity_type}/{layer}/{source_id}"


def _incident_card(incident: dict[str, Any]) -> dict[str, Any]:
    representative = incident.get("representative_conflict") or {}
    file_names = tuple(Path(path).name for path in incident.get("file_pair") or ("", ""))
    source_refs = representative.get("source_refs") or ("", "")
    geometry_sources = tuple(representative.get("geometry_sources") or incident.get("geometry_sources") or ())
    level_assignment_sources = tuple(representative.get("level_assignment_sources") or ())
    disciplines = (
        str(representative.get("discipline_a") or "unknown"),
        str(representative.get("discipline_b") or "unknown"),
    )
    layers = tuple(_layer_name(ref) for ref in source_refs)
    entities = tuple(_entity_name(ref) for ref in source_refs)
    area_mm2 = float(representative.get("plan_intersection_area_mm2") or 0.0)
    member_count = int(incident.get("member_count") or 0)
    overlap_depth_mm = float(representative.get("overlap_depth_z_mm") or 0.0)
    report_confidence = _report_confidence(
        base_confidence=str(incident.get("confidence") or representative.get("confidence") or "medium"),
        geometry_sources=geometry_sources,
        level_assignment_sources=level_assignment_sources,
        member_count=member_count,
    )
    severity = _severity(
        member_count=member_count,
        area_mm2=area_mm2,
        overlap_depth_mm=overlap_depth_mm,
        report_confidence=report_confidence,
    )
    priority = _priority(severity=severity, report_confidence=report_confidence)
    reader_profiles = _reader_profiles(
        disciplines=disciplines,
        file_names=file_names,
        layers=layers,
    )
    validation_reason = _validation_reason(
        report_confidence=report_confidence,
        geometry_sources=geometry_sources,
        level_assignment_sources=level_assignment_sources,
        member_count=member_count,
    )
    pair_label = f"{file_names[0]} vs {file_names[1]}"
    bounds = tuple(float(value) for value in incident.get("plan_bounds_mm") or representative.get("plan_intersection_bounds_mm") or (0, 0, 0, 0))
    centroid = tuple(float(value) for value in incident.get("plan_centroid_mm") or representative.get("plan_intersection_centroid_mm") or (0, 0))

    return {
        "incident_id": str(incident.get("incident_id") or "unknown"),
        "pair_label": pair_label,
        "file_names": file_names,
        "discipline_pair": " / ".join(disciplines),
        "disciplines": disciplines,
        "level_id": str(incident.get("level_id") or representative.get("level_ids", ["mixed"])[0]),
        "member_count": member_count,
        "area_mm2": area_mm2,
        "area_m2": area_mm2 / 1_000_000.0,
        "overlap_depth_mm": overlap_depth_mm,
        "report_confidence": report_confidence,
        "severity": severity,
        "priority": priority,
        "defensible": report_confidence != "low" and severity != "low",
        "validation_reason": validation_reason,
        "geometry_sources": geometry_sources,
        "level_assignment_sources": level_assignment_sources,
        "layer_pair": " / ".join(layer for layer in layers if layer),
        "entity_pair": " / ".join(entity for entity in entities if entity),
        "location_short": _location_short(level_id=str(incident.get("level_id") or "mixed"), centroid=centroid),
        "bounds_short": _bounds_short(bounds),
        "recommended_action": _recommended_action(disciplines=disciplines, severity=severity),
        "action_owner": _action_owner(disciplines),
        "reader_profiles": reader_profiles,
        "reader_reason": _reader_reason(disciplines=disciplines, severity=severity),
    }


def _coverage_for_bot(audits: list[dict[str, Any]], discipline: str) -> str:
    statuses = [str(item.get("audit_status") or "unknown") for item in audits if str(item.get("discipline") or "") == discipline]
    if not statuses:
        return "not_in_run"
    if any(status == "eligible" for status in statuses):
        return "direct"
    return "indirect"


def _pair_rollups(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        grouped[card["pair_label"]].append(card)
    rollups: list[dict[str, Any]] = []
    for pair_label, pair_cards in grouped.items():
        confidence_mix = Counter(card["report_confidence"] for card in pair_cards)
        severity_mix = Counter(card["severity"] for card in pair_cards)
        priorities = sorted({_priority_rank(card["priority"]): card["priority"] for card in pair_cards}.items())
        rollups.append(
            {
                "pair_label": pair_label,
                "incident_count": len(pair_cards),
                "member_count": sum(card["member_count"] for card in pair_cards),
                "top_priority": priorities[0][1] if priorities else "P3",
                "confidence_mix_label": _counter_label(confidence_mix),
                "severity_mix_label": _counter_label(severity_mix),
            }
        )
    rollups.sort(key=lambda item: (-item["incident_count"], item["pair_label"]))
    return rollups


def _reader_sections(
    cards: list[dict[str, Any]],
    *,
    coordinate_audit_payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    titles = {
        "arquitectura": "Arquitectura",
        "electrico": "Electrico",
        "sanitario": "Sanitario",
    }
    audits = coordinate_audit_payload.get("audits") or []
    audit_disciplines = {str(item.get("discipline") or "") for item in audits}
    coverage_map = {
        "arquitectura": "ARQUITECTURA" in audit_disciplines or any("ARQUITECTURA" in card["disciplines"] for card in cards),
        "electrico": "ELECTRICO" in audit_disciplines or any("ELECTRICO" in card["disciplines"] for card in cards),
        "sanitario": "HIDROSANITARIO" in audit_disciplines or any("HIDROSANITARIO" in card["disciplines"] for card in cards),
    }

    sections: dict[str, dict[str, Any]] = {}
    for profile_key, title in titles.items():
        profile_cards = [card for card in cards if profile_key in card["reader_profiles"]]
        coverage = "direct" if coverage_map[profile_key] else "not_in_run"
        focus_text = (
            "review top defendable conflicts first"
            if profile_cards
            else "no direct pair for this profile in the current run"
        )
        sections[profile_key] = {
            "title": title,
            "coverage": coverage,
            "focus_text": focus_text,
            "incidents": profile_cards,
        }
    return sections


def _noise_summary(
    *,
    debug_payload: dict[str, Any],
    hotspot_payload: dict[str, Any],
    coordinate_audit_payload: dict[str, Any],
    pair_schedule_payload: dict[str, Any],
) -> dict[str, Any]:
    suppressed = debug_payload.get("suppressed_elements") or []
    suppression_reasons = Counter(str(item.get("suppression_reason") or "unknown") for item in suppressed)
    audits = coordinate_audit_payload.get("audits") or []
    audit_statuses = Counter(str(item.get("audit_status") or "unknown") for item in audits)
    pairs = pair_schedule_payload.get("pairs") or []
    blocked_pairs = [item for item in pairs if not bool(item.get("scheduled"))]
    blocked_reasons = Counter(str(item.get("block_reason") or "unknown") for item in blocked_pairs)
    return {
        "debug_conflict_count": int(debug_payload.get("debug_conflict_count") or 0),
        "suppressed_element_count": int(debug_payload.get("suppressed_element_count") or 0),
        "suppression_reasons_label": _counter_label(suppression_reasons) or "none",
        "audit_status_label": _counter_label(audit_statuses) or "none",
        "blocked_pair_count": len(blocked_pairs),
        "blocked_reasons_label": _counter_label(blocked_reasons) or "none",
        "hotspot_incident_count": int(hotspot_payload.get("incident_count") or 0),
    }


def _report_confidence(
    *,
    base_confidence: str,
    geometry_sources: tuple[str, ...],
    level_assignment_sources: tuple[str, ...],
    member_count: int,
) -> str:
    score = {"low": 0, "medium": 1, "high": 2}.get(base_confidence.lower(), 1)
    if any("bbox" in source for source in geometry_sources):
        score -= 2
    elif any("line" in source for source in geometry_sources):
        score -= 1
    if geometry_sources and all("polyline" in source for source in geometry_sources):
        score += 1
    if any(source == "default_level" for source in level_assignment_sources):
        score -= 1
    if any("clamped" in source or "fallback" in source for source in level_assignment_sources):
        score -= 1
    if member_count >= 6:
        score += 1
    if score >= 3:
        return "high"
    if score >= 1:
        return "medium"
    return "low"


def _severity(
    *,
    member_count: int,
    area_mm2: float,
    overlap_depth_mm: float,
    report_confidence: str,
) -> str:
    score = 0.0
    if member_count >= 12:
        score += 2.0
    elif member_count >= 6:
        score += 1.0
    elif member_count >= 3:
        score += 0.5
    if area_mm2 >= 2_000_000.0:
        score += 2.0
    elif area_mm2 >= 750_000.0:
        score += 1.0
    elif area_mm2 >= 200_000.0:
        score += 0.5
    if overlap_depth_mm >= 250.0:
        score += 1.0
    elif overlap_depth_mm >= 100.0:
        score += 0.5
    if report_confidence == "high":
        score += 1.0
    elif report_confidence == "low":
        score -= 1.0
    if score >= 4.5 and report_confidence == "high":
        return "critical"
    if score >= 3.0:
        return "high"
    if score >= 1.5:
        return "medium"
    return "low"


def _priority(*, severity: str, report_confidence: str) -> str:
    if severity == "critical":
        return "P1"
    if severity == "high" and report_confidence == "high":
        return "P1"
    if severity in {"high", "medium"}:
        return "P2"
    return "P3"


def _validation_reason(
    *,
    report_confidence: str,
    geometry_sources: tuple[str, ...],
    level_assignment_sources: tuple[str, ...],
    member_count: int,
) -> str:
    if report_confidence == "low":
        return "low confidence signal"
    if any("line" in source for source in geometry_sources):
        return "line-based geometry needs manual confirmation"
    if any(source == "default_level" for source in level_assignment_sources):
        return "level assignment came from default level"
    if member_count <= 1:
        return "isolated single-member incident"
    return "manual confirmation recommended"


def _recommended_action(*, disciplines: tuple[str, str], severity: str) -> str:
    discipline_set = set(disciplines)
    urgency = (
        "escalar en la siguiente ronda de coordinacion"
        if severity in {"critical", "high"}
        else "revisar con validacion acotada"
    )
    if {"ARQUITECTURA", "ESTRUCTURA"}.issubset(discipline_set):
        return f"Validar si la geometria arquitectonica invade espacio estructural o si solo traza un contorno, y luego {urgency}."
    if {"ARQUITECTURA", "ELECTRICO"}.issubset(discipline_set):
        return f"Revisar ruta, reserva y holguras entre arquitectura y el trazado electrico, y luego {urgency}."
    if {"ARQUITECTURA", "HIDROSANITARIO"}.issubset(discipline_set):
        return f"Revisar ruta de tuberias, reserva de shaft y supuestos de pendiente u holgura, y luego {urgency}."
    if {"ESTRUCTURA", "ELECTRICO"}.issubset(discipline_set):
        return f"Confirmar apertura, manga o estrategia de reruteo antes de coordinar la incidencia, y luego {urgency}."
    if {"ESTRUCTURA", "HIDROSANITARIO"}.issubset(discipline_set):
        return f"Confirmar apertura, manga o estrategia de reruteo para sistemas hidrosanitarios, y luego {urgency}."
    return f"Revisar el par directamente y {urgency}."


def _action_owner(disciplines: tuple[str, str]) -> str:
    owner_map = {
        "ARQUITECTURA": "Arquitectura",
        "ELECTRICO": "Electrico",
        "ESTRUCTURA": "Estructura",
        "HIDROSANITARIO": "Sanitario",
        "MECANICO": "Mecanico",
    }
    return " + ".join(owner_map.get(item, item.title()) for item in disciplines)


def _reader_profiles(
    *,
    disciplines: tuple[str, str],
    file_names: tuple[str, str],
    layers: tuple[str, str],
) -> list[str]:
    profiles: set[str] = set()
    tokens = _profile_tokens([*disciplines, *file_names, *layers])
    if "ARQUITECTURA" in disciplines:
        profiles.add("arquitectura")
    if "ELECTRICO" in disciplines or any(
        token.startswith(("ELEC", "LIGHT", "POWER", "TOMA", "PANEL", "SWITCH", "OUTLET", "LUMIN"))
        for token in tokens
    ):
        profiles.add("electrico")
    if "HIDROSANITARIO" in disciplines or any(
        token.startswith(("SANIT", "AGUA", "DRENAJ", "PIPE", "TUB", "DESAG", "WASTE", "VENT"))
        for token in tokens
    ):
        profiles.add("sanitario")
    return sorted(profiles)


def _reader_reason(*, disciplines: tuple[str, str], severity: str) -> dict[str, str]:
    base = {
        "arquitectura": "la geometria arquitectonica o la reserva espacial estan implicadas",
        "electrico": "la ruta electrica o la reserva podria requerir ajuste",
        "sanitario": "la ruta sanitaria, el shaft o la pendiente podria requerir ajuste",
    }
    if "ESTRUCTURA" in disciplines and severity in {"critical", "high"}:
        base["arquitectura"] = "una decision arquitectonica puede crear o resolver un conflicto estructural"
    return base


def _layer_name(source_ref: str) -> str:
    parts = source_ref.split("|")
    return parts[1] if len(parts) > 1 else ""


def _entity_name(source_ref: str) -> str:
    parts = source_ref.split("|")
    return parts[2] if len(parts) > 2 else ""


def _location_short(*, level_id: str, centroid: tuple[float, float]) -> str:
    return f"{level_id}; ({round(centroid[0]):,}, {round(centroid[1]):,}) mm"


def _bounds_short(bounds: tuple[float, float, float, float]) -> str:
    return ", ".join(f"{round(value):,}" for value in bounds)


def _counter_label(counter: Counter[str] | dict[str, int]) -> str:
    if not counter:
        return ""
    items = counter.items() if isinstance(counter, Counter) else counter.items()
    ordered = sorted(items, key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{label}={count}" for label, count in ordered if count)


def _severity_rank(label: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(label, 4)


def _priority_rank(label: str) -> int:
    return {"P1": 0, "P2": 1, "P3": 2}.get(label, 3)


def _profile_tokens(parts: list[str]) -> list[str]:
    tokens: list[str] = []
    for part in parts:
        tokens.extend(token for token in re.split(r"[^A-Z0-9]+", part.upper()) if token)
    return tokens
