"""Coordinate and eligibility audit helpers for staged clash runs."""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from coordination.selection.fast_compare import PreMatchCandidate, primary_geometry_role
from coordination.core.models_25d import Element25D

AuditStatus = Literal["eligible", "needs_alignment", "annotation_noise", "bbox_only", "extract_failed", "detail_only"]


class PairScheduleStatus:
    """Typed block/ready codes for PairScheduleItem.block_reason / selection_reason."""
    READY_HIGH = "READY_HIGH"
    READY_MEDIUM = "READY_MEDIUM"
    READY_LOW = "READY_LOW"
    BLOCKED_ALIGNMENT = "BLOCKED_ALIGNMENT"
    BLOCKED_NO_PRIMARY_GEOMETRY = "BLOCKED_NO_PRIMARY_GEOMETRY"
    BLOCKED_DETAIL_ONLY = "BLOCKED_DETAIL_ONLY"
    BLOCKED_COORDINATE_MISMATCH = "BLOCKED_COORDINATE_MISMATCH"
    BLOCKED_LEVEL_MISMATCH = "BLOCKED_LEVEL_MISMATCH"
    BLOCKED_ROLE_MISSING = "BLOCKED_ROLE_MISSING"


_DETAIL_ONLY_NAME_TOKENS = (
    "DETALLE", "DETALLES", "DETAIL", "DETAILS", "DET.", "AMPLIACION",
    "AMPLIACIÓN", "TYPICAL", "SIMBOLOGIA", "SIMBOLOGÍA",
)
DETAIL_ONLY_MAX_PRIMARY_COUNT = 5

COMBINED_AS_BUILT_NAME_TOKENS = (
    "COMBINADO",
    "TODAS",
    "GENERAL",
    "COORDINACION",
    "COORDINACIÓN",
    "AS-BUILT",
    "AS BUILT",
    "ASBUILT",
)
HIGH_ENTITY_COUNT_THRESHOLD = 50_000
HIGH_LAYOUT_COUNT_THRESHOLD = 20
LARGE_FILE_SIZE_BYTES = 75 * 1024 * 1024


class SourceAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rel_path: str
    file_name: str
    suffix: str
    issue_key: str
    cohort_id: str
    discipline: str
    level_id: str
    level_source: str
    drawing_type: str = "generic"
    coordinate_band_key: tuple[int, int] | None = None
    coordinate_band: str | None = None
    centroid_mm: tuple[float, float] | None = None
    bounds_mm: tuple[float, float, float, float] | None = None
    units_to_mm_factor: float | None = None
    raw_entity_count: int = 0
    raw_primary_candidate_count: int = 0
    raw_annotation_count: int = 0
    raw_bbox_only_count: int = 0
    selected_total_count: int = 0
    selected_primary_count: int = 0
    dominant_entity_types: list[str] = Field(default_factory=list)
    audit_status: AuditStatus = "extract_failed"
    detail_only: bool = False
    notes: list[str] = Field(default_factory=list)


class PairScheduleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohort_id: str
    file_a: str
    file_b: str
    coordinate_band: str | None = None
    level_ids: tuple[str, str]
    decision: str = "not_comparable"
    score: float = 0.0
    reason_codes: list[str] = Field(default_factory=list)
    selection_reason: str | None = None
    promotion_basis: str | None = None
    documentary_cohort_relation: str = "same_cohort"
    scheduled: bool
    block_reason: str | None = None


def selection_sanity_flags(
    *,
    path: str | Path,
    raw_entity_count: int = 0,
    layout_count: int = 0,
    file_size_bytes: int | None = None,
) -> list[str]:
    """Flag combined/as-built files promoted from the SERENA sanitation POC."""
    text = str(path).upper()
    flags: list[str] = []
    matched = [token for token in COMBINED_AS_BUILT_NAME_TOKENS if token in text]
    if matched:
        flags.append(f"name_pattern={','.join(matched)}")
    if raw_entity_count > HIGH_ENTITY_COUNT_THRESHOLD:
        flags.append(f"high_entity_count={raw_entity_count}")
    if layout_count > HIGH_LAYOUT_COUNT_THRESHOLD:
        flags.append(f"high_layout_count={layout_count}")
    if file_size_bytes is not None and file_size_bytes > LARGE_FILE_SIZE_BYTES:
        flags.append(f"large_file_size_mb={file_size_bytes / (1024 * 1024):.1f}")
    return flags


