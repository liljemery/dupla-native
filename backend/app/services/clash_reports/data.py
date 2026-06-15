"""Parse clash job artifacts into structured report data."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.services.clash_reports.formatting import (
    FilenameAliasRegistry,
    wrap_filename_alias,
)
from app.services.clash_reports.normalize import (
    FieldProvenance,
    file_discipline_hints_from_documents,
    merge_enriched_cards,
    normalize_incident_for_reports,
    parse_revision_md_incidents,
)

_NA = "no disponible"


def _parse_json_field(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _project_letter(project_name: str) -> str:
    base = project_name.split("—")[0].split("–")[0].strip()
    slug = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").upper()
    parts = slug.split("_")
    return parts[0][0] if parts else "X"


@dataclass
class IncidentView:
    incident_id: str
    human_code: str
    group_code: str
    layer_a: str | None
    layer_b: str | None
    file_a_alias: str
    file_b_alias: str
    file_a_full: str
    file_b_full: str
    discipline_a: str
    discipline_b: str
    level_id: str
    severity: str
    confidence: str
    area_mm2: float
    area_m2_text: str
    z_depth_mm: float | None
    z_depth_text: str
    center_text: str
    bounds_text: str
    bounds: tuple[float, float, float, float] | None
    zoom_command: str | None
    zoom_fallback: str | None
    member_count: int
    clash_type: str
    handle_a: str | None
    handle_b: str | None
    what_to_check: str
    provenance: FieldProvenance = field(default_factory=FieldProvenance)
    warnings: list[str] = field(default_factory=list)


@dataclass
class GroupView:
    code: str
    layer_a: str
    layer_b: str
    discipline_pair: str
    incident_count: int
    total_area_m2: float
    priority: str
    incidents: list[IncidentView] = field(default_factory=list)


@dataclass
class ReportBundle:
    meta: dict[str, Any]
    primary: dict[str, Any]
    context: dict[str, Any]
    pair_schedule: dict[str, Any]
    analyzed_documents: list[dict[str, Any]]
    alias_registry: FilenameAliasRegistry
    incidents: list[IncidentView]
    groups: list[GroupView]
    warnings: list[str]
    output_dir: str | None = None


def _view_from_normalized(
    norm,
    *,
    human_code: str,
    group_code: str,
    registry: FilenameAliasRegistry,
) -> IncidentView:
    file_a_alias = wrap_filename_alias(
        norm.file_a_full,
        registry,
        discipline=norm.discipline_a if norm.discipline_a != _NA else None,
        level=norm.level_id if norm.level_id != _NA else None,
    )
    file_b_alias = wrap_filename_alias(
        norm.file_b_full,
        registry,
        discipline=norm.discipline_b if norm.discipline_b != _NA else None,
        level=norm.level_id if norm.level_id != _NA else None,
    )
    return IncidentView(
        incident_id=norm.incident_id,
        human_code=human_code,
        group_code=group_code,
        layer_a=norm.layer_a,
        layer_b=norm.layer_b,
        file_a_alias=file_a_alias,
        file_b_alias=file_b_alias,
        file_a_full=norm.file_a_full,
        file_b_full=norm.file_b_full,
        discipline_a=norm.discipline_a,
        discipline_b=norm.discipline_b,
        level_id=norm.level_id,
        severity=norm.severity,
        confidence=norm.confidence,
        area_mm2=norm.area_mm2,
        area_m2_text=norm.area_m2_text,
        z_depth_mm=norm.z_depth_mm,
        z_depth_text=norm.z_depth_text,
        center_text=norm.center_text,
        bounds_text=norm.bounds_text,
        bounds=norm.bounds,
        zoom_command=norm.zoom_command,
        zoom_fallback=norm.zoom_fallback,
        member_count=norm.member_count,
        clash_type=norm.clash_type,
        handle_a=norm.handle_a,
        handle_b=norm.handle_b,
        what_to_check=norm.what_to_check,
        provenance=norm.provenance,
        warnings=list(norm.warnings),
    )


def build_report_bundle(
    *,
    meta: dict[str, Any],
    artifacts: dict[str, Any],
) -> ReportBundle:
    primary = _parse_json_field(artifacts.get("primary_incidents"))
    context = _parse_json_field(artifacts.get("coordination_context"))
    pair_schedule = _parse_json_field(artifacts.get("pair_schedule"))
    analyzed_documents = [
        d for d in (artifacts.get("analyzed_documents") or []) if isinstance(d, dict)
    ]
    output_dir = artifacts.get("output_dir")
    revision_md = str(artifacts.get("revision_md") or "")

    project_name = str(meta.get("project_name") or primary.get("project_name") or "Proyecto")
    letter = _project_letter(project_name)
    registry = FilenameAliasRegistry()
    file_hints = file_discipline_hints_from_documents(analyzed_documents)
    enriched_cards = merge_enriched_cards(context)
    revision_parsed = parse_revision_md_incidents(revision_md)

    for doc in analyzed_documents:
        wrap_filename_alias(
            str(doc.get("original_name") or doc.get("file_name") or ""),
            registry,
            discipline=str(doc.get("discipline") or doc.get("discipline_bucket") or ""),
            level=str(doc.get("level_id") or "") or None,
        )

    raw_incidents = [i for i in (primary.get("incidents") or []) if isinstance(i, dict)]

    pre_normalized: list[tuple[dict[str, Any], Any]] = []
    for inc in raw_incidents:
        iid = str(inc.get("incident_id") or "")
        norm = normalize_incident_for_reports(
            raw=inc,
            human_code="?",
            group_code="?",
            enriched=enriched_cards.get(iid),
            revision_parsed=revision_parsed.get(iid),
            file_discipline_hints=file_hints,
        )
        pre_normalized.append((inc, norm))

    layer_groups: dict[tuple[str, str], list[tuple[dict[str, Any], Any]]] = defaultdict(list)
    for inc, norm in pre_normalized:
        key = (norm.layer_a or _NA, norm.layer_b or _NA)
        layer_groups[key].append((inc, norm))

    sorted_groups = sorted(
        layer_groups.items(),
        key=lambda kv: -sum(n.area_mm2 for _, n in kv[1]),
    )

    group_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    all_incidents: list[IncidentView] = []
    groups: list[GroupView] = []

    for g_idx, ((layer_a, layer_b), items) in enumerate(sorted_groups):
        gl = group_letters[g_idx] if g_idx < len(group_letters) else str(g_idx)
        group_code = f"{letter}-{gl}"
        total_area = sum(n.area_mm2 for _, n in items) / 1_000_000.0
        priority = "Empieza aqui" if g_idx == 0 else ("Revisar" if g_idx < 3 else "Confirmar rapido")
        first_norm = items[0][1]
        discipline_pair = f"{first_norm.discipline_a} / {first_norm.discipline_b}"
        group_view = GroupView(
            code=group_code,
            layer_a=layer_a,
            layer_b=layer_b,
            discipline_pair=discipline_pair,
            incident_count=len(items),
            total_area_m2=round(total_area, 2),
            priority=priority,
        )

        for i_idx, (inc, norm) in enumerate(items):
            human_code = f"{group_code}{i_idx + 1}"
            iid = str(inc.get("incident_id") or "")
            final_norm = normalize_incident_for_reports(
                raw=inc,
                human_code=human_code,
                group_code=group_code,
                enriched=enriched_cards.get(iid),
                revision_parsed=revision_parsed.get(iid),
                file_discipline_hints=file_hints,
            )
            view = _view_from_normalized(
                final_norm,
                human_code=human_code,
                group_code=group_code,
                registry=registry,
            )
            group_view.incidents.append(view)
            all_incidents.append(view)

        groups.append(group_view)

    global_warnings: list[str] = []
    for inc in all_incidents:
        global_warnings.extend(inc.warnings)

    if not raw_incidents:
        global_warnings.append("No se detectaron incidencias primarias en esta corrida.")

    return ReportBundle(
        meta=meta,
        primary=primary,
        context=context,
        pair_schedule=pair_schedule,
        analyzed_documents=analyzed_documents,
        alias_registry=registry,
        incidents=all_incidents,
        groups=groups,
        warnings=list(dict.fromkeys(global_warnings)),
        output_dir=str(output_dir) if output_dir else None,
    )


def executive_summary(bundle: ReportBundle) -> dict[str, str]:
    primary = bundle.primary
    levels = sorted({i.level_id for i in bundle.incidents if i.level_id != _NA})
    total_area = sum(i.area_mm2 for i in bundle.incidents) / 1_000_000.0
    top_group = bundle.groups[0].code if bundle.groups else _NA
    return {
        "incidents": str(len(bundle.incidents)),
        "conflicts": str(primary.get("incident_conflict_count") or sum(i.member_count for i in bundle.incidents)),
        "levels": ", ".join(levels) if levels else _NA,
        "top_group": top_group,
        "total_area": f"{total_area:.2f} m2",
    }
