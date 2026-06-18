"""Generalized fast-compare clash pipeline for the coordination service.

Accepts uploaded files directly (no NASAS directory structure required).
Produces the result dict that clash_workflow_service.ensure_ingested() expects:
  {
    "report": {coordination_report_context},
    "artifacts": {
      "primary_incidents": {"incidents": [...]},
      "output_dir": "/path/to/run/dir"
    }
  }
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

from coordination.core.clash import ClashConflict, group_conflicts_into_incidents
from coordination.core.models_25d import Discipline, Element25D, ProjectLevel
from coordination.core.nasas_paths import COORDINATION_ISSUE_METADATA_KEY
from coordination.core.registry import ProjectLevelRegistryDocument, ProjectLevelRegistry
from coordination.extraction.from_dwg_accore import (
    extract_elements_from_accore_payload,
    load_accore_payload_via_accore,
    profile_accore_payload,
)
from coordination.extraction.from_dwg_ezdxf import extract_elements_from_dwg
from coordination.reporting.reporting import build_coordination_report_context
from coordination.selection.coordinate_audit import (
    apply_coordinate_band_gating,
    build_pair_schedule,
    build_source_audit,
)
from coordination.selection.fast_compare import (
    FAST_COMPARE_ANALYSIS_PROFILE,
    SourceCandidate,
    build_pre_match_candidates,
    compute_readiness_payload,
    finalize_readiness_payload,
    normalize_fast_compare_element,
    primary_geometry_role,
    select_preferred_candidates,
    suppress_visual_backups,
)
from coordination.selection.level_inference import infer_level_from_view_name
from coordination import clash_pairs

logger = logging.getLogger("dupla.coordination.service.pipeline")

# Backend discipline_bucket → motor Discipline enum
_BUCKET_TO_DISCIPLINE: dict[str, Discipline] = {
    "arquitectura": Discipline.ARCH,
    "estructura": Discipline.STRUC,
    "electrica": Discipline.MEP_ELEC,
    "mecanica": Discipline.MEP_HVAC,
    "plomeria": Discipline.MEP_PLUMBING,
}

_DEFAULT_LEVEL_ID = "NPT_P1"
_SINGLE_COHORT = "main"


@dataclass(frozen=True)
class FileInput:
    """One uploaded CAD file ready to be processed."""

    path: Path
    original_name: str
    discipline_bucket: str


@dataclass
class PipelineConfig:
    max_dwg_entities: int = 350
    min_dwg_area_mm2: float = 40_000.0
    primary_min_plan_area_mm2: float = 10_000.0
    coordinate_band_cell_mm: float = 500_000.0
    max_workers: int = 2
    accore_timeout_seconds: int = 240
    strict_levels: bool = False
    cache_root: Path | None = None


def _bucket_to_discipline(bucket: str) -> Discipline:
    disc = _BUCKET_TO_DISCIPLINE.get(bucket.lower().strip())
    if disc is None:
        raise ValueError(f"Disciplina no soportada: {bucket!r}")
    return disc


def _build_default_doc(project_name: str) -> ProjectLevelRegistryDocument:
    return ProjectLevelRegistryDocument(
        project_name=project_name,
        levels=[
            ProjectLevel(
                id=_DEFAULT_LEVEL_ID,
                name="Planta 1",
                offset_to_project_zero_mm=0.0,
            )
        ],
    )


def _build_candidates(
    inputs: list[FileInput],
    doc: ProjectLevelRegistryDocument,
) -> list[SourceCandidate]:
    candidates: list[SourceCandidate] = []
    for inp in inputs:
        discipline = _bucket_to_discipline(inp.discipline_bucket)
        view_text = inp.original_name
        level_resolution = infer_level_from_view_name(
            view_text,
            doc=doc,
            default_level_id=_DEFAULT_LEVEL_ID,
        )
        candidates.append(
            SourceCandidate(
                path=inp.path,
                rel_path=inp.original_name,
                issue_key="upload",
                discipline=discipline,
                suffix=inp.path.suffix.lower(),
                level_id=level_resolution.level_id,
                level_source=level_resolution.source,
                cohort_id=_SINGLE_COHORT,
                drawing_type="generic",
                drawing_type_source="api_metadata",
            )
        )
    return candidates


def _tag_elements(
    elements: Iterable[Element25D],
    *,
    issue_key: str,
    file_name: str,
    geometry_source: str | None = None,
    geometry_quality: str | None = None,
    level_assignment_source: str | None = None,
) -> list[Element25D]:
    tagged: list[Element25D] = []
    for element in elements:
        metadata = dict(element.metadata)
        metadata[COORDINATION_ISSUE_METADATA_KEY] = issue_key
        metadata.setdefault("file", file_name)
        if geometry_source is not None:
            metadata["geometry_source"] = geometry_source
        if geometry_quality is not None:
            metadata["geometry_quality"] = geometry_quality
        if level_assignment_source is not None:
            metadata["level_assignment_source"] = level_assignment_source
        tagged.append(element.model_copy(update={"metadata": metadata}))
    return tagged


def _profile_candidates(
    candidates: list[SourceCandidate],
    cache_root: Path,
    timeout_seconds: int,
    max_workers: int,
) -> dict[str, dict[str, Any]]:
    dwg_candidates = [c for c in candidates if c.suffix == ".dwg"]
    if not dwg_candidates:
        return {}

    def _worker(candidate: SourceCandidate) -> tuple[str, dict[str, Any]]:
        try:
            payload_result = load_accore_payload_via_accore(
                candidate.path,
                cache_root=cache_root / "accore",
                accoreconsole_path=None,
                extractor_dll=None,
                timeout_seconds=timeout_seconds,
            )
            profile = profile_accore_payload(payload_result.payload) if payload_result.payload else None
            return (
                candidate.rel_path,
                {"payload": payload_result.payload, "profile": profile, "cache_hit": payload_result.cache_hit},
            )
        except Exception as exc:
            logger.warning("Accore profile failed for %s: %s", candidate.path.name, exc)
            return (candidate.rel_path, {"payload": None, "profile": None, "cache_hit": False})

    results: dict[str, dict[str, Any]] = {}
    n = max(1, max_workers)
    if n == 1 or len(dwg_candidates) == 1:
        for c in dwg_candidates:
            rel, entry = _worker(c)
            results[rel] = entry
    else:
        with ThreadPoolExecutor(max_workers=n) as executor:
            futures = {executor.submit(_worker, c): c.rel_path for c in dwg_candidates}
            for future in as_completed(futures):
                rel, entry = future.result()
                results[rel] = entry
    return results


def _extract_elements_for_candidate(
    candidate: SourceCandidate,
    profiled_payloads: dict[str, dict[str, Any]],
    config: PipelineConfig,
) -> list[Element25D]:
    if candidate.suffix == ".dwg":
        payload = profiled_payloads.get(candidate.rel_path, {}).get("payload")
        if payload:
            elements = extract_elements_from_accore_payload(
                payload,
                path=candidate.path,
                discipline=candidate.discipline,
                level_id=candidate.level_id,
                translation_mm=(0.0, 0.0),
                max_entities=config.max_dwg_entities,
                min_area_mm2=config.min_dwg_area_mm2,
                z_thickness_mm=250.0,
                z_ref_mm=None,
            )
            if elements:
                return _tag_elements(
                    elements,
                    issue_key=candidate.issue_key,
                    file_name=candidate.path.name,
                    level_assignment_source=candidate.level_source,
                )

        # Fallback: ezdxf (binary DWG will be skipped gracefully)
        logger.info("Falling back to ezdxf for %s", candidate.path.name)
        elements = extract_elements_from_dwg(
            candidate.path,
            candidate.discipline,
            level_id=candidate.level_id,
            translation_mm=(0.0, 0.0),
            min_area_mm2=config.min_dwg_area_mm2,
            max_entities=config.max_dwg_entities,
        )
        return _tag_elements(
            elements,
            issue_key=candidate.issue_key,
            file_name=candidate.path.name,
            geometry_source="dwg_ezdxf_bbox",
            geometry_quality="medium",
            level_assignment_source=candidate.level_source,
        )

    if candidate.suffix in {".dxf"}:
        elements = extract_elements_from_dwg(
            candidate.path,
            candidate.discipline,
            level_id=candidate.level_id,
            translation_mm=(0.0, 0.0),
            min_area_mm2=config.min_dwg_area_mm2,
            max_entities=config.max_dwg_entities,
        )
        return _tag_elements(
            elements,
            issue_key=candidate.issue_key,
            file_name=candidate.path.name,
            level_assignment_source=candidate.level_source,
        )

    logger.warning("Unsupported file type for extraction: %s", candidate.suffix)
    return []


def _extract_scheduled_elements(
    scheduled_candidates: list[SourceCandidate],
    profiled_payloads: dict[str, dict[str, Any]],
    config: PipelineConfig,
) -> tuple[list[Element25D], list[Element25D]]:
    results: dict[str, list[Element25D]] = {}

    def _worker(candidate: SourceCandidate) -> tuple[str, list[Element25D]]:
        try:
            elements = _extract_elements_for_candidate(candidate, profiled_payloads, config)
            return (candidate.rel_path, elements)
        except Exception as exc:
            logger.exception("Extraction failed for %s: %s", candidate.path.name, exc)
            return (candidate.rel_path, [])

    n = max(1, config.max_workers)
    if n == 1 or len(scheduled_candidates) == 1:
        for c in scheduled_candidates:
            rel, elements = _worker(c)
            results[rel] = elements
    else:
        with ThreadPoolExecutor(max_workers=n) as executor:
            futures = {executor.submit(_worker, c): c for c in scheduled_candidates}
            for future in as_completed(futures):
                c = futures[future]
                rel, elements = future.result()
                results[rel] = elements

    all_elements: list[Element25D] = []
    suppressed: list[Element25D] = []

    for candidate in scheduled_candidates:
        extracted = results.get(candidate.rel_path, [])
        normalized: list[Element25D] = []
        for element in extracted:
            ne = normalize_fast_compare_element(
                element,
                file_level_id=candidate.level_id,
                cohort_id=candidate.cohort_id or _SINGLE_COHORT,
                level_source=candidate.level_source,
            )
            meta = dict(ne.metadata)
            meta["source_rel_path"] = candidate.rel_path
            normalized.append(ne.model_copy(update={"metadata": meta}))

        all_elements.extend(normalized)
        suppressed.extend(e for e in normalized if not primary_geometry_role(e))
        logger.info(
            "%s → %d elementos (%s, %s)",
            candidate.path.name,
            len(normalized),
            candidate.discipline.value,
            candidate.level_id,
        )

    return all_elements, suppressed


def _build_primary_conflicts(
    all_elements: list[Element25D],
    registry: ProjectLevelRegistry,
    required_disciplines: tuple[Discipline, ...],
    config: PipelineConfig,
) -> list[ClashConflict]:
    grouped: dict[tuple[str, str], list[Element25D]] = defaultdict(list)
    for element in all_elements:
        if not primary_geometry_role(element):
            continue
        grouped[
            (
                str(element.metadata.get("cohort_id") or _SINGLE_COHORT),
                str(element.metadata.get("file_level_id") or element.z_data.level_id),
            )
        ].append(element)

    required = {d.value for d in required_disciplines}
    conflicts: list[ClashConflict] = []
    for (_, _level_id), group in sorted(grouped.items()):
        disciplines = {e.discipline.value for e in group}
        if not required.issubset(disciplines):
            continue
        conflicts.extend(
            clash_pairs(
                group,
                registry,
                strict_levels=config.strict_levels,
                min_plan_area_mm2=config.primary_min_plan_area_mm2,
            )
        )
    conflicts.sort(key=lambda c: (-c.overlap_depth_z_mm, -c.plan_intersection_area_mm2))
    return conflicts


def _build_hotspot_incidents(
    primary_conflicts: list[ClashConflict],
    debug_conflicts: list[ClashConflict],
) -> list:
    from collections import Counter

    scored_pairs: Counter[tuple[str, str]] = Counter()
    for conflict in primary_conflicts + debug_conflicts:
        file_pair = tuple(sorted(ref.split("|", 1)[0] for ref in conflict.source_refs))
        score = 2 if any("polyline" in src for src in conflict.geometry_sources) else 1
        scored_pairs[file_pair] += score
    top_pairs = {pair for pair, _ in scored_pairs.most_common(8)}
    if not top_pairs:
        return []
    hotspot_conflicts = [
        c
        for c in primary_conflicts + debug_conflicts
        if tuple(sorted(ref.split("|", 1)[0] for ref in c.source_refs)) in top_pairs
    ]
    return group_conflicts_into_incidents(hotspot_conflicts, cell_size_mm=1000.0)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_clash_pipeline(
    inputs: list[FileInput],
    project_name: str,
    output_dir: Path,
    config: PipelineConfig | None = None,
) -> dict[str, Any]:
    """Run the fast-compare clash pipeline on a set of uploaded files.

    Returns the result dict expected by clash_workflow_service.ensure_ingested().
    """
    if config is None:
        config = PipelineConfig()

    cache_root = config.cache_root or (output_dir / "cache")
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    doc = _build_default_doc(project_name)
    registry = doc.to_registry()

    # Build source candidates from uploaded file metadata
    all_candidates = _build_candidates(inputs, doc)
    if not all_candidates:
        raise ValueError("No valid source candidates could be built from the uploaded files")

    unique_disciplines = tuple({c.discipline for c in all_candidates})

    # Readiness
    pre_match = build_pre_match_candidates(all_candidates, required_disciplines=unique_disciplines)
    readiness_payload = compute_readiness_payload(
        all_candidates,
        required_disciplines=unique_disciplines,
        pre_match_candidates=pre_match,
    )
    readiness_payload["analysis_profile"] = FAST_COMPARE_ANALYSIS_PROFILE
    readiness_payload["project_name"] = project_name

    selected_candidates = select_preferred_candidates(all_candidates, pair_candidates=pre_match)
    selected_candidates = sorted(
        suppress_visual_backups(selected_candidates),
        key=lambda c: c.rel_path,
    )

    if not selected_candidates:
        logger.warning("No candidates selected after filtering")
        return _empty_result(project_name, output_dir, generated_at)

    # Profile DWG files via accore
    profiled_payloads = _profile_candidates(
        selected_candidates,
        cache_root=cache_root,
        timeout_seconds=config.accore_timeout_seconds,
        max_workers=config.max_workers,
    )

    # Coordinate audit + pair schedule
    candidate_audits = [
        build_source_audit(
            candidate,
            elements=None,
            accore_profile=profiled_payloads.get(candidate.rel_path, {}).get("profile"),
            coordinate_band_cell_mm=config.coordinate_band_cell_mm,
        )
        for candidate in selected_candidates
    ]
    candidate_audits = apply_coordinate_band_gating(candidate_audits, required_disciplines=unique_disciplines)

    coordinate_audit_payload = {
        "generated_at": generated_at,
        "project_name": project_name,
        "analysis_profile": FAST_COMPARE_ANALYSIS_PROFILE,
        "audit_count": len(candidate_audits),
        "audits": [audit.model_dump() for audit in candidate_audits],
    }
    pair_schedule = build_pair_schedule(
        candidate_audits,
        required_disciplines=unique_disciplines,
        pre_match_candidates=pre_match,
    )
    scheduled_pairs = [item for item in pair_schedule if item.scheduled]
    scheduled_file_set = {path for item in scheduled_pairs for path in (item.file_a, item.file_b)}

    pair_schedule_payload = {
        "generated_at": generated_at,
        "project_name": project_name,
        "analysis_profile": FAST_COMPARE_ANALYSIS_PROFILE,
        "pair_count": len(pair_schedule),
        "scheduled_pair_count": len(scheduled_pairs),
        "pairs": [item.model_dump() for item in pair_schedule],
    }

    readiness_payload = finalize_readiness_payload(
        readiness_payload,
        audits=coordinate_audit_payload["audits"],
        pair_schedule=[item.model_dump() for item in pair_schedule],
    )
    _write_json(output_dir / "comparison_readiness_report.json", readiness_payload)
    _write_json(output_dir / "coordinate_audit.json", coordinate_audit_payload)
    _write_json(output_dir / "pair_schedule.json", pair_schedule_payload)

    if not scheduled_pairs:
        logger.warning("No scheduled pairs — returning empty result")
        return _empty_result(project_name, output_dir, generated_at)

    # Extract elements
    extract_start = perf_counter()
    scheduled_candidates = [c for c in selected_candidates if c.rel_path in scheduled_file_set]
    all_elements, suppressed_elements = _extract_scheduled_elements(
        scheduled_candidates,
        profiled_payloads,
        config,
    )
    logger.info(
        "Extraction: %d files → %d elements in %.2fs",
        len(scheduled_file_set),
        len(all_elements),
        perf_counter() - extract_start,
    )

    # Clash detection
    clash_start = perf_counter()
    primary_conflicts = _build_primary_conflicts(
        all_elements, registry, unique_disciplines, config
    )
    primary_incidents = group_conflicts_into_incidents(primary_conflicts)
    logger.info(
        "Clash detection: %d incidents from %d conflicts in %.2fs",
        len(primary_incidents),
        len(primary_conflicts),
        perf_counter() - clash_start,
    )

    # Hotspots
    hotspot_incidents = _build_hotspot_incidents(primary_conflicts, debug_conflicts=[])
    hotspot_payload = None
    if hotspot_incidents:
        hotspot_payload = {
            "generated_at": generated_at,
            "project_name": project_name,
            "analysis_profile": FAST_COMPARE_ANALYSIS_PROFILE,
            "incident_count": len(hotspot_incidents),
            "incidents": [i.model_dump() for i in hotspot_incidents],
        }

    primary_payload = {
        "generated_at": generated_at,
        "project_name": project_name,
        "analysis_profile": FAST_COMPARE_ANALYSIS_PROFILE,
        "incident_count": len(primary_incidents),
        "incident_conflict_count": len(primary_conflicts),
        "incidents": [i.model_dump() for i in primary_incidents],
    }
    debug_payload = {
        "generated_at": generated_at,
        "project_name": project_name,
        "analysis_profile": FAST_COMPARE_ANALYSIS_PROFILE,
        "debug_conflict_count": 0,
        "suppressed_element_count": len(suppressed_elements),
        "suppressed_elements": [],
        "debug_conflicts": [],
    }

    _write_json(output_dir / "primary_incidents.json", primary_payload)
    if hotspot_payload:
        _write_json(output_dir / "hotspot_incidents.json", hotspot_payload)

    # Build report context (becomes the "report" key in the service result)
    summary_payload: dict[str, Any] = {
        "generated_at": generated_at,
        "project_name": project_name,
        "analysis_profile": FAST_COMPARE_ANALYSIS_PROFILE,
        "status": "completed",
        "selected_candidate_count": len(selected_candidates),
        "element_count": len(all_elements),
        "scheduled_pair_count": len(scheduled_pairs),
        "scheduled_file_count": len(scheduled_file_set),
    }
    report_context = build_coordination_report_context(
        summary_payload=summary_payload,
        primary_payload=primary_payload,
        debug_payload=debug_payload,
        hotspot_payload=hotspot_payload,
        coordinate_audit_payload=coordinate_audit_payload,
        pair_schedule_payload=pair_schedule_payload,
    )
    _write_json(output_dir / "coordination_report_context.json", report_context)

    return {
        "report": report_context,
        "artifacts": {
            "primary_incidents": primary_payload,
            "output_dir": str(output_dir),
        },
    }


def _empty_result(project_name: str, output_dir: Path, generated_at: str) -> dict[str, Any]:
    primary_payload = {
        "generated_at": generated_at,
        "project_name": project_name,
        "analysis_profile": FAST_COMPARE_ANALYSIS_PROFILE,
        "incident_count": 0,
        "incident_conflict_count": 0,
        "incidents": [],
    }
    return {
        "report": {
            "project_name": project_name,
            "status": "no_clashes_detected",
            "generated_at": generated_at,
        },
        "artifacts": {
            "primary_incidents": primary_payload,
            "output_dir": str(output_dir),
        },
    }