def hs_findings(
    *,
    path: str | Path,
    raw_entity_count: int = 0,
    layout_count: int = 0,
    file_size_bytes: int | None = None,
    alternatives: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Return the HS-oriented selection sanity report used by Phase 1."""
    flags = selection_sanity_flags(
        path=path,
        raw_entity_count=raw_entity_count,
        layout_count=layout_count,
        file_size_bytes=file_size_bytes,
    )
    return {
        "path": str(path),
        "raw_entity_count": raw_entity_count,
        "layout_count": layout_count,
        "file_size_bytes": file_size_bytes,
        "flags": flags,
        "selection_blocked": bool(flags),
        "alternatives": [str(item) for item in alternatives or []],
    }


def _is_detail_only_file(
    *,
    path: str,
    raw_primary_candidate_count: int,
    raw_entity_count: int,
    dominant_entity_types: list[str],
) -> bool:
    """Heuristic: return True when the file is likely a detail sheet, not a floor plan.

    Signals used:
    - File name contains known detail keywords (DETALLE, DETALLES, etc.)
    - Very few primary geometry candidates relative to total entities
    """
    name_upper = Path(path).stem.upper()
    if any(token in name_upper for token in _DETAIL_ONLY_NAME_TOKENS):
        return True
    if raw_entity_count > 0 and raw_primary_candidate_count <= DETAIL_ONLY_MAX_PRIMARY_COUNT:
        annotation_heavy = any(
            t.upper() in ("MTEXT", "TEXT", "DIMENSION", "LEADER", "INSERT", "HATCH")
            for t in dominant_entity_types
        )
        if annotation_heavy:
            return True
    return False


def build_source_audit(
    candidate: Any,
    *,
    elements: list[Element25D] | None = None,
    accore_profile: dict[str, Any] | None = None,
    coordinate_band_cell_mm: float = 500_000.0,
    min_primary_elements: int = 20,
    max_annotation_ratio: float = 0.60,
) -> SourceAudit:
    elements = list(elements or [])
    selected_total = len(elements)
    selected_primary = sum(1 for element in elements if primary_geometry_role(element))
    bbox_like = sum(
        1 for element in elements if "bbox" in str(element.metadata.get("geometry_source") or "").lower()
    )
    bounds_mm, centroid_mm = _elements_bounds_and_centroid(elements)
    dominant_entity_types = _dominant_entity_types(elements)

    raw_entity_count = int(accore_profile.get("raw_entity_count") or 0) if accore_profile else 0
    raw_primary_candidate_count = (
        int(accore_profile.get("raw_primary_candidate_count") or 0) if accore_profile else selected_primary
    )
    raw_annotation_count = int(accore_profile.get("raw_annotation_count") or 0) if accore_profile else 0
    raw_bbox_only_count = int(accore_profile.get("raw_bbox_only_count") or 0) if accore_profile else bbox_like
    units_to_mm_factor = (
        float(accore_profile.get("units_to_mm_factor"))
        if accore_profile and accore_profile.get("units_to_mm_factor") is not None
        else None
    )
    if not dominant_entity_types and accore_profile:
        dominant_entity_types = [str(item) for item in accore_profile.get("dominant_entity_types") or []]

    if (
        (bounds_mm is None or centroid_mm is None)
        and accore_profile
        and accore_profile.get("dominant_cluster_bounds_mm")
        and accore_profile.get("dominant_cluster_centroid_mm")
    ):
        cluster_bounds = accore_profile["dominant_cluster_bounds_mm"]
        bounds_mm = (
            float(cluster_bounds[0]),
            float(cluster_bounds[1]),
            float(cluster_bounds[2]),
            float(cluster_bounds[3]),
        )
        cluster_centroid = accore_profile["dominant_cluster_centroid_mm"]
        centroid_mm = (float(cluster_centroid[0]), float(cluster_centroid[1]))

    if (
        (bounds_mm is None or centroid_mm is None)
        and accore_profile
        and accore_profile.get("bounds_mm")
        and accore_profile.get("centroid_mm")
    ):
        raw_bounds = accore_profile["bounds_mm"]
        bounds_mm = (float(raw_bounds[0]), float(raw_bounds[1]), float(raw_bounds[2]), float(raw_bounds[3]))
        raw_centroid = accore_profile["centroid_mm"]
        centroid_mm = (float(raw_centroid[0]), float(raw_centroid[1]))
    coordinate_band_key, coordinate_band = _coordinate_band(centroid_mm, cell_size_mm=coordinate_band_cell_mm)

    candidate_path = str(getattr(candidate, "path", "") or getattr(candidate, "rel_path", ""))
    file_size_bytes = None
    try:
        path_obj = Path(candidate_path)
        if path_obj.exists():
            file_size_bytes = path_obj.stat().st_size
    except Exception:
        file_size_bytes = None
    layout_count = int(accore_profile.get("layout_count") or accore_profile.get("paper_space_layout_count") or 0) if accore_profile else 0
    sanity_flags = selection_sanity_flags(
        path=candidate_path,
        raw_entity_count=raw_entity_count,
        layout_count=layout_count,
        file_size_bytes=file_size_bytes,
    )

    notes: list[str] = []
    if accore_profile and raw_entity_count > 0:
        annotation_ratio = (raw_annotation_count / raw_entity_count) if raw_entity_count > 0 else 0.0
        if annotation_ratio > max_annotation_ratio:
            status: AuditStatus = "annotation_noise"
            notes.append(f"annotation_ratio={annotation_ratio:.2f}")
        elif raw_primary_candidate_count == 0:
            status = "bbox_only"
            notes.append("sin geometria primaria util")
        else:
            status = "eligible"
            if raw_primary_candidate_count < min_primary_elements:
                notes.append(f"low_primary_count={raw_primary_candidate_count}")
    elif selected_total == 0:
        status = "extract_failed"
        notes.append("sin perfil ligero ni elementos extraidos")
    else:
        annotation_ratio = (raw_annotation_count / raw_entity_count) if raw_entity_count > 0 else 0.0
        if annotation_ratio > max_annotation_ratio:
            status = "annotation_noise"
            notes.append(f"annotation_ratio={annotation_ratio:.2f}")
        elif selected_primary == 0 or raw_primary_candidate_count == 0:
            status = "bbox_only"
            notes.append("sin geometria primaria util")
        else:
            status = "eligible"
            if selected_primary < min_primary_elements:
                notes.append(f"low_primary_count={selected_primary}")

    if sanity_flags:
        status = "needs_alignment"
        notes.extend(f"selection_sanity:{flag}" for flag in sanity_flags)

    detail_only = _is_detail_only_file(
        path=str(getattr(candidate, "rel_path", "") or getattr(candidate, "path", "")),
        raw_primary_candidate_count=raw_primary_candidate_count,
        raw_entity_count=raw_entity_count,
        dominant_entity_types=dominant_entity_types,
    )
    if detail_only and status == "eligible":
        status = "detail_only"
        notes.append("detected_as_detail_sheet")

    return SourceAudit(
        rel_path=str(candidate.rel_path),
        file_name=Path(str(candidate.rel_path)).name,
        suffix=str(candidate.suffix),
        issue_key=str(candidate.issue_key),
        cohort_id=str(candidate.cohort_id or candidate.issue_key),
        discipline=str(candidate.discipline.value),
        level_id=str(candidate.level_id),
        level_source=str(candidate.level_source),
        drawing_type=str(getattr(candidate, "drawing_type", "generic")),
        coordinate_band_key=coordinate_band_key,
        coordinate_band=coordinate_band,
        centroid_mm=centroid_mm,
        bounds_mm=bounds_mm,
        units_to_mm_factor=units_to_mm_factor,
        raw_entity_count=raw_entity_count,
        raw_primary_candidate_count=raw_primary_candidate_count,
        raw_annotation_count=raw_annotation_count,
        raw_bbox_only_count=raw_bbox_only_count,
        selected_total_count=selected_total,
        selected_primary_count=selected_primary,
        dominant_entity_types=dominant_entity_types,
        audit_status=status,
        detail_only=detail_only,
        notes=notes,
    )


def apply_coordinate_band_gating(
    audits: list[SourceAudit],
    *,
    required_disciplines: tuple[Any, ...],
) -> list[SourceAudit]:
    required_values = {
        discipline.value if hasattr(discipline, "value") else str(discipline)
        for discipline in required_disciplines
    }
    band_counts: Counter[tuple[int, int]] = Counter(
        audit.coordinate_band_key
        for audit in audits
        if audit.audit_status == "eligible"
        and audit.coordinate_band_key is not None
        and audit.discipline in required_values
    )
    if not band_counts:
        return audits
    dominant_band = band_counts.most_common(1)[0][0]

    gated: list[SourceAudit] = []
    for audit in audits:
        if (
            audit.audit_status == "eligible"
            and audit.coordinate_band_key is not None
            and audit.coordinate_band_key != dominant_band
        ):
            notes = list(audit.notes)
            notes.append("fuera de la banda dominante")
            gated.append(audit.model_copy(update={"audit_status": "needs_alignment", "notes": notes}))
        else:
            gated.append(audit)
    return gated


def build_pair_schedule(
    audits: list[SourceAudit],
    *,
    required_disciplines: tuple[Any, ...],
    pre_match_candidates: list[PreMatchCandidate] | None = None,
) -> list[PairScheduleItem]:
    required_values = {
        discipline.value if hasattr(discipline, "value") else str(discipline)
        for discipline in required_disciplines
    }
    schedule: list[PairScheduleItem] = []
    audit_by_rel = {audit.rel_path: audit for audit in audits}
    if pre_match_candidates:
        seen: set[tuple[str, str]] = set()
        for pair in pre_match_candidates:
            key = tuple(sorted((pair.file_a, pair.file_b)))
            if key in seen:
                continue
            seen.add(key)
            left = audit_by_rel.get(pair.file_a)
            right = audit_by_rel.get(pair.file_b)
            if left is None or right is None:
                continue
            if left.discipline not in required_values or right.discipline not in required_values:
                continue
            block_reason = None
            scheduled = True
            selection_reason = "documentary_auto_match"
            promotion_basis = None
            reason_codes = list(pair.reason_codes)
            updated_score = float(pair.score)
            if left.audit_status == "detail_only":
                scheduled = False
                block_reason = PairScheduleStatus.BLOCKED_DETAIL_ONLY
            elif right.audit_status == "detail_only":
                scheduled = False
                block_reason = PairScheduleStatus.BLOCKED_DETAIL_ONLY
            elif left.audit_status in ("needs_alignment",):
                scheduled = False
                block_reason = PairScheduleStatus.BLOCKED_ALIGNMENT
            elif right.audit_status in ("needs_alignment",):
                scheduled = False
                block_reason = PairScheduleStatus.BLOCKED_ALIGNMENT
            elif left.audit_status in ("bbox_only", "extract_failed", "annotation_noise"):
                scheduled = False
                block_reason = PairScheduleStatus.BLOCKED_NO_PRIMARY_GEOMETRY
            elif right.audit_status in ("bbox_only", "extract_failed", "annotation_noise"):
                scheduled = False
                block_reason = PairScheduleStatus.BLOCKED_NO_PRIMARY_GEOMETRY
            elif left.level_id != right.level_id:
                scheduled = False
                block_reason = PairScheduleStatus.BLOCKED_LEVEL_MISMATCH
            elif left.coordinate_band_key != right.coordinate_band_key:
                scheduled = False
                updated_score = max(updated_score - 0.15, 0.0)
                block_reason = PairScheduleStatus.BLOCKED_COORDINATE_MISMATCH
            else:
                updated_score = min(round(updated_score + 0.15, 3), 1.0)
                if pair.documentary_cohort_relation == "cross_cohort":
                    selection_reason = "promoted_from_coordinate_audit"
                    promotion_basis = "eligible + same_level + compatible_band + compatible_type"
                    if "audit_promoted" not in reason_codes:
                        reason_codes.append("audit_promoted")

            if pair.decision != "auto_comparable" and scheduled:
                if updated_score >= 0.75:
                    selection_reason = "promoted_from_coordinate_audit"
                    promotion_basis = "eligible + same_level + compatible_band + compatible_type"
                    if "audit_promoted" not in reason_codes:
                        reason_codes.append("audit_promoted")
                else:
                    scheduled = False
                    block_reason = PairScheduleStatus.BLOCKED_ROLE_MISSING

            schedule.append(
                PairScheduleItem(
                    cohort_id=left.cohort_id,
                    file_a=left.rel_path,
                    file_b=right.rel_path,
                    coordinate_band=left.coordinate_band if left.coordinate_band == right.coordinate_band else None,
                    level_ids=(left.level_id, right.level_id),
                    decision=pair.decision,
                    score=updated_score,
                    reason_codes=reason_codes,
                    selection_reason=selection_reason,
                    promotion_basis=promotion_basis,
                    documentary_cohort_relation=(
                        "same_cohort" if pair.documentary_cohort_relation == "same_cohort" else "cross_cohort_promoted"
                    ),
                    scheduled=scheduled,
                    block_reason=block_reason,
                )
            )
    else:
        ordered = sorted(audits, key=lambda item: (item.cohort_id, item.rel_path))
        for index, left in enumerate(ordered):
            if left.discipline not in required_values:
                continue
            for right in ordered[index + 1 :]:
                if right.cohort_id != left.cohort_id:
                    continue
                if right.discipline not in required_values or right.discipline == left.discipline:
                    continue
                block_reason = None
                scheduled = True
                if left.audit_status == "detail_only" or right.audit_status == "detail_only":
                    scheduled = False
                    block_reason = PairScheduleStatus.BLOCKED_DETAIL_ONLY
                elif left.audit_status in ("needs_alignment",):
                    scheduled = False
                    block_reason = PairScheduleStatus.BLOCKED_ALIGNMENT
                elif right.audit_status in ("needs_alignment",):
                    scheduled = False
                    block_reason = PairScheduleStatus.BLOCKED_ALIGNMENT
                elif left.audit_status in ("bbox_only", "extract_failed", "annotation_noise"):
                    scheduled = False
                    block_reason = PairScheduleStatus.BLOCKED_NO_PRIMARY_GEOMETRY
                elif right.audit_status in ("bbox_only", "extract_failed", "annotation_noise"):
                    scheduled = False
                    block_reason = PairScheduleStatus.BLOCKED_NO_PRIMARY_GEOMETRY
                elif left.coordinate_band_key != right.coordinate_band_key:
                    scheduled = False
                    block_reason = PairScheduleStatus.BLOCKED_COORDINATE_MISMATCH
                elif left.level_id != right.level_id:
                    scheduled = False
                    block_reason = PairScheduleStatus.BLOCKED_LEVEL_MISMATCH

                pair_score = 1.0 if scheduled else 0.0
                schedule.append(
                    PairScheduleItem(
                        cohort_id=left.cohort_id,
                        file_a=left.rel_path,
                        file_b=right.rel_path,
                        coordinate_band=left.coordinate_band if left.coordinate_band == right.coordinate_band else None,
                        level_ids=(left.level_id, right.level_id),
                        decision="auto_comparable" if scheduled else "not_comparable",
                        score=pair_score,
                        reason_codes=[] if scheduled else [block_reason or "unknown"],
                        selection_reason=(
                            PairScheduleStatus.READY_HIGH if pair_score >= 0.75
                            else PairScheduleStatus.READY_MEDIUM if pair_score >= 0.50
                            else PairScheduleStatus.READY_LOW
                        ) if scheduled else "same_cohort_schedule",
                        documentary_cohort_relation="same_cohort",
                        scheduled=scheduled,
                        block_reason=block_reason,
                    )
                )
    return schedule


def render_coordinate_audit_markdown(
    audits: list[SourceAudit],
    *,
    project_name: str,
    root: Path,
) -> str:
    status_counts = Counter(audit.audit_status for audit in audits)
    lines = [
        f"# Coordinate Audit - {project_name}",
        "",
        f"- Root: `{root.as_posix()}`",
        f"- Files audited: {len(audits)}",
        f"- Status mix: {_counter_label(status_counts)}",
        "",
        "## Reading Guide",
        "- `eligible` can enter the scheduled clash flow.",
        "- `needs_alignment`, `annotation_noise`, `bbox_only`, and `extract_failed` are technical blockers or low-trust inputs.",
        "",
        "## Sources",
        "| File | Discipline | Level | Drawing type | Status | Coordinate band | Raw primary | Raw annotation | Notes |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for audit in audits:
        lines.append(
            "| "
            f"`{audit.file_name}` | "
            f"{audit.discipline} | "
            f"`{audit.level_id}` | "
            f"`{audit.drawing_type}` | "
            f"`{audit.audit_status}` | "
            f"`{audit.coordinate_band or 'none'}` | "
            f"{audit.raw_primary_candidate_count} | "
            f"{audit.raw_annotation_count} | "
            f"{'; '.join(audit.notes) or '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_hotspot_markdown(
    incidents: list[Any],
    *,
    project_name: str,
    root: Path,
) -> str:
    lines = [
        f"# Hotspot Incidents - {project_name}",
        "",
        f"- Root: `{root.as_posix()}`",
        f"- Incident count: {len(incidents)}",
        "",
        "## Reading Guide",
        "- Hotspots show concentration zones, not final defendable clashes.",
        "- Use them to detect repeated noise, dense overlap areas, or candidate review regions.",
        "",
        "## Hotspots",
        "| Pair | Members | Level | Geometry | Center | Notes |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for incident in incidents:
        representative = incident.representative_conflict
        x, y = incident.plan_centroid_mm
        lines.append(
            "| "
            f"`{Path(incident.file_pair[0]).name} vs {Path(incident.file_pair[1]).name}` | "
            f"{incident.member_count} | "
            f"`{' / '.join(representative.level_ids)}` | "
            f"`{' / '.join(incident.geometry_sources)}` | "
            f"({round(x):,}, {round(y):,}) mm | "
            f"{'; '.join(representative.notes) or '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


def _counter_label(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{label}={count}" for label, count in counter.most_common())


def _coordinate_band(
    centroid_mm: tuple[float, float] | None,
    *,
    cell_size_mm: float,
) -> tuple[tuple[int, int] | None, str | None]:
    if centroid_mm is None:
        return (None, None)
    key = (
        int(math.floor(centroid_mm[0] / cell_size_mm)),
        int(math.floor(centroid_mm[1] / cell_size_mm)),
    )
    label = f"X~{centroid_mm[0] / 1_000_000.0:.2f}M, Y~{centroid_mm[1] / 1_000_000.0:.2f}M"
    return (key, label)


def _elements_bounds_and_centroid(
    elements: list[Element25D],
) -> tuple[tuple[float, float, float, float] | None, tuple[float, float] | None]:
    if not elements:
        return (None, None)
    primary_elements = [element for element in elements if primary_geometry_role(element)]
    points_source = primary_elements or elements
    xs: list[float] = []
    ys: list[float] = []
    for element in points_source:
        for x, y in element.footprint_coords_mm:
            xs.append(float(x))
            ys.append(float(y))
    if not xs or not ys:
        return (None, None)
    bounds = (min(xs), min(ys), max(xs), max(ys))
    centroid = ((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0)
    return (bounds, centroid)


def _dominant_entity_types(elements: list[Element25D]) -> list[str]:
    counts: Counter[str] = Counter()
    for element in elements:
        parts = str(element.source_ref).split("|")
        if len(parts) >= 3:
            counts[parts[2]] += 1
    return [entity_type for entity_type, _count in counts.most_common(5)]
