"""Helpers for fast, low-noise clash comparison runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from coordination.selection.level_inference import LevelResolution, infer_level_from_view_name
from coordination.core.models_25d import Discipline, Element25D
from coordination.core.nasas_paths import coordination_issue_key, discipline_from_nasas_relative_path
from coordination.core.registry import ProjectLevelRegistryDocument
from coordination.selection.source_selection import normalize_source_text, relative_posix

FAST_COMPARE_ANALYSIS_PROFILE = "fast_compare"
FAST_COMPARE_APS_PROFILE = "fast_compare_aps"
FAST_COMPARE_LOCAL_PROFILE = "fast_compare_local"
FAST_COMPARE_DISCIPLINES = (
    Discipline.ARCH,
    Discipline.STRUC,
    Discipline.MEP_ELEC,
    Discipline.MEP_PLUMBING,
    Discipline.MEP_HVAC,
)
FAST_COMPARE_LEVEL_THICKNESS_MM = {
    "CIMENTACION": 800.0,
    "SOTANO": 400.0,
    "NPT_P1": 300.0,
    "NPT_P2": 300.0,
    "TECHO": 400.0,
}
FAST_COMPARE_DEFAULT_THICKNESS_MM = 300.0
FAST_COMPARE_Z_CLAMP_MM = 2000.0
CAD_SUFFIXES = {".dwg", ".dxf"}


@dataclass(frozen=True)
class SourceCandidate:
    path: Path
    rel_path: str
    issue_key: str
    discipline: Discipline
    suffix: str
    level_id: str
    level_source: str
    cohort_id: str | None = None
    drawing_type: str = "generic"
    drawing_type_source: str = "heuristic"


@dataclass(frozen=True)
class PreMatchCandidate:
    file_a: str
    file_b: str
    file_name_a: str
    file_name_b: str
    issue_key_a: str
    issue_key_b: str
    discipline_a: str
    discipline_b: str
    level_id: str
    drawing_type_a: str
    drawing_type_b: str
    drawing_type_compatibility: float
    revision_proximity: float
    geometry_overlap_hint: float
    anchor_quality: float
    score: float
    decision: str
    reason_codes: tuple[str, ...]
    documentary_cohort_relation: str


@dataclass(frozen=True)
class CohortManifest:
    cohort_name: str
    source_files: frozenset[str]


@dataclass(frozen=True)
class AlignmentOverride:
    source_file: str
    translate_mm: tuple[float, float]
    level_id: str | None = None
    level_source: str | None = None
    note: str | None = None


def parse_include_disciplines(raw: str | None) -> tuple[Discipline, ...]:
    if not raw or not raw.strip():
        return FAST_COMPARE_DISCIPLINES
    out: list[Discipline] = []
    for token in raw.split(","):
        value = token.strip().upper()
        if not value:
            continue
        matched = next(
            (
                discipline
                for discipline in Discipline
                if value in {discipline.name.upper(), discipline.value.upper()}
            ),
            None,
        )
        if matched is None:
            raise ValueError(f"Disciplina no soportada en --include-disciplines: {token!r}")
        if matched not in out:
            out.append(matched)
    if not out:
        raise ValueError("--include-disciplines no produjo disciplinas validas")
    return tuple(out)


def build_source_candidates(
    media: Iterable[Path],
    *,
    root: Path,
    doc: ProjectLevelRegistryDocument,
    default_level_id: str,
) -> list[SourceCandidate]:
    candidates: list[SourceCandidate] = []
    for path in media:
        rel = relative_posix(path, root)
        view_text = "\n".join(part for part in (path.stem, path.name, rel, path.parent.name) if part)
        level_resolution = infer_level_from_view_name(
            view_text,
            doc=doc,
            default_level_id=default_level_id,
        )
        candidates.append(
            SourceCandidate(
                path=path,
                rel_path=rel,
                issue_key=coordination_issue_key(path, root),
                discipline=discipline_from_nasas_relative_path(rel.lower()),
                suffix=path.suffix.lower(),
                level_id=level_resolution.level_id,
                level_source=level_resolution.source,
                drawing_type=_infer_drawing_type(rel),
                drawing_type_source="path_heuristic",
            )
        )
    return candidates


def load_cohort_manifest(path: Path, *, root: Path) -> CohortManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    source_files = payload.get("source_files")
    if not isinstance(source_files, list) or not source_files:
        raise ValueError("cohort manifest requiere source_files no vacio")
    normalized: set[str] = set()
    for raw in source_files:
        if not isinstance(raw, str) or not raw.strip():
            continue
        file_path = Path(raw)
        rel = relative_posix(file_path if file_path.is_absolute() else root / file_path, root)
        normalized.add(normalize_source_text(rel))
    if not normalized:
        raise ValueError("cohort manifest no contiene source_files validos")
    cohort_name = str(payload.get("cohort_name") or payload.get("name") or path.stem)
    return CohortManifest(cohort_name=cohort_name, source_files=frozenset(normalized))


def load_alignment_manifest(path: Path, *, root: Path) -> dict[str, AlignmentOverride]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("alignment manifest requiere entries no vacio")

    overrides: dict[str, AlignmentOverride] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_source = entry.get("source_file")
        translate_mm = entry.get("translate_mm")
        level_id = entry.get("level_id")
        level_source = entry.get("level_source")
        if not isinstance(raw_source, str) or not raw_source.strip():
            continue
        if (
            not isinstance(translate_mm, list)
            or len(translate_mm) != 2
            or any(not isinstance(value, (int, float)) for value in translate_mm)
        ):
            raise ValueError("alignment manifest requiere translate_mm=[dx,dy] por entry")
        file_path = Path(raw_source)
        rel = relative_posix(file_path if file_path.is_absolute() else root / file_path, root)
        key = normalize_source_text(rel)
        overrides[key] = AlignmentOverride(
            source_file=rel,
            translate_mm=(float(translate_mm[0]), float(translate_mm[1])),
            level_id=str(level_id).strip() if isinstance(level_id, str) and level_id.strip() else None,
            level_source=(
                str(level_source).strip()
                if isinstance(level_source, str) and level_source.strip()
                else (
                    f"manual_manifest:{str(level_id).strip()}"
                    if isinstance(level_id, str) and level_id.strip()
                    else None
                )
            ),
            note=str(entry.get("note")) if entry.get("note") else None,
        )
    if not overrides:
        raise ValueError("alignment manifest no contiene entries validos")
    return overrides


def apply_manifest_selection(
    candidates: Iterable[SourceCandidate],
    *,
    manifest: CohortManifest,
) -> list[SourceCandidate]:
    selected: list[SourceCandidate] = []
    for candidate in candidates:
        if normalize_source_text(candidate.rel_path) not in manifest.source_files:
            continue
        selected.append(
            SourceCandidate(
                path=candidate.path,
                rel_path=candidate.rel_path,
                issue_key=candidate.issue_key,
                discipline=candidate.discipline,
                suffix=candidate.suffix,
                level_id=candidate.level_id,
                level_source=candidate.level_source,
                cohort_id=manifest.cohort_name,
                drawing_type=candidate.drawing_type,
                drawing_type_source=candidate.drawing_type_source,
            )
        )
    return selected


def compute_readiness_payload(
    candidates: Iterable[SourceCandidate],
    *,
    required_disciplines: tuple[Discipline, ...],
    pre_match_candidates: Iterable[PreMatchCandidate] | None = None,
) -> dict[str, object]:
    candidates = list(candidates)
    groups: dict[str, list[SourceCandidate]] = {}
    for candidate in candidates:
        groups.setdefault(candidate.issue_key, []).append(candidate)

    cohorts: list[dict[str, object]] = []
    comparable_issue_keys: list[str] = []
    availability = _discipline_issue_availability(groups)
    for issue_key, group in sorted(groups.items()):
        files_by_discipline: dict[str, list[str]] = {}
        levels_by_discipline: dict[str, list[str]] = {}
        for discipline in required_disciplines:
            members = [candidate for candidate in group if candidate.discipline == discipline]
            if members:
                files_by_discipline[discipline.value] = sorted(candidate.rel_path for candidate in members)
                levels_by_discipline[discipline.value] = sorted({candidate.level_id for candidate in members})
        missing = [discipline.value for discipline in required_disciplines if discipline.value not in files_by_discipline]
        shared_levels = _shared_levels(levels_by_discipline, required_disciplines)
        comparable = not missing and bool(shared_levels)
        if comparable:
            comparable_issue_keys.append(issue_key)
        nearest_candidates = {
            discipline: _nearest_issue_candidate(issue_key, availability.get(discipline, []))
            for discipline in missing
        }
        cohorts.append(
            {
                "issue_key": issue_key,
                "available_disciplines": sorted(files_by_discipline),
                "missing_disciplines": missing,
                "files_by_discipline": files_by_discipline,
                "levels_by_discipline": levels_by_discipline,
                "shared_levels": shared_levels,
                "is_comparable": comparable,
                "nearest_candidates": nearest_candidates,
            }
        )

    pair_candidates = list(pre_match_candidates or build_pre_match_candidates(candidates, required_disciplines=required_disciplines))
    auto_pairs = [candidate for candidate in pair_candidates if candidate.decision == "auto_comparable"]
    manual_pairs = [candidate for candidate in pair_candidates if candidate.decision == "manual_candidate"]
    rejected_pairs = [candidate for candidate in pair_candidates if candidate.decision == "not_comparable"]

    return {
        "required_disciplines": [discipline.value for discipline in required_disciplines],
        "candidate_count": len(candidates),
        "comparable_issue_keys": comparable_issue_keys,
        "cohorts": cohorts,
        "documentary_cohorts": cohorts,
        "blocking_matrix": _build_blocking_matrix(
            candidates,
            documentary_cohorts=cohorts,
            pair_candidates=pair_candidates,
            required_disciplines=required_disciplines,
        ),
        "auto_pair_candidates": [_pre_match_payload(candidate) for candidate in auto_pairs],
        "manual_pair_candidates": [_pre_match_payload(candidate) for candidate in manual_pairs],
        "promoted_pair_candidates": [],
        "decision_summary": {
            "auto_comparable_count": len(auto_pairs),
            "manual_candidate_count": len(manual_pairs),
            "not_comparable_count": len(rejected_pairs),
            "documentary_comparable_cohort_count": len(comparable_issue_keys),
            "cross_cohort_auto_count": sum(
                1 for candidate in auto_pairs if candidate.documentary_cohort_relation == "cross_cohort"
            ),
        },
    }


def build_pre_match_candidates(
    candidates: Iterable[SourceCandidate],
    *,
    required_disciplines: tuple[Discipline, ...],
) -> list[PreMatchCandidate]:
    candidates = list(candidates)
    required_values = {discipline.value for discipline in required_disciplines}
    out: list[PreMatchCandidate] = []
    for index, left in enumerate(candidates):
        if left.discipline.value not in required_values:
            continue
        for right in candidates[index + 1 :]:
            if right.discipline.value not in required_values:
                continue
            if right.discipline == left.discipline:
                continue
            discipline_match = 1.0
            level_match = 1.0 if left.level_id == right.level_id else 0.0
            drawing_type_match = _drawing_type_compatibility(
                left=left,
                right=right,
                level_id=left.level_id if left.level_id == right.level_id else None,
            )
            geometry_overlap_hint = _geometry_overlap_hint(
                left=left,
                right=right,
                level_match=level_match,
                drawing_type_match=drawing_type_match,
            )
            revision_proximity = _revision_proximity(left.issue_key, right.issue_key)
            anchor_quality = min(_anchor_quality(left), _anchor_quality(right))
            score = round(
                (0.25 * discipline_match)
                + (0.25 * level_match)
                + (0.20 * drawing_type_match)
                + (0.15 * geometry_overlap_hint)
                + (0.10 * revision_proximity)
                + (0.05 * anchor_quality),
                3,
            )
            reason_codes = _pre_match_reason_codes(
                left=left,
                right=right,
                level_match=level_match,
                drawing_type_match=drawing_type_match,
                revision_proximity=revision_proximity,
                score=score,
            )
            if score >= 0.75:
                decision = "auto_comparable"
            elif score >= 0.55:
                decision = "manual_candidate"
            else:
                decision = "not_comparable"
            ordered = sorted((left, right), key=lambda item: item.rel_path)
            out.append(
                PreMatchCandidate(
                    file_a=ordered[0].rel_path,
                    file_b=ordered[1].rel_path,
                    file_name_a=ordered[0].path.name,
                    file_name_b=ordered[1].path.name,
                    issue_key_a=ordered[0].issue_key,
                    issue_key_b=ordered[1].issue_key,
                    discipline_a=ordered[0].discipline.value,
                    discipline_b=ordered[1].discipline.value,
                    level_id=left.level_id if left.level_id == right.level_id else "mixed",
                    drawing_type_a=ordered[0].drawing_type,
                    drawing_type_b=ordered[1].drawing_type,
                    drawing_type_compatibility=drawing_type_match,
                    revision_proximity=revision_proximity,
                    geometry_overlap_hint=geometry_overlap_hint,
                    anchor_quality=anchor_quality,
                    score=score,
                    decision=decision,
                    reason_codes=tuple(reason_codes),
                    documentary_cohort_relation=(
                        "same_cohort" if ordered[0].issue_key == ordered[1].issue_key else "cross_cohort"
                    ),
                )
            )
    out.sort(key=lambda item: (-item.score, item.level_id, item.file_a, item.file_b))
    return out


def select_comparable_candidates(
    candidates: Iterable[SourceCandidate],
    *,
    comparable_issue_keys: Iterable[str],
) -> list[SourceCandidate]:
    allowed = set(comparable_issue_keys)
    out: list[SourceCandidate] = []
    for candidate in candidates:
        if candidate.issue_key not in allowed:
            continue
        out.append(
            SourceCandidate(
                path=candidate.path,
                rel_path=candidate.rel_path,
                issue_key=candidate.issue_key,
                discipline=candidate.discipline,
                suffix=candidate.suffix,
                level_id=candidate.level_id,
                level_source=candidate.level_source,
                cohort_id=candidate.issue_key,
                drawing_type=candidate.drawing_type,
                drawing_type_source=candidate.drawing_type_source,
            )
        )
    return out


def select_preferred_candidates(
    candidates: Iterable[SourceCandidate],
    *,
    pair_candidates: Iterable[PreMatchCandidate],
) -> list[SourceCandidate]:
    candidates = list(candidates)
    candidate_by_rel = {candidate.rel_path: candidate for candidate in candidates}
    auto_pairs = [pair for pair in pair_candidates if pair.decision == "auto_comparable"]
    if not auto_pairs:
        return []

    selected_pairs = _select_anchor_pairs(auto_pairs, candidate_by_rel)
    file_to_group: dict[str, str] = {}
    for pair in selected_pairs:
        group_id = _comparison_group_id(pair)
        for rel_path in (pair.file_a, pair.file_b):
            file_to_group.setdefault(rel_path, group_id)

    selected: list[SourceCandidate] = []
    for rel_path, group_id in sorted(file_to_group.items()):
        candidate = candidate_by_rel.get(rel_path)
        if candidate is None:
            continue
        selected.append(
            SourceCandidate(
                path=candidate.path,
                rel_path=candidate.rel_path,
                issue_key=candidate.issue_key,
                discipline=candidate.discipline,
                suffix=candidate.suffix,
                level_id=candidate.level_id,
                level_source=candidate.level_source,
                cohort_id=group_id,
                drawing_type=candidate.drawing_type,
                drawing_type_source=candidate.drawing_type_source,
            )
        )
    return selected


def finalize_readiness_payload(
    readiness_payload: dict[str, object],
    *,
    audits: Iterable[dict[str, object]],
    pair_schedule: Iterable[dict[str, object]],
) -> dict[str, object]:
    payload = dict(readiness_payload)
    eligible_files = [
        {
            "file": str(item.get("rel_path") or ""),
            "discipline": str(item.get("discipline") or ""),
            "level_id": str(item.get("level_id") or ""),
            "coordinate_band": item.get("coordinate_band"),
            "audit_status": str(item.get("audit_status") or "unknown"),
        }
        for item in audits
        if str(item.get("audit_status") or "") == "eligible"
    ]
    promoted_pairs = [
        item
        for item in pair_schedule
        if bool(item.get("scheduled")) and str(item.get("selection_reason") or "") == "promoted_from_coordinate_audit"
    ]
    manual_pairs = list(payload.get("manual_pair_candidates") or [])
    payload["promoted_pair_candidates"] = promoted_pairs
    payload["audit_promotion_summary"] = {
        "eligible_files": eligible_files,
        "promoted_pair_count": len(promoted_pairs),
    }
    decision_summary = dict(payload.get("decision_summary") or {})
    decision_summary["promoted_pair_count"] = len(promoted_pairs)
    decision_summary["eligible_file_count"] = len(eligible_files)
    decision_summary["manual_candidate_count"] = len(manual_pairs)
    payload["decision_summary"] = decision_summary
    return payload


def suppress_visual_backups(candidates: Iterable[SourceCandidate]) -> list[SourceCandidate]:
    cad_keys = {
        (candidate.cohort_id or candidate.issue_key, candidate.discipline, candidate.level_id)
        for candidate in candidates
        if candidate.suffix in CAD_SUFFIXES
    }
    selected: list[SourceCandidate] = []
    for candidate in candidates:
        if candidate.suffix == ".pdf" and (
            candidate.cohort_id or candidate.issue_key,
            candidate.discipline,
            candidate.level_id,
        ) in cad_keys:
            continue
        selected.append(candidate)
    return selected


def normalize_fast_compare_element(
    element: Element25D,
    *,
    file_level_id: str,
    cohort_id: str,
    level_source: str,
) -> Element25D:
    metadata = dict(element.metadata)
    metadata["file_level_id"] = file_level_id
    metadata["cohort_id"] = cohort_id
    metadata.setdefault("geometry_role", "primary")
    if metadata["geometry_role"] != "primary":
        metadata.setdefault("suppression_reason", "non_primary_geometry")

    z_data = element.z_data
    clamp = abs(z_data.z_ref_raw_mm) > FAST_COMPARE_Z_CLAMP_MM or z_data.thickness_mm > FAST_COMPARE_Z_CLAMP_MM
    if clamp:
        z_data = z_data.model_copy(
            update={
                "level_id": file_level_id,
                "z_ref_raw_mm": 0.0,
                "thickness_mm": FAST_COMPARE_LEVEL_THICKNESS_MM.get(
                    file_level_id,
                    FAST_COMPARE_DEFAULT_THICKNESS_MM,
                ),
                "reference_point": "bottom",
            }
        )
        metadata["level_assignment_source"] = "clamped_2d_default"
    else:
        metadata["level_assignment_source"] = level_source

    return element.model_copy(update={"z_data": z_data, "metadata": metadata})


def render_readiness_markdown(
    payload: dict[str, object],
    *,
    project_name: str,
    root: Path,
) -> str:
    lines = [
        f"# Comparison Readiness Report - {project_name or 'Proyecto'}",
        "",
        f"- Root: `{root.as_posix()}`",
        f"- Required disciplines: {', '.join(payload['required_disciplines'])}",
        f"- Candidate files: {payload['candidate_count']}",
        f"- Comparable issue keys: {len(payload['comparable_issue_keys'])}",
        f"- Documentary auto pairs: {len(payload.get('auto_pair_candidates') or [])}",
        f"- Documentary manual pairs: {len(payload.get('manual_pair_candidates') or [])}",
        "",
        "## Documentary Cohorts",
    ]
    for cohort in payload["documentary_cohorts"]:
        issue_key = cohort["issue_key"]
        comparable = "yes" if cohort["is_comparable"] else "no"
        lines.append(f"- `{issue_key}` comparable: {comparable}")
        lines.append(f"  disciplines: {', '.join(cohort['available_disciplines']) or 'none'}")
        lines.append(f"  shared levels: {', '.join(cohort['shared_levels']) or 'none'}")
        if cohort["missing_disciplines"]:
            lines.append(f"  missing: {', '.join(cohort['missing_disciplines'])}")
        nearest = cohort["nearest_candidates"]
        for discipline, candidate in sorted(nearest.items()):
            if candidate:
                lines.append(f"  nearest {discipline}: {candidate}")
    lines.extend(
        [
            "",
            "## Blocking Matrix",
            "| File | Discipline | Level | Drawing type | Documentary status | Reasons | Action |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in payload.get("blocking_matrix") or []:
        lines.append(
            "| "
            f"`{Path(item['file']).name}` | "
            f"{item['discipline']} | "
            f"`{item['canonical_level']}` | "
            f"`{item['drawing_type']}` | "
            f"`{item['documentary_status']}` | "
            f"{', '.join(item['blocking_reason_codes']) or '-'} | "
            f"{item['recommended_action']} |"
        )
    lines.extend(
        [
            "",
            "## Documentary Candidate Pairs",
            "| Pair | Level | Decision | Score | Types | Cohort relation | Reasons |",
            "| --- | --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for item in (payload.get("auto_pair_candidates") or [])[:12] + (payload.get("manual_pair_candidates") or [])[:12]:
        lines.append(
            "| "
            f"`{Path(item['file_a']).name} vs {Path(item['file_b']).name}` | "
            f"`{item['level_id']}` | "
            f"`{item['decision']}` | "
            f"{item['score']:.3f} | "
            f"`{item['drawing_type_a']} / {item['drawing_type_b']}` | "
            f"`{item['documentary_cohort_relation']}` | "
            f"{', '.join(item['reason_codes']) or '-'} |"
        )
    audit_summary = payload.get("audit_promotion_summary") or {}
    eligible_files = audit_summary.get("eligible_files") or []
    if eligible_files:
        lines.extend(
            [
                "",
                "## La comparabilidad documental falló, pero el Coordinate Audit promovió pares comparables",
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
    promoted_pairs = payload.get("promoted_pair_candidates") or []
    if promoted_pairs:
        lines.extend(
            [
                "",
                "## Audit-Promoted Pairs",
                "| Pair | Selection reason | Levels | Score | Basis |",
                "| --- | --- | --- | ---: | --- |",
            ]
        )
        for item in promoted_pairs:
            lines.append(
                "| "
                f"`{Path(item['file_a']).name} vs {Path(item['file_b']).name}` | "
                f"`{item['selection_reason']}` | "
                f"`{' / '.join(item['level_ids'])}` | "
                f"{float(item.get('score') or 0.0):.3f} | "
                f"{item.get('promotion_basis') or '-'} |"
            )
    lines.append("")
    return "\n".join(lines)


def primary_geometry_role(element: Element25D) -> bool:
    return str(element.metadata.get("geometry_role") or "primary") == "primary"


def _pre_match_payload(candidate: PreMatchCandidate) -> dict[str, object]:
    return {
        "file_a": candidate.file_a,
        "file_b": candidate.file_b,
        "file_name_a": candidate.file_name_a,
        "file_name_b": candidate.file_name_b,
        "issue_key_a": candidate.issue_key_a,
        "issue_key_b": candidate.issue_key_b,
        "discipline_a": candidate.discipline_a,
        "discipline_b": candidate.discipline_b,
        "level_id": candidate.level_id,
        "drawing_type_a": candidate.drawing_type_a,
        "drawing_type_b": candidate.drawing_type_b,
        "drawing_type_compatibility": candidate.drawing_type_compatibility,
        "revision_proximity": candidate.revision_proximity,
        "geometry_overlap_hint": candidate.geometry_overlap_hint,
        "anchor_quality": candidate.anchor_quality,
        "score": candidate.score,
        "decision": candidate.decision,
        "reason_codes": list(candidate.reason_codes),
        "documentary_cohort_relation": candidate.documentary_cohort_relation,
    }


def _select_anchor_pairs(
    auto_pairs: list[PreMatchCandidate],
    candidate_by_rel: dict[str, SourceCandidate],
) -> list[PreMatchCandidate]:
    grouped: dict[tuple[str, str], list[PreMatchCandidate]] = {}
    for pair in auto_pairs:
        disciplines = tuple(sorted((pair.discipline_a, pair.discipline_b)))
        grouped.setdefault((disciplines[0] + "|" + disciplines[1], pair.level_id), []).append(pair)

    selected: list[PreMatchCandidate] = []
    for (_disciplines, _level_id), pairs in sorted(grouped.items()):
        arch_files = {
            rel_path
            for pair in pairs
            for rel_path, discipline in (
                (pair.file_a, pair.discipline_a),
                (pair.file_b, pair.discipline_b),
            )
            if discipline == Discipline.ARCH.value
        }
        if arch_files:
            ranked = sorted(
                (
                    (
                        rel_path,
                        round(sum(pair.score for pair in pairs if rel_path in {pair.file_a, pair.file_b}), 3),
                        _drawing_type_rank(candidate_by_rel[rel_path].drawing_type if rel_path in candidate_by_rel else "generic"),
                    )
                    for rel_path in arch_files
                ),
                key=lambda item: (-item[1], -item[2], item[0]),
            )
            chosen_arch = ranked[0][0]
            chosen_pairs = [pair for pair in pairs if chosen_arch in {pair.file_a, pair.file_b}]
            by_counterpart: dict[str, PreMatchCandidate] = {}
            for pair in chosen_pairs:
                counterpart = Path(pair.file_b if pair.file_a == chosen_arch else pair.file_a).name
                current = by_counterpart.get(counterpart)
                if current is None or pair.score > current.score:
                    by_counterpart[counterpart] = pair
            selected.extend(by_counterpart.values())
        else:
            selected.extend(pairs)
    selected.sort(key=lambda item: (-item.score, item.level_id, item.file_a, item.file_b))
    return selected


def _comparison_group_id(pair: PreMatchCandidate) -> str:
    arch_name = next(
        (
            Path(rel_path).stem
            for rel_path, discipline in ((pair.file_a, pair.discipline_a), (pair.file_b, pair.discipline_b))
            if discipline == Discipline.ARCH.value
        ),
        Path(pair.file_a).stem,
    )
    normalized = "".join(char.lower() if char.isalnum() else "_" for char in arch_name).strip("_")
    return f"prematch_{pair.level_id.lower()}_{normalized[:40]}"


def _drawing_type_rank(label: str) -> int:
    return {
        "floor_plan": 7,
        "upper_floor_plan": 6,
        "base_plan": 5,
        "formwork": 6,
        "ground_slab": 6,
        "intermediate_slab": 6,
        "foundation": 6,
        "roof_structure": 6,
        "basement_structure": 6,
        "structural_plan": 5,
        "generic_plan": 3,
        "detail": 1,
        "notes": 0,
        "schedule": 0,
        "generic": 2,
    }.get(label, 2)


def _build_blocking_matrix(
    candidates: list[SourceCandidate],
    *,
    documentary_cohorts: list[dict[str, object]],
    pair_candidates: list[PreMatchCandidate],
    required_disciplines: tuple[Discipline, ...],
) -> list[dict[str, object]]:
    cohort_status = {str(item["issue_key"]): item for item in documentary_cohorts}
    pair_lookup: dict[str, list[PreMatchCandidate]] = {}
    for pair in pair_candidates:
        pair_lookup.setdefault(pair.file_a, []).append(pair)
        pair_lookup.setdefault(pair.file_b, []).append(pair)
    out: list[dict[str, object]] = []
    required_values = {discipline.value for discipline in required_disciplines}
    for candidate in sorted(candidates, key=lambda item: item.rel_path):
        cohort = cohort_status.get(candidate.issue_key) or {}
        reasons = []
        missing = list(cohort.get("missing_disciplines") or [])
        if missing:
            reasons.append("missing_required_discipline")
            reasons.append("single_discipline_cohort")
        if not list(cohort.get("shared_levels") or []):
            reasons.append("no_shared_documentary_level")
        best_pairs = sorted(pair_lookup.get(candidate.rel_path, []), key=lambda item: (-item.score, item.file_b))
        if best_pairs:
            reasons.extend(code for code in best_pairs[0].reason_codes if code not in reasons)
        if candidate.discipline.value not in required_values:
            reasons.append("discipline_not_requested")
        out.append(
            {
                "file": candidate.rel_path,
                "discipline": candidate.discipline.value,
                "canonical_level": candidate.level_id,
                "drawing_type": candidate.drawing_type,
                "documentary_status": "documentary_comparable" if bool(cohort.get("is_comparable")) else "documentary_blocked",
                "blocking_reason_codes": reasons,
                "nearest_alternative_candidates": [
                    {
                        "file": pair.file_b if pair.file_a == candidate.rel_path else pair.file_a,
                        "score": pair.score,
                        "decision": pair.decision,
                    }
                    for pair in best_pairs[:3]
                ],
                "recommended_action": _blocking_action(reasons),
            }
        )
    return out


def _blocking_action(reason_codes: list[str]) -> str:
    if "drawing_type_incompatible" in reason_codes:
        return "Validar tipo de plano compatible antes de programar clash final."
    if "missing_required_discipline" in reason_codes:
        return "Cruzar el archivo con una disciplina complementaria fuera de la cohorte documental."
    if "cross_revision_pair_required" in reason_codes:
        return "Permitir emparejamiento cross-revision y confirmar ancla geometrica en audit."
    if "manual_pairing_needed" in reason_codes:
        return "Mantener como candidato manual y revisar con coordinate audit."
    return "Revisar compatibilidad documental y geometrica antes de descartar el archivo."


def _infer_drawing_type(rel_path: str) -> str:
    text = rel_path.lower()
    file_name = Path(rel_path).name.lower()
    if any(token in text for token in ("door schedule", "schedule")):
        return "schedule"
    if "notas estructurales" in text or "notas" in file_name:
        return "notes"
    if any(token in text for token in ("detalle", "det.", "details", "typical", "tipicos", "refuerzo", "vigas")):
        return "detail"
    if "upperfloor" in text or "upper floor" in text or "upper-floor" in text:
        return "upper_floor_plan"
    if "planta pisos" in text:
        return "floor_plan"
    if "id-base" in text or "id base" in text or ("base" in file_name and "reference detail" not in text):
        return "base_plan"
    if "encofrado" in text:
        return "formwork"
    if "losa" in text and "techo sotano" in text:
        return "basement_structure"
    if "losa" in text and "piso sobre terreno" in text:
        return "ground_slab"
    if "entrepiso" in text:
        return "intermediate_slab"
    if "cimientos" in text or "ciment" in text:
        return "foundation"
    if "techo" in text:
        return "roof_structure"
    if "planta est." in text:
        return "structural_plan"
    if "planta" in text:
        return "generic_plan"
    return "generic"


def _drawing_type_compatibility(
    *,
    left: SourceCandidate,
    right: SourceCandidate,
    level_id: str | None,
) -> float:
    pair = {
        (left.discipline.value, left.drawing_type),
        (right.discipline.value, right.drawing_type),
    }
    if level_id is None:
        return 0.15
    if {left.discipline.value, right.discipline.value} == {Discipline.ARCH.value, Discipline.STRUC.value}:
        arch_type = left.drawing_type if left.discipline == Discipline.ARCH else right.drawing_type
        struc_type = left.drawing_type if left.discipline == Discipline.STRUC else right.drawing_type
        arch_score = {
            "floor_plan": 1.0,
            "upper_floor_plan": 0.95,
            "base_plan": 0.62,
            "generic_plan": 0.50,
            "detail": 0.10,
            "notes": 0.0,
            "schedule": 0.0,
        }.get(arch_type, 0.35)
        structural_score_map = {
            "NPT_P1": {"formwork": 1.0, "ground_slab": 0.95, "structural_plan": 0.75, "detail": 0.15},
            "NPT_P2": {"intermediate_slab": 1.0, "structural_plan": 0.80, "detail": 0.15},
            "CIMENTACION": {"foundation": 1.0, "detail": 0.15},
            "SOTANO": {"basement_structure": 1.0, "foundation": 0.45, "detail": 0.15},
            "TECHO": {"roof_structure": 1.0, "detail": 0.15},
        }
        structural_score = structural_score_map.get(level_id, {}).get(struc_type, 0.30)
        return round(min(1.0, arch_score * structural_score if structural_score < 0.7 else (0.55 * arch_score) + (0.45 * structural_score)), 3)
    if "detail" in {left.drawing_type, right.drawing_type} or "notes" in {left.drawing_type, right.drawing_type}:
        return 0.20
    return 0.65


def _geometry_overlap_hint(
    *,
    left: SourceCandidate,
    right: SourceCandidate,
    level_match: float,
    drawing_type_match: float,
) -> float:
    if level_match <= 0.0:
        return 0.0
    if drawing_type_match >= 0.9:
        return 1.0
    if drawing_type_match >= 0.7:
        return 0.8
    if left.issue_key == right.issue_key:
        return 0.6
    return 0.45


def _revision_proximity(issue_key_a: str, issue_key_b: str) -> float:
    date_a = _parse_issue_date(issue_key_a)
    date_b = _parse_issue_date(issue_key_b)
    if date_a is None or date_b is None:
        return 0.5
    delta_days = abs((date_a - date_b).days)
    if delta_days <= 45:
        return 1.0
    if delta_days <= 180:
        return 0.85
    if delta_days <= 365:
        return 0.7
    if delta_days <= 730:
        return 0.55
    if delta_days <= 1200:
        return 0.35
    return 0.2


def _anchor_quality(candidate: SourceCandidate) -> float:
    score = 0.55
    if candidate.suffix in CAD_SUFFIXES:
        score += 0.20
    if not str(candidate.level_source).startswith("default"):
        score += 0.15
    if candidate.drawing_type not in {"detail", "notes", "schedule", "generic"}:
        score += 0.10
    return min(score, 1.0)


def _pre_match_reason_codes(
    *,
    left: SourceCandidate,
    right: SourceCandidate,
    level_match: float,
    drawing_type_match: float,
    revision_proximity: float,
    score: float,
) -> list[str]:
    reason_codes: list[str] = []
    if left.issue_key != right.issue_key:
        reason_codes.append("cross_revision_pair_required")
    if level_match <= 0.0:
        reason_codes.append("no_shared_documentary_level")
    if drawing_type_match < 0.40:
        reason_codes.append("drawing_type_incompatible")
    if score < 0.75:
        reason_codes.append("manual_pairing_needed")
    if revision_proximity < 0.6 and "cross_revision_pair_required" not in reason_codes:
        reason_codes.append("cross_revision_pair_required")
    return reason_codes


def _shared_levels(
    levels_by_discipline: dict[str, list[str]],
    required_disciplines: tuple[Discipline, ...],
) -> list[str]:
    shared: set[str] | None = None
    for discipline in required_disciplines:
        levels = set(levels_by_discipline.get(discipline.value, []))
        if not levels:
            return []
        shared = levels if shared is None else shared & levels
    return sorted(shared or [])


def _discipline_issue_availability(
    groups: dict[str, list[SourceCandidate]],
) -> dict[str, list[tuple[str, date | None]]]:
    availability: dict[str, list[tuple[str, date | None]]] = {}
    for issue_key, group in groups.items():
        issue_date = _parse_issue_date(issue_key)
        for discipline in {candidate.discipline.value for candidate in group}:
            availability.setdefault(discipline, []).append((issue_key, issue_date))
    return availability


def _nearest_issue_candidate(
    current_issue_key: str,
    options: list[tuple[str, date | None]],
) -> str | None:
    if not options:
        return None
    current_date = _parse_issue_date(current_issue_key)
    if current_date is not None:
        dated = [item for item in options if item[1] is not None]
        if dated:
            best = min(dated, key=lambda item: (abs((item[1] - current_date).days), item[0]))
            return best[0]
    return sorted(item[0] for item in options)[0]


def _parse_issue_date(issue_key: str) -> date | None:
    if not issue_key.startswith("d:") or len(issue_key) != 10:
        return None
    try:
        return date(
            int(issue_key[2:6]),
            int(issue_key[6:8]),
            int(issue_key[8:10]),
        )
    except ValueError:
        return None
