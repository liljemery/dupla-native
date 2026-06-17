#!/usr/bin/env python3
"""High-precision 2.5D clash runner for the NASAS 09 coordination workflow."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Iterable

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coordination.core.clash import ClashConflict, group_conflicts_into_incidents
from coordination.core.clash_element_mapper import map_primary_incidents_to_elements
from coordination.core.models_25d import Element25D
from coordination.core.nasas_paths import (
    COORDINATION_ISSUE_METADATA_KEY,
    coordination_issue_key,
    discipline_from_nasas_relative_path,
    file_translation_mm,
)
from coordination.core.registry import ProjectLevelRegistryDocument
from coordination.extraction.from_autodesk_properties import bulk_elements_from_autodesk_raw, load_autodesk_raw
from coordination.extraction.from_dwg_accore import (
    extract_elements_from_accore_payload,
    extract_elements_from_dwg_via_accore,
    load_accore_payload_via_accore,
    profile_accore_payload,
)
from coordination.extraction.companion_pdf import resolve_companion_pdf
from coordination.extraction.aps_cache import file_cache_key, load_cached_json
from coordination.extraction.from_aps_viewer_dump import viewer_dump_has_geometry
from coordination.extraction.from_dwg_aps import extract_elements_from_dwg_via_aps
from coordination.extraction.from_dwg_com import extract_elements_from_dwg_via_com
from coordination.extraction.from_dwg_ezdxf import extract_elements_from_dwg
from coordination.extraction.from_pdf_vector import extract_elements_from_pdf
from coordination.extraction.from_raster_image import extract_elements_from_image
from coordination.reporting.reporting import (
    build_analysis_bot_context,
    build_coordination_report_context,
    render_coordination_human_report_html,
    render_coordination_human_report_markdown,
    render_coordination_report_markdown,
    render_primary_incidents_markdown,
)
from coordination.reporting.tile_renderer import render_all_annotated_tiles, render_all_incident_tiles
from coordination.selection.coordinate_audit import (
    apply_coordinate_band_gating,
    build_pair_schedule,
    build_source_audit,
    render_coordinate_audit_markdown,
    render_hotspot_markdown,
)
from coordination.selection.fast_compare import (
    CAD_SUFFIXES,
    FAST_COMPARE_ANALYSIS_PROFILE,
    FAST_COMPARE_APS_PROFILE,
    apply_manifest_selection,
    build_pre_match_candidates,
    build_source_candidates,
    compute_readiness_payload,
    finalize_readiness_payload,
    load_alignment_manifest,
    load_cohort_manifest,
    normalize_fast_compare_element,
    parse_include_disciplines,
    primary_geometry_role,
    render_readiness_markdown,
    select_preferred_candidates,
    select_comparable_candidates,
    suppress_visual_backups,
)
from coordination.selection.level_inference import infer_level_from_view_name
from coordination.selection.source_selection import collect_coordination_media, normalize_source_text, relative_posix
from coordination.semantic.semantic_elements import (
    build_semantic_elements_from_accore_payload,
    export_elements_by_dwg_json,
)
from coordination.semantic.nearby_text import (
    enrich_elements_with_nearby_text,
    extract_texts_from_accore_payload,
)
from coordination.semantic.vision_validator import (
    apply_vision_results,
    validate_incident_tiles,
    vision_tile_result_to_dict,
)
from coordination import clash_pairs, conflicts_to_conflict_notes

logger = logging.getLogger("dupla.nasas09.coordination")

from coordination.selection.clash_media_filter import (
    MIN_EXACT_ELEMENTS_FOR_PDF_SKIP,
    clear_exact_companion_pdfs,
    exact_companion_pdf_names,
    register_exact_companion_pdf,
    should_skip_clash_media,
)


def _load_exact_companion_pdfs_from_cache(nasas_root: Path, cache_root: Path) -> None:
    """Precarga PDFs cuyo DWG ya tiene geometría viewer exacta en caché APS."""
    if not cache_root.is_dir():
        return
    for dwg in nasas_root.rglob("*.dwg"):
        diag = load_cached_json(cache_root, key=file_cache_key(dwg), suffix="diagnostics")
        if not isinstance(diag, dict):
            continue
        if str(diag.get("result") or "") not in {"viewer_geometry", "viewer_cache"}:
            continue
        if int(diag.get("viewer_elements") or 0) < MIN_EXACT_ELEMENTS_FOR_PDF_SKIP:
            continue
        companion = resolve_companion_pdf(dwg)
        if companion is not None:
            register_exact_companion_pdf(companion.name)


def _register_exact_dwg_companion(dwg_path: Path, elements: list[Element25D]) -> None:
    if len(elements) < MIN_EXACT_ELEMENTS_FOR_PDF_SKIP:
        return
    if not any(str(el.metadata.get("geometry_quality") or "") == "exact" for el in elements):
        return
    companion = resolve_companion_pdf(dwg_path)
    if companion is not None:
        register_exact_companion_pdf(companion.name)
        logger.info(
            "PDF compañero omitido en clash (DWG exacto): %s -> %s",
            dwg_path.name,
            companion.name,
        )

DEFAULT_NASAS = REPO_ROOT / "aps_integration" / "NASAS 09"
DEFAULT_REGISTRY = DEFAULT_NASAS / "coordination" / "sample_project_levels.json"
DEFAULT_OUT = DEFAULT_NASAS / "outputs" / "coordination" / "clash_project_report.json"
DEFAULT_AUTODESK = (
    DEFAULT_NASAS
    / "outputs"
    / "corridas"
    / "_cad_merge"
    / "27.11.2025 LAS NASAS 09, DUPLA.autodesk_raw.json"
)


def _analysis_profile_label(args: argparse.Namespace) -> str:
    return str(args.analysis_profile)


def _heuristic_profile_for_candidate(candidate: Any) -> dict[str, object]:
    """Lightweight stand-in for accore profiling when APS is used (any OS)."""
    return {
        "raw_entity_count": 100,
        "raw_primary_candidate_count": 50,
        "raw_annotation_count": 0,
        "raw_bbox_only_count": 0,
        "bounds_mm": [0.0, 0.0, 100_000.0, 100_000.0],
        "centroid_mm": [50_000.0, 50_000.0],
        "dominant_cluster_bounds_mm": [0.0, 0.0, 100_000.0, 100_000.0],
        "dominant_cluster_centroid_mm": [50_000.0, 50_000.0],
        "dominant_entity_types": ["LINE"],
        "units_to_mm_factor": 1.0,
        "profile_source": "heuristic",
        "rel_path": str(candidate.rel_path),
    }


def _heuristic_profile_candidates(selected_candidates: list) -> dict[str, dict[str, object]]:
    return {candidate.rel_path: {"profile": _heuristic_profile_for_candidate(candidate), "payload": None, "cache_hit": False} for candidate in selected_candidates}


def _write_extraction_progress(progress_path: Path, payload: dict[str, Any]) -> None:
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class _ExtractionProgressTracker:
    def __init__(self, progress_path: Path, total: int) -> None:
        self._path = progress_path
        self._total = total
        self._processed = 0
        self._lock = threading.Lock()
        self._start = perf_counter()
        self._active: list[str] = []
        _write_extraction_progress(
            progress_path,
            {
                "processed": 0,
                "total": total,
                "current_files": [],
                "elapsed_s": 0.0,
                "phase": "extraction",
            },
        )

    def begin(self, file_name: str) -> None:
        with self._lock:
            if file_name not in self._active:
                self._active.append(file_name)
            self._flush()

    def complete(self, file_name: str) -> None:
        with self._lock:
            self._processed += 1
            self._active = [name for name in self._active if name != file_name]
            self._flush()

    def _flush(self) -> None:
        _write_extraction_progress(
            self._path,
            {
                "processed": self._processed,
                "total": self._total,
                "current_files": list(self._active),
                "elapsed_s": round(perf_counter() - self._start, 2),
                "phase": "extraction",
            },
        )


def _init_aps_session(args: argparse.Namespace) -> tuple[dict[str, Any] | None, str | None]:
    if not args.dwg_via_aps:
        return (None, None)
    from aps_integration.aps_auth import get_aps_token
    from aps_integration.oss_manager import APS_BUCKET_NAME, create_bucket

    token_state: dict[str, Any] = {"access_token": get_aps_token(), "refresh_count": 0}
    bucket = APS_BUCKET_NAME
    create_bucket(token_state["access_token"], bucket)
    return (token_state, bucket)


@dataclass
class _MediaExtractionResult:
    path: Path
    rel: str
    issue_key: str
    suffix: str
    elements: list[Element25D]
    skipped: bool
    is_dwg: bool
    is_pdf: bool
    is_image: bool


def _should_skip_media(path: Path, suffix: str, args: argparse.Namespace) -> bool:
    skip = should_skip_clash_media(path, suffix, args)
    if skip and suffix == ".pdf" and path.name in exact_companion_pdf_names():
        logger.info("Omitiendo PDF compañero en clash (DWG con geometría exacta): %s", path.name)
    return skip


def _extract_media_item(
    path: Path,
    *,
    nasas_root: Path,
    args: argparse.Namespace,
    default_level_id: str,
    doc: ProjectLevelRegistryDocument,
    aps_token: str | dict | None,
    aps_bucket: str | None,
    cache_root: Path,
    progress: _ExtractionProgressTracker | None = None,
) -> _MediaExtractionResult:
    rel = relative_posix(path, nasas_root)
    issue_key = coordination_issue_key(path, nasas_root)
    suffix = path.suffix.lower()
    if _should_skip_media(path, suffix, args):
        return _MediaExtractionResult(path, rel, issue_key, suffix, [], True, False, False, False)

    if progress is not None:
        progress.begin(path.name)
    discipline = discipline_from_nasas_relative_path(rel.lower())
    translation = (0.0, 0.0) if args.shared_site_origin else file_translation_mm(path)
    try:
        elements = _extract_path_elements(
            path,
            suffix=suffix,
            discipline=discipline,
            issue_key=issue_key,
            default_level_id=default_level_id,
            translation_mm=translation,
            doc=doc,
            args=args,
            aps_token=aps_token,
            aps_bucket=aps_bucket,
            cache_root=cache_root,
        )
    except Exception:
        logger.exception("Fallo procesando %s", path)
        if progress is not None:
            progress.complete(path.name)
        return _MediaExtractionResult(path, rel, issue_key, suffix, [], True, False, False, False)

    if progress is not None:
        progress.complete(path.name)
    if suffix in {".dwg", ".dxf"} and elements:
        _register_exact_dwg_companion(path, elements)
    logger.info("%s -> %d elementos (%s)", path.name, len(elements), discipline.value)
    return _MediaExtractionResult(
        path,
        rel,
        issue_key,
        suffix,
        elements,
        False,
        suffix in {".dwg", ".dxf"},
        suffix == ".pdf",
        suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"},
    )


def _extract_standard_media_parallel(
    *,
    media: list[Path],
    nasas_root: Path,
    args: argparse.Namespace,
    default_level_id: str,
    doc: ProjectLevelRegistryDocument,
    aps_token: str | dict | None,
    aps_bucket: str | None,
    cache_root: Path,
) -> tuple[list[Element25D], dict[str, set[str]], dict[str, object]]:
    summary: dict[str, object] = {
        "selected_media": len(media),
        "dwg": 0,
        "pdf": 0,
        "image": 0,
        "skipped_runtime": 0,
    }
    issue_to_files: dict[str, set[str]] = defaultdict(set)
    all_elements: list[Element25D] = []

    clear_exact_companion_pdfs()
    _load_exact_companion_pdfs_from_cache(nasas_root, cache_root)
    media = sorted(media, key=lambda p: (p.suffix.lower() == ".pdf", p.name.lower()))

    eligible = [path for path in media if not _should_skip_media(path, path.suffix.lower(), args)]
    progress_path = args.output.parent / "extraction_progress.json"
    progress = _ExtractionProgressTracker(progress_path, len(eligible)) if eligible else None

    worker_count = max(1, int(args.max_workers or 1))

    def _worker(path: Path) -> _MediaExtractionResult:
        return _extract_media_item(
            path,
            nasas_root=nasas_root,
            args=args,
            default_level_id=default_level_id,
            doc=doc,
            aps_token=aps_token,
            aps_bucket=aps_bucket,
            cache_root=cache_root,
            progress=progress,
        )

    results: list[_MediaExtractionResult] = []
    if worker_count == 1 or len(media) <= 1:
        for path in media:
            results.append(_worker(path))
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(_worker, path): path for path in media}
            for future in as_completed(futures):
                results.append(future.result())

    for result in results:
        issue_to_files[result.issue_key].add(result.rel)
        if result.skipped:
            summary["skipped_runtime"] = int(summary["skipped_runtime"]) + 1
            continue
        all_elements.extend(result.elements)
        if result.is_dwg:
            summary["dwg"] = int(summary["dwg"]) + 1
        elif result.is_pdf:
            summary["pdf"] = int(summary["pdf"]) + 1
        elif result.is_image:
            summary["image"] = int(summary["image"]) + 1

    if progress is not None:
        _write_extraction_progress(
            progress_path,
            {
                "processed": len(eligible),
                "total": len(eligible),
                "current_files": [],
                "elapsed_s": round(perf_counter() - progress._start, 2),
                "phase": "clash",
            },
        )

    return all_elements, issue_to_files, summary


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Clashes proyecto NASAS 09 (multi-fuente, alta precision)")
    parser.add_argument(
        "--analysis-profile",
        choices=("standard", FAST_COMPARE_ANALYSIS_PROFILE, FAST_COMPARE_APS_PROFILE),
        default="standard",
        help="Perfil de analisis. fast_compare (accore Windows) y fast_compare_aps (APS, todos los SO) usan scheduling paralelo.",
    )
    parser.add_argument(
        "--stage",
        choices=("full", "coordinate_audit", "arq_est", "hotspots"),
        default="full",
        help="Etapa del perfil fast_compare. full ejecuta audit + arq_est + hotspots.",
    )
    parser.add_argument(
        "--enable-semantic-mapping",
        action="store_true",
        help="Genera elements_by_dwg.json y clash_element_links.json como capa MVP posterior a primary_incidents.",
    )
    parser.add_argument(
        "--enable-vision-validation",
        action="store_true",
        help="Validate clashes with vision model.",
    )
    parser.add_argument(
        "--max-vision-tiles",
        type=int,
        default=50,
        help="Max tiles to validate with vision.",
    )
    parser.add_argument(
        "--vision-model",
        type=str,
        default=None,
        help="Override vision model (default: gpt-5.1).",
    )
    parser.add_argument("--nasas-root", type=Path, default=DEFAULT_NASAS)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--include-disciplines",
        type=str,
        default=None,
        help="Lista CSV de disciplinas permitidas. Ej: ARQUITECTURA,ESTRUCTURA",
    )
    parser.add_argument(
        "--cohort-manifest",
        type=Path,
        default=None,
        help="JSON opcional con source_files para autorizar una cohorte manual.",
    )
    parser.add_argument(
        "--alignment-manifest",
        type=Path,
        default=None,
        help="JSON opcional con translate_mm por archivo para alinear fuentes manualmente.",
    )
    parser.add_argument(
        "--shared-site-origin",
        dest="shared_site_origin",
        action="store_true",
        default=True,
        help="Usar origen comun en planta para archivos comparables (default).",
    )
    parser.add_argument(
        "--separate-file-origin",
        dest="shared_site_origin",
        action="store_false",
        help="Modo diagnostico: separa cada archivo con una traslacion por hash.",
    )
    parser.add_argument(
        "--page-z-step-mm",
        type=float,
        default=3200.0,
        help="Fallback de depuracion para paginas PDF sin nivel detectable.",
    )
    parser.add_argument("--max-dwg-entities", type=int, default=350)
    parser.add_argument("--min-dwg-area-mm2", type=float, default=40_000.0)
    parser.add_argument(
        "--primary-min-plan-area-mm2",
        type=float,
        default=10_000.0,
        help="Area minima en planta para incidencias primarias de fast_compare.",
    )
    parser.add_argument(
        "--coordinate-band-cell-mm",
        type=float,
        default=500_000.0,
        help="Tamano de celda para agrupar bandas de coordenadas en fast_compare.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=6,
        help="Workers paralelos para profiling/extraccion (APS, accore o standard).",
    )
    parser.add_argument(
        "--include-autodesk-bulk",
        action="store_true",
        help="Incluye entidades proxy desde autodesk_raw (solo baja confianza).",
    )
    parser.add_argument("--autodesk-raw", type=Path, default=DEFAULT_AUTODESK)
    parser.add_argument("--autodesk-bulk-max", type=int, default=450)
    parser.add_argument("--strict-levels", action="store_true")
    parser.add_argument(
        "--mix-issues",
        action="store_true",
        help="Mezcla entregas distintas en un solo pase de clash.",
    )
    parser.add_argument(
        "--dwg-via-aps",
        action="store_true",
        help="DWG via APS Model Derivative. Los DXF se procesan localmente con ezdxf.",
    )
    parser.add_argument(
        "--aps-translation-timeout",
        type=int,
        default=3600,
        help="Timeout de traduccion APS cuando se usa --dwg-via-aps.",
    )
    parser.add_argument(
        "--accore-timeout-seconds",
        type=int,
        default=240,
        help="Timeout local de AutoCAD Core Console para DWG binario.",
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=None,
        help="Directorio de cache para respuestas APS y dumps de geometria Viewer.",
    )
    parser.add_argument("--skip-dwg", action="store_true", help="Omitir archivos CAD (.dwg/.dxf).")
    parser.add_argument("--skip-pdf", action="store_true", help="Omitir PDF.")
    parser.add_argument(
        "--include-images",
        action="store_true",
        help="Incluir imagenes raster como fuentes de baja confianza.",
    )
    parser.add_argument(
        "--allow-proxy-hard-clashes",
        action="store_true",
        help="Permite que fuentes proxy o low entren al flujo HARD.",
    )
    parser.add_argument(
        "--allow-pdf-page-fallback",
        action="store_true",
        help="Si una pagina PDF no produce clusters, usar bbox de la hoja como fallback.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("ezdxf").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    is_fast_compare_profile = args.analysis_profile in (
        FAST_COMPARE_ANALYSIS_PROFILE,
        FAST_COMPARE_APS_PROFILE,
    )
    if is_fast_compare_profile:
        args.mix_issues = False
        args.include_images = False
        args.allow_proxy_hard_clashes = False
        args.allow_pdf_page_fallback = False
        args.dwg_via_aps = args.analysis_profile == FAST_COMPARE_APS_PROFILE

    if not args.registry.is_file():
        logger.error("Falta registro de niveles: %s", args.registry)
        return 1
    if args.dwg_via_aps and (not os.getenv("CLIENT_ID") or not os.getenv("CLIENT_SECRET")):
        logger.error("--dwg-via-aps requiere CLIENT_ID y CLIENT_SECRET en el entorno.")
        return 1

    doc = ProjectLevelRegistryDocument.model_validate(
        json.loads(args.registry.read_text(encoding="utf-8"))
    )
    registry = doc.to_registry()
    default_level_id = "NPT_P1" if "NPT_P1" in registry.root else "NASAS_ARQ_P1_NPT"

    nasas_root = args.nasas_root.resolve()
    media, scan_skips = collect_coordination_media(
        nasas_root,
        extra_patterns=doc.source_exclude_patterns,
        require_planos_recibidos=True,
    )
    cache_root = args.cache_root.resolve() if args.cache_root else args.output.parent / "cache"

    if is_fast_compare_profile:
        return _run_fast_compare(
            args=args,
            doc=doc,
            registry=registry,
            default_level_id=default_level_id,
            media=media,
            scan_skips=scan_skips,
            nasas_root=nasas_root,
            cache_root=cache_root,
        )

    summary: dict[str, object] = {
        "selected_media": len(media),
        "dwg": 0,
        "pdf": 0,
        "image": 0,
        "skipped_runtime": 0,
        "scan_skips": scan_skips,
    }

    aps_token, aps_bucket = _init_aps_session(args)

    extract_start = perf_counter()
    all_elements, issue_to_files, extract_summary = _extract_standard_media_parallel(
        media=media,
        nasas_root=nasas_root,
        args=args,
        default_level_id=default_level_id,
        doc=doc,
        aps_token=aps_token,
        aps_bucket=aps_bucket,
        cache_root=cache_root,
    )
    summary.update(extract_summary)
    summary["extract_seconds"] = round(perf_counter() - extract_start, 3)
    summary["max_workers"] = int(args.max_workers or 1)
    logger.info(
        "Standard extract: %d archivos -> %d elementos en %.2fs (%d workers)",
        len(media),
        len(all_elements),
        float(summary["extract_seconds"]),
        summary["max_workers"],
    )

    autodesk_bulk_count = 0
    if args.include_autodesk_bulk and args.autodesk_raw.is_file():
        merge_issue = coordination_issue_key(args.autodesk_raw, nasas_root)
        issue_to_files[merge_issue].add(relative_posix(args.autodesk_raw, nasas_root))
        raw = load_autodesk_raw(args.autodesk_raw)
        bulk = bulk_elements_from_autodesk_raw(
            raw,
            level_id=default_level_id,
            max_entities=args.autodesk_bulk_max,
        )
        all_elements.extend(
            _tag_elements(
                bulk,
                issue_key=merge_issue,
                file_name=args.autodesk_raw.name,
                geometry_source="autodesk_bulk",
                geometry_quality="proxy",
                level_assignment_source="default_level",
                sheet_name=args.autodesk_raw.stem,
            )
        )
        autodesk_bulk_count = len(bulk)
        logger.info("autodesk_raw bulk -> %d elementos", autodesk_bulk_count)

    if not all_elements:
        logger.warning("No se generaron elementos bajo %s", nasas_root)

    issue_groups, conflicts = _build_issue_groups_and_conflicts(
        elements=all_elements,
        registry=registry,
        issue_to_files=issue_to_files,
        mix_issues=args.mix_issues,
        strict_levels=args.strict_levels,
        allow_proxy_hard_clashes=args.allow_proxy_hard_clashes,
    )
    conflicts.sort(key=lambda item: (-item.overlap_depth_z_mm, -item.plan_intersection_area_mm2))
    human = conflicts_to_conflict_notes(conflicts)

    summary["element_count"] = len(all_elements)
    summary["hard_eligible_element_count"] = sum(group["hard_eligible_count"] for group in issue_groups)
    summary["geometry_quality_counts"] = dict(
        Counter(str(el.metadata.get("geometry_quality") or "unknown") for el in all_elements)
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "nasas_root": str(nasas_root),
        "project_name": doc.project_name,
        "level_id_default": default_level_id,
        "inputs_summary": summary,
        "autodesk_bulk_count": autodesk_bulk_count,
        "element_count": len(all_elements),
        "conflict_count": len(conflicts),
        "conflicts": [conflict.model_dump() for conflict in conflicts],
        "conflicts_human": human,
        "issue_groups": issue_groups,
        "notes": [
            "El runner agrupa por coordination_issue_key antes del clash salvo --mix-issues.",
            "DWG usa AutoCAD Core Console local cuando esta disponible; COM queda como fallback y APS es opcional. DXF se procesa localmente con ezdxf.",
            "PDF se modela por clusters vectoriales; el bbox de pagina solo entra con --allow-pdf-page-fallback.",
            "Raster y APS bulk quedan fuera del flujo HARD por defecto por geometry_quality baja.",
        ],
        "mix_issues": bool(args.mix_issues),
        "dwg_via_aps": bool(args.dwg_via_aps),
        "shared_site_origin": bool(args.shared_site_origin),
        "allow_proxy_hard_clashes": bool(args.allow_proxy_hard_clashes),
    }
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Informe: %s (%d conflictos, %d elementos)", args.output, len(conflicts), len(all_elements))

    _export_plan_geometry(all_elements, args.output.parent / "plan_geometry.json")

    for line in human[:50]:
        print(line)
    if len(human) > 50:
        print(f"... y {len(human) - 50} mas (ver JSON).")
    return 0


def _export_plan_geometry(all_elements: list[Element25D], output_path: Path) -> None:
    """Persist per-file element footprints + extents so downstream consumers can
    render a high-resolution 2D plan with accurate clash overlays.

    Output schema:
        {"files": {"<filename>": {"discipline", "extents_mm"[4], "element_count",
                                   "elements": [{"discipline", "footprint_mm"[[x,y],...]}]}}}
    """
    files: dict[str, dict[str, Any]] = {}
    for el in all_elements:
        footprint = list(getattr(el, "footprint_coords_mm", None) or [])
        if len(footprint) < 2:
            continue
        source_ref = str(getattr(el, "source_ref", "") or "")
        file_name = Path(source_ref.split("|", 1)[0]).name or str(
            (el.metadata or {}).get("file") or "unknown"
        )
        discipline = el.discipline.value if hasattr(el.discipline, "value") else str(el.discipline)
        entry = files.setdefault(
            file_name, {"discipline": discipline, "elements": []}
        )
        entry["elements"].append(
            {
                "discipline": discipline,
                "footprint_mm": [[round(float(x), 1), round(float(y), 1)] for x, y in footprint],
            }
        )

    out: dict[str, Any] = {"files": {}}
    for file_name, data in files.items():
        xs = [p[0] for e in data["elements"] for p in e["footprint_mm"]]
        ys = [p[1] for e in data["elements"] for p in e["footprint_mm"]]
        out["files"][file_name] = {
            "discipline": data["discipline"],
            "extents_mm": [min(xs), min(ys), max(xs), max(ys)] if xs else None,
            "element_count": len(data["elements"]),
            "elements": data["elements"],
        }
    try:
        output_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        logger.info("plan_geometry.json -> %d archivos", len(out["files"]))
    except OSError as exc:
        logger.warning("No se pudo escribir plan_geometry.json: %s", exc)


def _extract_path_elements(
    path: Path,
    *,
    suffix: str,
    discipline,
    issue_key: str,
    default_level_id: str,
    translation_mm: tuple[float, float],
    doc: ProjectLevelRegistryDocument,
    args: argparse.Namespace,
    aps_token: str | dict | None,
    aps_bucket: str | None,
    cache_root: Path,
    file_level_id: str | None = None,
    file_level_source: str | None = None,
) -> list[Element25D]:
    if file_level_id is None or file_level_source is None:
        view_text = "\n".join(
            part
            for part in (
                path.stem,
                path.name,
                relative_posix(path, args.nasas_root.resolve()),
                path.parent.name,
            )
            if part
        )
        level_resolution = infer_level_from_view_name(
            view_text,
            doc=doc,
            default_level_id=default_level_id,
        )
    else:
        level_resolution = SimpleNamespace(level_id=file_level_id, source=file_level_source)
    if suffix in {".dwg", ".dxf"}:
        if suffix == ".dwg" and args.dwg_via_aps and aps_token and aps_bucket:
            aps_elements = extract_elements_from_dwg_via_aps(
                path,
                discipline,
                level_id=level_resolution.level_id,
                translation_mm=translation_mm,
                token=aps_token,
                bucket_name=aps_bucket,
                coordination_issue_key=issue_key,
                max_entities=args.max_dwg_entities,
                min_area_m2=max(args.min_dwg_area_mm2 / 1_000_000.0, 0.001),
                translation_timeout_seconds=args.aps_translation_timeout,
                cache_root=cache_root,
                level_doc=doc,
            )
            if aps_elements:
                return _tag_elements(
                    aps_elements,
                    issue_key=issue_key,
                    file_name=path.name,
                    level_assignment_source=level_resolution.source,
                    sheet_name=path.stem,
                )
            viewer_cached = load_cached_json(cache_root, key=file_cache_key(path), suffix="viewer")
            if isinstance(viewer_cached, dict) and viewer_dump_has_geometry(viewer_cached):
                logger.info(
                    "DWG %s tiene viewer.json con geometría — omitiendo PDF compañero",
                    path.name,
                )
                return []
        if suffix == ".dwg":
            accore_elements = extract_elements_from_dwg_via_accore(
                path,
                discipline,
                level_id=level_resolution.level_id,
                translation_mm=translation_mm,
                max_entities=args.max_dwg_entities,
                min_area_mm2=args.min_dwg_area_mm2,
                cache_root=cache_root / "accore",
                timeout_seconds=args.accore_timeout_seconds,
            )
            if accore_elements:
                return _tag_elements(
                    accore_elements,
                    issue_key=issue_key,
                    file_name=path.name,
                    level_assignment_source=level_resolution.source,
                    sheet_name=path.stem,
                )
            com_elements = extract_elements_from_dwg_via_com(
                path,
                discipline,
                level_id=level_resolution.level_id,
                translation_mm=translation_mm,
                max_entities=args.max_dwg_entities,
                min_area_mm2=args.min_dwg_area_mm2,
            )
            if com_elements:
                return _tag_elements(
                    com_elements,
                    issue_key=issue_key,
                    file_name=path.name,
                    geometry_source="dwg_com_bbox",
                    geometry_quality="medium",
                    level_assignment_source=level_resolution.source,
                    sheet_name=path.stem,
                )
        companion_pdf = resolve_companion_pdf(path)
        if companion_pdf is not None:
            pdf_elements = extract_elements_from_pdf(
                companion_pdf,
                discipline,
                level_id=level_resolution.level_id,
                translation_mm=translation_mm,
                page_z_step_mm=args.page_z_step_mm,
                level_doc=doc,
                allow_page_fallback=True,
            )
            if pdf_elements:
                logger.info(
                    "DWG %s sin geometría local/APS — usando PDF compañero %s (%d elementos)",
                    path.name,
                    companion_pdf.name,
                    len(pdf_elements),
                )
                return _tag_elements(
                    pdf_elements,
                    issue_key=issue_key,
                    file_name=path.name,
                    geometry_source="pdf_companion_vector",
                    geometry_quality="medium",
                    level_assignment_source=level_resolution.source,
                    sheet_name=companion_pdf.stem,
                )
        return _tag_elements(
            extract_elements_from_dwg(
                path,
                discipline,
                level_id=level_resolution.level_id,
                translation_mm=translation_mm,
                max_entities=args.max_dwg_entities,
                min_area_mm2=args.min_dwg_area_mm2,
            ),
            issue_key=issue_key,
            file_name=path.name,
            geometry_source="dwg_ezdxf",
            geometry_quality="high",
            level_assignment_source=level_resolution.source,
            sheet_name=path.stem,
        )
    if suffix == ".pdf":
        return _tag_elements(
            extract_elements_from_pdf(
                path,
                discipline,
                level_id=default_level_id,
                translation_mm=translation_mm,
                page_z_step_mm=args.page_z_step_mm,
                level_doc=doc,
                allow_page_fallback=args.allow_pdf_page_fallback,
            ),
            issue_key=issue_key,
            file_name=path.name,
        )
    return _tag_elements(
        extract_elements_from_image(
            path,
            discipline,
            level_id=default_level_id,
            translation_mm=translation_mm,
            level_doc=doc,
        ),
        issue_key=issue_key,
        file_name=path.name,
    )


def _tag_elements(
    elements: Iterable[Element25D],
    *,
    issue_key: str,
    file_name: str,
    geometry_source: str | None = None,
    geometry_quality: str | None = None,
    level_assignment_source: str | None = None,
    sheet_name: str | None = None,
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
        if sheet_name is not None:
            metadata["sheet_or_view_name"] = sheet_name
        tagged.append(element.model_copy(update={"metadata": metadata}))
    return tagged


def _build_issue_groups_and_conflicts(
    *,
    elements: list[Element25D],
    registry,
    issue_to_files: dict[str, set[str]],
    mix_issues: bool,
    strict_levels: bool,
    allow_proxy_hard_clashes: bool,
) -> tuple[list[dict[str, object]], list]:
    by_issue: dict[str, list[Element25D]] = defaultdict(list)
    for element in elements:
        issue = str(element.metadata.get(COORDINATION_ISSUE_METADATA_KEY) or "__missing__")
        by_issue[issue].append(element)

    issue_groups: list[dict[str, object]] = []
    all_conflicts: list = []

    if mix_issues:
        eligible = [element for element in elements if _hard_clash_eligible(element, allow_proxy_hard_clashes)]
        all_conflicts = clash_pairs(
            eligible,
            registry,
            strict_levels=strict_levels,
            min_plan_area_mm2=0.5,
        )
        for issue_key, group_elements in sorted(by_issue.items()):
            issue_groups.append(
                {
                    "issue_key": issue_key,
                    "element_count": len(group_elements),
                    "hard_eligible_count": sum(
                        1 for element in group_elements if _hard_clash_eligible(element, allow_proxy_hard_clashes)
                    ),
                    "conflict_count": 0,
                    "source_files": sorted(issue_to_files.get(issue_key, set())),
                }
            )
        return (issue_groups, all_conflicts)

    for issue_key, group_elements in sorted(by_issue.items()):
        eligible = [element for element in group_elements if _hard_clash_eligible(element, allow_proxy_hard_clashes)]
        conflicts = clash_pairs(
            eligible,
            registry,
            strict_levels=strict_levels,
            min_plan_area_mm2=0.5,
        )
        all_conflicts.extend(conflicts)
        issue_groups.append(
            {
                "issue_key": issue_key,
                "element_count": len(group_elements),
                "hard_eligible_count": len(eligible),
                "conflict_count": len(conflicts),
                "source_files": sorted(issue_to_files.get(issue_key, set())),
                "conflicts_human": conflicts_to_conflict_notes(conflicts),
            }
        )
    return (issue_groups, all_conflicts)


def _hard_clash_eligible(element: Element25D, allow_proxy: bool) -> bool:
    quality = str(element.metadata.get("geometry_quality") or "medium").lower()
    if quality == "low":
        return False
    if quality == "proxy" and not allow_proxy:
        return False
    return True


def _resolve_candidate_translation(
    *,
    candidate,
    args: argparse.Namespace,
    alignment_overrides: dict[str, object] | None,
) -> tuple[float, float]:
    base_translation = (0.0, 0.0) if args.shared_site_origin else file_translation_mm(candidate.path)
    override = _resolve_candidate_alignment_override(
        candidate=candidate,
        alignment_overrides=alignment_overrides,
    )
    if override is None:
        return base_translation
    dx, dy = override.translate_mm
    return (base_translation[0] + dx, base_translation[1] + dy)


def _resolve_candidate_alignment_override(
    *,
    candidate,
    alignment_overrides: dict[str, object] | None,
):
    if not alignment_overrides:
        return None
    return alignment_overrides.get(normalize_source_text(candidate.rel_path))


def _apply_alignment_override_to_candidate(
    *,
    candidate,
    alignment_overrides: dict[str, object] | None,
):
    override = _resolve_candidate_alignment_override(
        candidate=candidate,
        alignment_overrides=alignment_overrides,
    )
    if override is None:
        return candidate
    if not getattr(override, "level_id", None):
        return candidate
    return candidate.__class__(
        path=candidate.path,
        rel_path=candidate.rel_path,
        issue_key=candidate.issue_key,
        discipline=candidate.discipline,
        suffix=candidate.suffix,
        level_id=override.level_id,
        level_source=getattr(override, "level_source", None) or candidate.level_source,
        cohort_id=candidate.cohort_id,
        drawing_type=getattr(candidate, "drawing_type", "generic"),
        drawing_type_source=getattr(candidate, "drawing_type_source", "heuristic"),
    )


def _apply_translation_to_profile(
    profile: dict[str, object] | None,
    *,
    translation_mm: tuple[float, float],
) -> dict[str, object] | None:
    if profile is None:
        return None
    dx, dy = translation_mm
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return dict(profile)

    adjusted = dict(profile)
    bounds = profile.get("bounds_mm")
    if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
        adjusted["bounds_mm"] = (
            float(bounds[0]) + dx,
            float(bounds[1]) + dy,
            float(bounds[2]) + dx,
            float(bounds[3]) + dy,
            *(tuple(bounds[4:]) if len(bounds) > 4 else ()),
        )
    centroid = profile.get("centroid_mm")
    if isinstance(centroid, (list, tuple)) and len(centroid) >= 2:
        adjusted["centroid_mm"] = (
            float(centroid[0]) + dx,
            float(centroid[1]) + dy,
            *(tuple(centroid[2:]) if len(centroid) > 2 else ()),
        )
    cluster_bounds = profile.get("dominant_cluster_bounds_mm")
    if isinstance(cluster_bounds, (list, tuple)) and len(cluster_bounds) >= 4:
        adjusted["dominant_cluster_bounds_mm"] = (
            float(cluster_bounds[0]) + dx,
            float(cluster_bounds[1]) + dy,
            float(cluster_bounds[2]) + dx,
            float(cluster_bounds[3]) + dy,
            *(tuple(cluster_bounds[4:]) if len(cluster_bounds) > 4 else ()),
        )
    cluster_centroid = profile.get("dominant_cluster_centroid_mm")
    if isinstance(cluster_centroid, (list, tuple)) and len(cluster_centroid) >= 2:
        adjusted["dominant_cluster_centroid_mm"] = (
            float(cluster_centroid[0]) + dx,
            float(cluster_centroid[1]) + dy,
            *(tuple(cluster_centroid[2:]) if len(cluster_centroid) > 2 else ()),
        )
    return adjusted


def _profile_fast_compare_candidates(
    *,
    selected_candidates: list,
    cache_root: Path,
    timeout_seconds: int,
    max_workers: int,
) -> tuple[dict[str, dict[str, object]], dict[str, int]]:
    dwg_candidates = [candidate for candidate in selected_candidates if candidate.suffix == ".dwg"]
    if not dwg_candidates:
        return ({}, {"profiled_file_count": 0, "accore_cache_hits": 0, "accore_cache_misses": 0})

    def _worker(candidate) -> tuple[str, dict[str, object]]:
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
            {
                "payload": payload_result.payload,
                "profile": profile,
                "cache_hit": payload_result.cache_hit,
            },
        )

    results: dict[str, dict[str, object]] = {}
    worker_count = max(1, int(max_workers or 1))
    if worker_count == 1 or len(dwg_candidates) == 1:
        for candidate in dwg_candidates:
            rel_path, payload_entry = _worker(candidate)
            results[rel_path] = payload_entry
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(_worker, candidate): candidate.rel_path for candidate in dwg_candidates}
            for future in as_completed(futures):
                rel_path, payload_entry = future.result()
                results[rel_path] = payload_entry

    cache_hits = sum(1 for entry in results.values() if bool(entry.get("cache_hit")))
    return (
        results,
        {
            "profiled_file_count": len(dwg_candidates),
            "accore_cache_hits": cache_hits,
            "accore_cache_misses": len(dwg_candidates) - cache_hits,
        },
    )


def _extract_fast_compare_accore_elements(
    *,
    candidate,
    payload: dict[str, object],
    args: argparse.Namespace,
    translation_mm: tuple[float, float],
) -> list[Element25D]:
    accore_elements = extract_elements_from_accore_payload(
        payload,
        path=candidate.path,
        discipline=candidate.discipline,
        level_id=candidate.level_id,
        translation_mm=translation_mm,
        max_entities=args.max_dwg_entities,
        min_area_mm2=args.min_dwg_area_mm2,
        z_thickness_mm=250.0,
        z_ref_mm=None,
    )
    if not accore_elements:
        return []
    return _tag_elements(
        accore_elements,
        issue_key=candidate.issue_key,
        file_name=candidate.path.name,
        level_assignment_source=candidate.level_source,
        sheet_name=candidate.path.stem,
    )


def _extract_fast_compare_scheduled_elements(
    *,
    selected_candidates: list,
    scheduled_file_set: set[str],
    args: argparse.Namespace,
    default_level_id: str,
    doc: ProjectLevelRegistryDocument,
    cache_root: Path,
    profiled_payloads: dict[str, dict[str, object]],
    alignment_overrides: dict[str, object] | None,
    aps_token: str | dict | None = None,
    aps_bucket: str | None = None,
) -> tuple[list[Element25D], list[Element25D], int]:
    scheduled_candidates = [candidate for candidate in selected_candidates if candidate.rel_path in scheduled_file_set]
    if not scheduled_candidates:
        return ([], [], 0)

    progress_path = args.output.parent / "extraction_progress.json"
    progress = _ExtractionProgressTracker(progress_path, len(scheduled_candidates))

    results: dict[str, list[Element25D]] = {}
    fallback_candidates: list = []
    skipped_runtime = 0

    def _worker(candidate) -> tuple[str, list[Element25D], bool]:
        translation = _resolve_candidate_translation(
            candidate=candidate,
            args=args,
            alignment_overrides=alignment_overrides,
        )
        if candidate.suffix == ".dwg" and args.dwg_via_aps and aps_token and aps_bucket:
            progress.begin(candidate.path.name)
            try:
                elements = _extract_path_elements(
                    candidate.path,
                    suffix=candidate.suffix,
                    discipline=candidate.discipline,
                    issue_key=candidate.issue_key,
                    default_level_id=default_level_id,
                    translation_mm=translation,
                    doc=doc,
                    args=args,
                    aps_token=aps_token,
                    aps_bucket=aps_bucket,
                    cache_root=cache_root,
                    file_level_id=candidate.level_id,
                    file_level_source=candidate.level_source,
                )
            finally:
                progress.complete(candidate.path.name)
            return (candidate.rel_path, elements, not bool(elements))
        if candidate.suffix == ".dwg":
            payload = profiled_payloads.get(candidate.rel_path, {}).get("payload")
            if not payload:
                return (candidate.rel_path, [], True)
            elements = _extract_fast_compare_accore_elements(
                candidate=candidate,
                payload=payload,
                args=args,
                translation_mm=translation,
            )
            return (candidate.rel_path, elements, not bool(elements))
        elements = _extract_path_elements(
            candidate.path,
            suffix=candidate.suffix,
            discipline=candidate.discipline,
            issue_key=candidate.issue_key,
            default_level_id=default_level_id,
            translation_mm=translation,
            doc=doc,
            args=args,
            aps_token=None,
            aps_bucket=None,
            cache_root=cache_root,
            file_level_id=candidate.level_id,
            file_level_source=candidate.level_source,
        )
        return (candidate.rel_path, elements, False)

    worker_count = max(1, int(args.max_workers or 1))
    if worker_count == 1 or len(scheduled_candidates) == 1:
        for candidate in scheduled_candidates:
            try:
                rel_path, elements, needs_fallback = _worker(candidate)
                results[rel_path] = elements
                if needs_fallback:
                    fallback_candidates.append(candidate)
            except Exception:
                logger.exception("Fallo extrayendo %s", candidate.path)
                skipped_runtime += 1
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(_worker, candidate): candidate for candidate in scheduled_candidates}
            for future in as_completed(futures):
                candidate = futures[future]
                try:
                    rel_path, elements, needs_fallback = future.result()
                    results[rel_path] = elements
                    if needs_fallback:
                        fallback_candidates.append(candidate)
                except Exception:
                    logger.exception("Fallo extrayendo %s", candidate.path)
                    skipped_runtime += 1

    for candidate in sorted(fallback_candidates, key=lambda item: item.rel_path):
        try:
            translation = _resolve_candidate_translation(
                candidate=candidate,
                args=args,
                alignment_overrides=alignment_overrides,
            )
            com_elements = extract_elements_from_dwg_via_com(
                candidate.path,
                candidate.discipline,
                level_id=candidate.level_id,
                translation_mm=translation,
                max_entities=args.max_dwg_entities,
                min_area_mm2=args.min_dwg_area_mm2,
            )
            results[candidate.rel_path] = _tag_elements(
                com_elements,
                issue_key=candidate.issue_key,
                file_name=candidate.path.name,
                geometry_source="dwg_com_bbox",
                geometry_quality="medium",
                level_assignment_source=candidate.level_source,
                sheet_name=candidate.path.stem,
            )
        except Exception:
            logger.exception("Fallo fallback COM para %s", candidate.path)
            skipped_runtime += 1

    all_elements: list[Element25D] = []
    suppressed_elements: list[Element25D] = []
    for candidate in scheduled_candidates:
        extracted = results.get(candidate.rel_path, [])
        cohort_id = candidate.cohort_id or candidate.issue_key
        normalized: list[Element25D] = []
        for element in extracted:
            normalized_element = normalize_fast_compare_element(
                element,
                file_level_id=candidate.level_id,
                cohort_id=cohort_id,
                level_source=candidate.level_source,
            )
            metadata = dict(normalized_element.metadata)
            metadata["source_rel_path"] = candidate.rel_path
            normalized.append(normalized_element.model_copy(update={"metadata": metadata}))
        all_elements.extend(normalized)
        suppressed_elements.extend(element for element in normalized if not primary_geometry_role(element))
        logger.info(
            "%s -> %d elementos (%s, %s)",
            candidate.path.name,
            len(normalized),
            candidate.discipline.value,
            candidate.level_id,
        )
    _enrich_fast_compare_elements_with_nearby_text(
        all_elements=all_elements,
        scheduled_candidates=scheduled_candidates,
        profiled_payloads=profiled_payloads,
        args=args,
        alignment_overrides=alignment_overrides,
    )
    _write_extraction_progress(
        progress_path,
        {
            "processed": len(scheduled_candidates),
            "total": len(scheduled_candidates),
            "current_files": [],
            "elapsed_s": round(perf_counter() - progress._start, 2),
            "phase": "clash",
        },
    )
    return (all_elements, suppressed_elements, skipped_runtime)


def _enrich_fast_compare_elements_with_nearby_text(
    *,
    all_elements: list[Element25D],
    scheduled_candidates: list,
    profiled_payloads: dict[str, dict[str, object]],
    args: argparse.Namespace,
    alignment_overrides: dict[str, object] | None,
) -> None:
    files_processed = 0
    total_texts = 0
    elements_enriched = 0
    elements_with_text = 0
    elements_without_text = 0
    elements_by_rel: dict[str, list[Element25D]] = defaultdict(list)
    for element in all_elements:
        rel_path = str(element.metadata.get("source_rel_path") or "")
        if rel_path:
            elements_by_rel[rel_path].append(element)

    for candidate in scheduled_candidates:
        payload_entry = profiled_payloads.get(candidate.rel_path, {})
        payload = payload_entry.get("payload")
        file_elements = elements_by_rel.get(candidate.rel_path, [])
        if not isinstance(payload, dict):
            if file_elements:
                enrich_elements_with_nearby_text(file_elements, [])
                elements_enriched += len(file_elements)
                elements_without_text += len(file_elements)
            continue
        files_processed += 1
        translation = _resolve_candidate_translation(
            candidate=candidate,
            args=args,
            alignment_overrides=alignment_overrides,
        )
        texts = extract_texts_from_accore_payload(
            payload,
            float(payload.get("UnitsToMmFactor") or 1.0),
            candidate.rel_path,
            translation_mm=translation,
        )
        total_texts += len(texts)
        enrich_elements_with_nearby_text(file_elements, texts)
        enriched_with_text = sum(1 for element in file_elements if element.metadata.get("nearby_texts"))
        elements_enriched += len(file_elements)
        elements_with_text += enriched_with_text
        elements_without_text += len(file_elements) - enriched_with_text
        if texts:
            logger.info(
                "nearby_text: %d texts found, enriched %d elements for %s",
                len(texts),
                len(file_elements),
                candidate.rel_path,
            )
        else:
            logger.info("nearby_text: no text entities found in %s", candidate.rel_path)

    logger.info(
        "nearby_text enrichment summary: files=%d total_texts=%d elements_enriched=%d "
        "with_nearby_text=%d without_nearby_text=%d",
        files_processed,
        total_texts,
        elements_enriched,
        elements_with_text,
        elements_without_text,
    )


def _build_semantic_mapping_payloads(
    *,
    generated_at: str,
    project_name: str,
    run_label: str,
    selected_candidates: list,
    scheduled_file_set: set[str],
    all_elements: list[Element25D],
    profiled_payloads: dict[str, dict[str, object]],
    primary_payload: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    candidate_by_rel = {
        candidate.rel_path: candidate for candidate in selected_candidates if candidate.rel_path in scheduled_file_set
    }
    elements_by_rel: dict[str, list[Element25D]] = defaultdict(list)
    for element in all_elements:
        rel_path = str(element.metadata.get("source_rel_path") or "")
        if rel_path:
            elements_by_rel[rel_path].append(element)

    semantic_elements = []
    for rel_path in sorted(scheduled_file_set):
        candidate = candidate_by_rel.get(rel_path)
        if candidate is None:
            continue
        raw_elements = elements_by_rel.get(rel_path, [])
        if not raw_elements:
            continue
        payload_entry = profiled_payloads.get(rel_path, {})
        payload = payload_entry.get("payload")
        semantic_elements.extend(
            build_semantic_elements_from_accore_payload(
                raw_elements=raw_elements,
                source_file=candidate.path,
                source_rel_path=rel_path,
                payload=payload if isinstance(payload, dict) else None,
            )
        )

    elements_by_dwg_payload = export_elements_by_dwg_json(
        generated_at=generated_at,
        project_name=project_name,
        run_label=run_label,
        semantic_elements=semantic_elements,
    )
    clash_element_links_payload = map_primary_incidents_to_elements(
        generated_at=generated_at,
        project_name=project_name,
        run_label=run_label,
        primary_payload=primary_payload,
        elements_by_dwg_payload=elements_by_dwg_payload,
    )
    return (elements_by_dwg_payload, clash_element_links_payload)


def _run_fast_compare(
    *,
    args: argparse.Namespace,
    doc: ProjectLevelRegistryDocument,
    registry,
    default_level_id: str,
    media: list[Path],
    scan_skips: dict[str, int],
    nasas_root: Path,
    cache_root: Path,
) -> int:
    profile_label = _analysis_profile_label(args)
    aps_token, aps_bucket = _init_aps_session(args)
    overall_metrics: dict[str, object] = {
        "audit_seconds": 0.0,
        "schedule_seconds": 0.0,
        "extract_seconds": 0.0,
        "clash_seconds": 0.0,
        "scheduled_pair_count": 0,
        "scheduled_file_count": 0,
        "profiled_file_count": 0,
        "accore_cache_hits": 0,
        "accore_cache_misses": 0,
        "skipped_runtime": 0,
    }
    include_disciplines = parse_include_disciplines(args.include_disciplines)
    candidates = sorted(
        [
        candidate
        for candidate in build_source_candidates(
            media,
            root=nasas_root,
            doc=doc,
            default_level_id=default_level_id,
        )
        if candidate.discipline in include_disciplines
        and not (args.skip_dwg and candidate.suffix in {".dwg", ".dxf"})
        and not (args.skip_pdf and candidate.suffix == ".pdf")
        ],
        key=lambda candidate: candidate.rel_path,
    )

    readiness_start = perf_counter()
    pre_match_candidates = build_pre_match_candidates(
        candidates,
        required_disciplines=include_disciplines,
    )
    readiness_payload = compute_readiness_payload(
        candidates,
        required_disciplines=include_disciplines,
        pre_match_candidates=pre_match_candidates,
    )
    readiness_payload["analysis_profile"] = profile_label
    readiness_payload["project_name"] = doc.project_name
    readiness_payload["scan_skips"] = scan_skips
    alignment_overrides = (
        load_alignment_manifest(args.alignment_manifest, root=nasas_root)
        if args.alignment_manifest is not None
        else {}
    )
    if alignment_overrides:
        readiness_payload["alignment_manifest"] = {
            "path": str(args.alignment_manifest),
            "entry_count": len(alignment_overrides),
        }

    if args.cohort_manifest is not None:
        manifest = load_cohort_manifest(args.cohort_manifest, root=nasas_root)
        selected_candidates = apply_manifest_selection(candidates, manifest=manifest)
        readiness_payload["cohort_manifest"] = {
            "cohort_name": manifest.cohort_name,
            "source_file_count": len(manifest.source_files),
            "selected_count": len(selected_candidates),
        }
    else:
        selected_candidates = select_preferred_candidates(candidates, pair_candidates=pre_match_candidates)

    selected_candidates = [
        _apply_alignment_override_to_candidate(
            candidate=candidate,
            alignment_overrides=alignment_overrides,
        )
        for candidate in suppress_visual_backups(selected_candidates)
    ]
    selected_candidates = sorted(selected_candidates, key=lambda candidate: candidate.rel_path)
    readiness_payload["selected_candidates"] = [
        {
            "rel_path": candidate.rel_path,
            "issue_key": candidate.issue_key,
            "cohort_id": candidate.cohort_id or candidate.issue_key,
            "discipline": candidate.discipline.value,
            "level_id": candidate.level_id,
            "drawing_type": candidate.drawing_type,
            "suffix": candidate.suffix,
        }
        for candidate in selected_candidates
    ]

    readiness_json = args.output.parent / "comparison_readiness_report.json"
    readiness_md = args.output.parent / "comparison_readiness_report.md"
    logger.info(
        "Fast compare readiness: %d candidatos seleccionados en %.2fs",
        len(selected_candidates),
        perf_counter() - readiness_start,
    )

    if not selected_candidates:
        _write_json(readiness_json, readiness_payload)
        readiness_md.write_text(
            render_readiness_markdown(readiness_payload, project_name=doc.project_name or "Proyecto", root=nasas_root),
            encoding="utf-8",
        )
        return _write_fast_compare_summary(
            args=args,
            doc=doc,
            nasas_root=nasas_root,
            readiness_json=readiness_json,
            readiness_md=readiness_md,
            coordinate_audit_json=None,
            coordinate_audit_md=None,
            pair_schedule_json=None,
            selected_candidates=selected_candidates,
            all_elements=[],
            primary_incidents=[],
            debug_conflicts=[],
            suppressed_elements=[],
            status="readiness_only",
            metrics=overall_metrics,
        )

    audit_start = perf_counter()
    if args.analysis_profile == FAST_COMPARE_APS_PROFILE:
        profiled_payloads = _heuristic_profile_candidates(selected_candidates)
        profile_metrics = {
            "profiled_file_count": len(selected_candidates),
            "accore_cache_hits": 0,
            "accore_cache_misses": 0,
        }
    else:
        profiled_payloads, profile_metrics = _profile_fast_compare_candidates(
            selected_candidates=selected_candidates,
            cache_root=cache_root,
            timeout_seconds=args.accore_timeout_seconds,
            max_workers=args.max_workers,
        )
    overall_metrics.update(profile_metrics)
    candidate_audits = [
        build_source_audit(
            candidate,
            elements=None,
            accore_profile=_apply_translation_to_profile(
                profiled_payloads.get(candidate.rel_path, {}).get("profile"),
                translation_mm=_resolve_candidate_translation(
                    candidate=candidate,
                    args=args,
                    alignment_overrides=alignment_overrides,
                ),
            ),
            coordinate_band_cell_mm=args.coordinate_band_cell_mm,
        )
        for candidate in selected_candidates
    ]
    candidate_audits = apply_coordinate_band_gating(
        candidate_audits,
        required_disciplines=include_disciplines,
    )
    overall_metrics["audit_seconds"] = round(perf_counter() - audit_start, 3)
    logger.info(
        "Fast compare audit: %d archivos auditados (%d perfilados DWG) en %.2fs",
        len(candidate_audits),
        overall_metrics["profiled_file_count"],
        float(overall_metrics["audit_seconds"]),
    )

    coordinate_audit_json = args.output.parent / "coordinate_audit.json"
    coordinate_audit_md = args.output.parent / "coordinate_audit.md"
    pair_schedule_json = args.output.parent / "pair_schedule.json"

    schedule_start = perf_counter()
    pair_schedule = build_pair_schedule(
        candidate_audits,
        required_disciplines=include_disciplines,
        pre_match_candidates=pre_match_candidates if args.cohort_manifest is None else None,
    )
    scheduled_pairs = [item for item in pair_schedule if item.scheduled]
    scheduled_file_set = {path for item in scheduled_pairs for path in (item.file_a, item.file_b)}
    overall_metrics["scheduled_pair_count"] = len(scheduled_pairs)
    overall_metrics["scheduled_file_count"] = len(scheduled_file_set)
    overall_metrics["schedule_seconds"] = round(perf_counter() - schedule_start, 3)
    coordinate_audit_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_name": doc.project_name,
        "analysis_profile": profile_label,
        "stage": args.stage,
        "audit_count": len(candidate_audits),
        "audits": [audit.model_dump() for audit in candidate_audits],
    }
    readiness_payload = finalize_readiness_payload(
        readiness_payload,
        audits=coordinate_audit_payload["audits"],
        pair_schedule=[item.model_dump() for item in pair_schedule],
    )
    _write_json(readiness_json, readiness_payload)
    readiness_md.write_text(
        render_readiness_markdown(readiness_payload, project_name=doc.project_name or "Proyecto", root=nasas_root),
        encoding="utf-8",
    )
    _write_json(coordinate_audit_json, coordinate_audit_payload)
    coordinate_audit_md.write_text(
        render_coordinate_audit_markdown(
            candidate_audits,
            project_name=doc.project_name or "Proyecto",
            root=nasas_root,
        ),
        encoding="utf-8",
    )
    pair_schedule_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_name": doc.project_name,
        "analysis_profile": profile_label,
        "stage": args.stage,
        "pair_count": len(pair_schedule),
        "scheduled_pair_count": len(scheduled_pairs),
        "pairs": [item.model_dump() for item in pair_schedule],
    }
    _write_json(pair_schedule_json, pair_schedule_payload)
    logger.info(
        "Fast compare schedule: %d/%d pares programados en %.2fs",
        len(scheduled_pairs),
        len(pair_schedule),
        float(overall_metrics["schedule_seconds"]),
    )

    if args.stage == "coordinate_audit":
        return _write_fast_compare_summary(
            args=args,
            doc=doc,
            nasas_root=nasas_root,
            readiness_json=readiness_json,
            readiness_md=readiness_md,
            coordinate_audit_json=coordinate_audit_json,
            coordinate_audit_md=coordinate_audit_md,
            pair_schedule_json=pair_schedule_json,
            selected_candidates=selected_candidates,
            all_elements=[],
            primary_incidents=[],
            debug_conflicts=[],
            suppressed_elements=[],
            status="coordinate_audit_only",
            metrics=overall_metrics,
        )

    if not scheduled_pairs:
        return _write_fast_compare_summary(
            args=args,
            doc=doc,
            nasas_root=nasas_root,
            readiness_json=readiness_json,
            readiness_md=readiness_md,
            coordinate_audit_json=coordinate_audit_json,
            coordinate_audit_md=coordinate_audit_md,
            pair_schedule_json=pair_schedule_json,
            selected_candidates=selected_candidates,
            all_elements=[],
            primary_incidents=[],
            debug_conflicts=[],
            suppressed_elements=[],
            status="no_scheduled_pairs",
            metrics=overall_metrics,
        )

    extract_start = perf_counter()
    all_elements, suppressed_elements, skipped_runtime = _extract_fast_compare_scheduled_elements(
        selected_candidates=selected_candidates,
        scheduled_file_set=scheduled_file_set,
        args=args,
        default_level_id=default_level_id,
        doc=doc,
        cache_root=cache_root,
        profiled_payloads=profiled_payloads,
        alignment_overrides=alignment_overrides,
        aps_token=aps_token,
        aps_bucket=aps_bucket,
    )
    overall_metrics["skipped_runtime"] = skipped_runtime
    overall_metrics["extract_seconds"] = round(perf_counter() - extract_start, 3)
    logger.info(
        "Fast compare extract: %d archivos programados -> %d elementos en %.2fs",
        len(scheduled_file_set),
        len(all_elements),
        float(overall_metrics["extract_seconds"]),
    )

    clash_start = perf_counter()
    element_lookup = {element.id: element for element in all_elements}
    primary_conflicts = _build_fast_compare_primary_conflicts(
        all_elements=all_elements,
        registry=registry,
        strict_levels=args.strict_levels,
        required_disciplines=include_disciplines,
        min_plan_area_mm2=args.primary_min_plan_area_mm2,
    )
    primary_incidents = group_conflicts_into_incidents(primary_conflicts)

    debug_conflicts = _build_fast_compare_debug_conflicts(
        all_elements=all_elements,
        registry=registry,
        strict_levels=args.strict_levels,
        required_disciplines=include_disciplines,
        primary_conflicts=primary_conflicts,
        element_lookup=element_lookup,
    )
    overall_metrics["clash_seconds"] = round(perf_counter() - clash_start, 3)
    logger.info(
        "Fast compare clash: %d incidencias primarias, %d debug en %.2fs",
        len(primary_incidents),
        len(debug_conflicts),
        float(overall_metrics["clash_seconds"]),
    )

    primary_json = args.output.parent / "primary_incidents.json"
    primary_md = args.output.parent / "primary_incidents.md"
    debug_json = args.output.parent / "debug_candidates.json"
    hotspot_json = args.output.parent / "hotspot_incidents.json"
    hotspot_md = args.output.parent / "hotspot_incidents.md"
    elements_by_dwg_json = args.output.parent / "elements_by_dwg.json"
    clash_element_links_json = args.output.parent / "clash_element_links.json"
    generated_at = datetime.now(timezone.utc).isoformat()
    primary_payload = {
        "generated_at": generated_at,
        "project_name": doc.project_name,
        "analysis_profile": _analysis_profile_label(args),
        "incident_count": len(primary_incidents),
        "incident_conflict_count": len(primary_conflicts),
        "incidents": [incident.model_dump() for incident in primary_incidents],
    }
    _write_json(primary_json, primary_payload)
    primary_md.write_text(
        render_primary_incidents_markdown(
            project_name=doc.project_name or "Proyecto",
            root=nasas_root,
            primary_payload=primary_payload,
        ),
        encoding="utf-8",
    )
    rendered_tiles = []
    if primary_incidents:
        try:
            rendered_tiles = render_all_incident_tiles(
                incidents=primary_incidents,
                all_elements=all_elements,
                output_dir=args.output.parent,
                width_px=800,
            )
            logger.info("Rendered %d incident tiles", len(rendered_tiles))
        except Exception as exc:
            logger.warning("Tile rendering failed: %s", exc)
    vision_overrides = {}
    if args.enable_vision_validation and rendered_tiles:
        try:
            vision_results = validate_incident_tiles(
                tiles=rendered_tiles,
                all_elements=all_elements,
                max_tiles=args.max_vision_tiles,
                model=args.vision_model,
            )
            vision_overrides = apply_vision_results(vision_results)
            vision_output = [vision_tile_result_to_dict(result) for result in vision_results]
            (args.output.parent / "vision_validation.json").write_text(
                json.dumps(vision_output, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info(
                "Vision validation: %d/%d tiles validated",
                sum(1 for result in vision_results if result.success),
                len(vision_results),
            )
        except Exception as exc:
            logger.warning("Vision validation failed: %s", exc)
    debug_payload = {
        "generated_at": generated_at,
        "project_name": doc.project_name,
        "analysis_profile": _analysis_profile_label(args),
        "debug_conflict_count": len(debug_conflicts),
        "suppressed_element_count": len(suppressed_elements),
        "suppressed_elements": [
            {
                "id": element.id,
                "source_ref": element.source_ref,
                "discipline": element.discipline.value,
                "geometry_source": element.metadata.get("geometry_source"),
                "geometry_role": element.metadata.get("geometry_role"),
                "suppression_reason": element.metadata.get("suppression_reason"),
                "file_level_id": element.metadata.get("file_level_id"),
                "cohort_id": element.metadata.get("cohort_id"),
            }
            for element in suppressed_elements
        ],
        "debug_conflicts": [conflict.model_dump() for conflict in debug_conflicts],
    }
    _write_json(debug_json, debug_payload)
    hotspot_payload = None
    hotspot_incidents = []
    if args.stage in {"full", "hotspots"} and primary_conflicts:
        hotspot_incidents = _build_hotspot_incidents(
            primary_conflicts=primary_conflicts,
            debug_conflicts=debug_conflicts,
        )
        if hotspot_incidents:
            hotspot_payload = {
                "generated_at": generated_at,
                "project_name": doc.project_name,
                "analysis_profile": _analysis_profile_label(args),
                "incident_count": len(hotspot_incidents),
                "incidents": [incident.model_dump() for incident in hotspot_incidents],
            }
            _write_json(hotspot_json, hotspot_payload)
            hotspot_md.write_text(
                render_hotspot_markdown(
                    hotspot_incidents,
                    project_name=doc.project_name or "Proyecto",
                    root=nasas_root,
                ),
                encoding="utf-8",
            )

    technical_report_md = args.output.parent / "technical_coordination_report.md"
    technical_report_context_json = args.output.parent / "coordination_report_context.json"
    analysis_bot_context_json = args.output.parent / "analysis_bot_context.json"
    coordination_human_md = args.output.parent / "coordination_report_human.md"
    coordination_human_html = args.output.parent / "coordination_report_human.html"
    semantic_elements_payload = None
    clash_element_links_payload = None
    if args.enable_semantic_mapping:
        try:
            semantic_elements_payload, clash_element_links_payload = _build_semantic_mapping_payloads(
                generated_at=generated_at,
                project_name=doc.project_name,
                run_label=args.output.parent.name,
                selected_candidates=selected_candidates,
                scheduled_file_set=scheduled_file_set,
                all_elements=all_elements,
                profiled_payloads=profiled_payloads,
                primary_payload=primary_payload,
            )
            _write_json(elements_by_dwg_json, semantic_elements_payload)
            _write_json(clash_element_links_json, clash_element_links_payload)
        except Exception:
            semantic_elements_payload = None
            clash_element_links_payload = None
            logger.exception("Semantic mapping MVP failed; continuing without semantic artifacts.")
    technical_report_context = build_coordination_report_context(
        summary_payload={
            "generated_at": generated_at,
            "project_name": doc.project_name,
            "analysis_profile": _analysis_profile_label(args),
            "status": "completed",
            "selected_candidate_count": len(selected_candidates),
            "element_count": len(all_elements),
            "scheduled_pair_count": len(scheduled_pairs),
            "scheduled_file_count": len(scheduled_file_set),
        }
        | overall_metrics,
        primary_payload=primary_payload,
        debug_payload=debug_payload,
        hotspot_payload=hotspot_payload,
        coordinate_audit_payload=coordinate_audit_payload,
        pair_schedule_payload=pair_schedule_payload,
    )
    annotated_tiles = []
    if rendered_tiles:
        try:
            incident_severities = {
                str(card.get("incident_id")): {
                    "severity": str(card.get("severity") or "noise"),
                    "action_owner": str(card.get("action_owner") or ""),
                }
                for card in technical_report_context.get("all_incidents") or []
            }
            annotated_tiles = render_all_annotated_tiles(
                base_tiles=rendered_tiles,
                vision_overrides=vision_overrides,
                incident_severities=incident_severities,
                output_dir=args.output.parent,
            )
            logger.info("Generated %d annotated tiles", len(annotated_tiles))
        except Exception as exc:
            logger.warning("Annotated tile rendering failed: %s", exc)
    _write_json(technical_report_context_json, technical_report_context)
    technical_report_md.write_text(
        render_coordination_report_markdown(
            project_name=doc.project_name or "Proyecto",
            root=nasas_root,
            summary_payload={
                "generated_at": generated_at,
                "project_name": doc.project_name,
                "analysis_profile": _analysis_profile_label(args),
                "status": "completed",
                "selected_candidate_count": len(selected_candidates),
                "element_count": len(all_elements),
                "scheduled_pair_count": len(scheduled_pairs),
                "scheduled_file_count": len(scheduled_file_set),
            }
            | overall_metrics,
            primary_payload=primary_payload,
            debug_payload=debug_payload,
            hotspot_payload=hotspot_payload,
            coordinate_audit_payload=coordinate_audit_payload,
            pair_schedule_payload=pair_schedule_payload,
        ),
        encoding="utf-8",
    )
    analysis_bot_context = build_analysis_bot_context(
        project_name=doc.project_name or "Proyecto",
        nasas_root=nasas_root,
        run_label=args.output.parent.name,
        summary_payload={
            "generated_at": generated_at,
            "project_name": doc.project_name,
            "analysis_profile": _analysis_profile_label(args),
            "status": "completed",
        }
        | overall_metrics,
        readiness_payload=readiness_payload,
        coordinate_audit_payload=coordinate_audit_payload,
        pair_schedule_payload=pair_schedule_payload,
        report_context=technical_report_context,
        semantic_elements_payload=semantic_elements_payload,
        clash_element_links_payload=clash_element_links_payload,
    )
    _write_json(analysis_bot_context_json, analysis_bot_context)
    human_report_md = render_coordination_human_report_markdown(
        project_name=doc.project_name or "Proyecto",
        run_label=args.output.parent.name,
        summary_payload={
            "generated_at": generated_at,
            "project_name": doc.project_name,
            "analysis_profile": _analysis_profile_label(args),
            "status": "completed",
        }
        | overall_metrics,
        readiness_payload=readiness_payload,
        coordinate_audit_payload=coordinate_audit_payload,
        pair_schedule_payload=pair_schedule_payload,
        report_context=technical_report_context,
        clash_element_links_payload=clash_element_links_payload,
    )
    coordination_human_md.write_text(human_report_md, encoding="utf-8")
    coordination_human_html.write_text(
        render_coordination_human_report_html(
            project_name=doc.project_name or "Proyecto",
            run_label=args.output.parent.name,
            markdown=human_report_md,
        ),
        encoding="utf-8",
    )

    return _write_fast_compare_summary(
        args=args,
        doc=doc,
        nasas_root=nasas_root,
        readiness_json=readiness_json,
        readiness_md=readiness_md,
        coordinate_audit_json=coordinate_audit_json,
        coordinate_audit_md=coordinate_audit_md,
        pair_schedule_json=pair_schedule_json,
        selected_candidates=selected_candidates,
        all_elements=all_elements,
        primary_incidents=primary_incidents,
        debug_conflicts=debug_conflicts,
        suppressed_elements=suppressed_elements,
        status="completed",
        metrics=overall_metrics,
        primary_json=primary_json,
        primary_md=primary_md,
        debug_json=debug_json,
        hotspot_json=hotspot_json if hotspot_incidents else None,
        hotspot_md=hotspot_md if hotspot_incidents else None,
        technical_report_md=technical_report_md,
        technical_report_context_json=technical_report_context_json,
        analysis_bot_context_json=analysis_bot_context_json,
        coordination_human_md=coordination_human_md,
        coordination_human_html=coordination_human_html,
        elements_by_dwg_json=elements_by_dwg_json if semantic_elements_payload else None,
        clash_element_links_json=clash_element_links_json if clash_element_links_payload else None,
    )


def _build_fast_compare_primary_conflicts(
    *,
    all_elements: list[Element25D],
    registry,
    strict_levels: bool,
    required_disciplines: tuple,
    min_plan_area_mm2: float = 0.5,
) -> list[ClashConflict]:
    grouped: dict[tuple[str, str], list[Element25D]] = defaultdict(list)
    for element in all_elements:
        if not primary_geometry_role(element):
            continue
        grouped[
            (
                str(element.metadata.get("cohort_id") or "__missing__"),
                str(element.metadata.get("file_level_id") or element.z_data.level_id),
            )
        ].append(element)

    conflicts: list[ClashConflict] = []
    required = {discipline.value for discipline in required_disciplines}
    for (_, _level_id), group in sorted(grouped.items()):
        disciplines = {element.discipline.value for element in group}
        if not required.issubset(disciplines):
            continue
        conflicts.extend(
            clash_pairs(
                group,
                registry,
                strict_levels=strict_levels,
                min_plan_area_mm2=min_plan_area_mm2,
            )
        )
    conflicts.sort(key=lambda item: (-item.overlap_depth_z_mm, -item.plan_intersection_area_mm2))
    return conflicts


def _build_fast_compare_debug_conflicts(
    *,
    all_elements: list[Element25D],
    registry,
    strict_levels: bool,
    required_disciplines: tuple,
    primary_conflicts: list[ClashConflict],
    element_lookup: dict[str, Element25D],
) -> list[ClashConflict]:
    primary_keys = {(conflict.element_id_a, conflict.element_id_b) for conflict in primary_conflicts}
    grouped: dict[str, list[Element25D]] = defaultdict(list)
    for element in all_elements:
        grouped[str(element.metadata.get("cohort_id") or "__missing__")].append(element)

    required = {discipline.value for discipline in required_disciplines}
    debug: list[ClashConflict] = []
    for _, group in sorted(grouped.items()):
        disciplines = {element.discipline.value for element in group}
        if not required.issubset(disciplines):
            continue
        for conflict in clash_pairs(
            group,
            registry,
            strict_levels=strict_levels,
            min_plan_area_mm2=0.5,
        ):
            if (conflict.element_id_a, conflict.element_id_b) in primary_keys:
                continue
            if _is_debug_conflict(conflict, element_lookup):
                debug.append(conflict)
    debug.sort(key=lambda item: (-item.overlap_depth_z_mm, -item.plan_intersection_area_mm2))
    return debug


def _is_debug_conflict(conflict: ClashConflict, element_lookup: dict[str, Element25D]) -> bool:
    if conflict.level_ids[0] != conflict.level_ids[1]:
        return True
    element_a = element_lookup.get(conflict.element_id_a)
    element_b = element_lookup.get(conflict.element_id_b)
    if element_a is None or element_b is None:
        return True
    if not primary_geometry_role(element_a) or not primary_geometry_role(element_b):
        return True
    return any("bbox" in source for source in conflict.geometry_sources)


def _build_hotspot_incidents(
    *,
    primary_conflicts: list[ClashConflict],
    debug_conflicts: list[ClashConflict],
) -> list:
    scored_pairs: Counter[tuple[str, str]] = Counter()
    for conflict in primary_conflicts + debug_conflicts:
        file_pair = tuple(sorted(ref.split("|", 1)[0] for ref in conflict.source_refs))
        score = 2 if any("polyline" in source for source in conflict.geometry_sources) else 1
        scored_pairs[file_pair] += score
    top_pairs = {pair for pair, _score in scored_pairs.most_common(8)}
    if not top_pairs:
        return []
    hotspot_conflicts = [
        conflict
        for conflict in primary_conflicts + debug_conflicts
        if tuple(sorted(ref.split("|", 1)[0] for ref in conflict.source_refs)) in top_pairs
    ]
    return group_conflicts_into_incidents(hotspot_conflicts, cell_size_mm=1000.0)


def _write_fast_compare_summary(
    *,
    args: argparse.Namespace,
    doc: ProjectLevelRegistryDocument,
    nasas_root: Path,
    readiness_json: Path,
    readiness_md: Path,
    coordinate_audit_json: Path | None,
    coordinate_audit_md: Path | None,
    pair_schedule_json: Path | None,
    selected_candidates: list,
    all_elements: list[Element25D],
    primary_incidents: list,
    debug_conflicts: list[ClashConflict],
    suppressed_elements: list[Element25D],
    status: str,
    metrics: dict[str, object] | None = None,
    primary_json: Path | None = None,
    primary_md: Path | None = None,
    debug_json: Path | None = None,
    hotspot_json: Path | None = None,
    hotspot_md: Path | None = None,
    technical_report_md: Path | None = None,
    technical_report_context_json: Path | None = None,
    analysis_bot_context_json: Path | None = None,
    coordination_human_md: Path | None = None,
    coordination_human_html: Path | None = None,
    elements_by_dwg_json: Path | None = None,
    clash_element_links_json: Path | None = None,
) -> int:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_name": doc.project_name,
        "analysis_profile": _analysis_profile_label(args),
        "status": status,
        "nasas_root": str(nasas_root),
        "selected_candidate_count": len(selected_candidates),
        "element_count": len(all_elements),
        "primary_incident_count": len(primary_incidents),
        "debug_conflict_count": len(debug_conflicts),
        "suppressed_element_count": len(suppressed_elements),
        "comparison_readiness_report_json": str(readiness_json),
        "comparison_readiness_report_md": str(readiness_md),
        "coordinate_audit_json": str(coordinate_audit_json) if coordinate_audit_json else None,
        "coordinate_audit_md": str(coordinate_audit_md) if coordinate_audit_md else None,
        "pair_schedule_json": str(pair_schedule_json) if pair_schedule_json else None,
        "primary_incidents_json": str(primary_json) if primary_json else None,
        "primary_incidents_md": str(primary_md) if primary_md else None,
        "debug_candidates_json": str(debug_json) if debug_json else None,
        "hotspot_incidents_json": str(hotspot_json) if hotspot_json else None,
        "hotspot_incidents_md": str(hotspot_md) if hotspot_md else None,
        "technical_coordination_report_md": str(technical_report_md) if technical_report_md else None,
        "coordination_report_context_json": str(technical_report_context_json) if technical_report_context_json else None,
        "analysis_bot_context_json": str(analysis_bot_context_json) if analysis_bot_context_json else None,
        "coordination_report_human_md": str(coordination_human_md) if coordination_human_md else None,
        "coordination_report_human_html": str(coordination_human_html) if coordination_human_html else None,
        "elements_by_dwg_json": str(elements_by_dwg_json) if elements_by_dwg_json else None,
        "clash_element_links_json": str(clash_element_links_json) if clash_element_links_json else None,
    }
    if metrics:
        payload.update(metrics)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if status == "readiness_only":
        logger.info("Fast compare listo solo para readiness: %s", readiness_md)
        return 0
    logger.info(
        "Fast compare: %s (%d incidencias primarias, %d debug, %d elementos)",
        args.output,
        len(primary_incidents),
        len(debug_conflicts),
        len(all_elements),
    )
    for line in _render_primary_incident_lines(primary_incidents)[:30]:
        print(line)
    if len(primary_incidents) > 30:
        print(f"... y {len(primary_incidents) - 30} incidencias mas (ver JSON/MD).")
    return 0


def _render_primary_incident_lines(incidents: list) -> list[str]:
    lines: list[str] = []
    for incident in incidents:
        representative = incident.representative_conflict
        x, y = incident.plan_centroid_mm
        bounds = incident.plan_bounds_mm
        lines.append(
            "- "
            f"`{Path(incident.file_pair[0]).name}` vs `{Path(incident.file_pair[1]).name}`: "
            f"{incident.member_count} miembros, nivel `{incident.level_id}`, "
            f"centro ({round(x):,}, {round(y):,}) mm, "
            f"bounds [{round(bounds[0]):,}, {round(bounds[1]):,}, {round(bounds[2]):,}, {round(bounds[3]):,}] mm, "
            f"geometrias {' / '.join(incident.geometry_sources)}, confianza {incident.confidence}, "
            f"conflicto ref `{representative.element_id_a}` vs `{representative.element_id_b}`"
        )
    return lines


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
