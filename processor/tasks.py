import tempfile
import asyncio
import os
import json
import shutil
import uuid
import unicodedata
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from aps_integration.aps_auth import get_aps_token
from aps_integration.oss_manager import create_bucket, upload_file_to_bucket, APS_BUCKET_NAME
from aps_integration.model_derivative import extract_dwg_data
from agents.vision_agent import VISION_PROMPT_VERSION, run_full_vision_analysis, vision_model_id
from processors.json_processor import process_autodesk_json
from knowledge.bc3_embeddings import load_or_build_embeddings
from knowledge.methodology_generator import generate_methodology_context
from knowledge.training_data import extract_training_pairs
from processors.bc3_parser import merge_bc3_catalogs, parse_bc3
from core.pipeline import build_budget_from_sources
from core.schemas import ProjectContext
from disciplines import get_engine

from pricing.excel_price_loader import load_or_cache_constructor_pricing
from pricing.apu_matcher import APUMatcher

# --- Phase 1 port: full-engine modules (vision/exports wired in later phases) ---
from budget.export_bc3 import export_budget_bc3
from budget.export_excel import export_budget_workbook
from core.output_structure import RunOutputDir
from core.location_parser import parse_location_from_filename
from core.quality_engine import write_input_gaps_markdown, write_quality_report_json
from disciplines.domain_rules import load_domain_rules_for_discipline
from disciplines.domain_validator import (
    validate_vision_output,
    write_missing_attributes_report,
    write_unclassified_report,
)
from analysis.day1_prep import build_day1_artifacts
from analysis.day2_prep import build_day2_dataset_artifacts
from pricing.excel_price_loader import load_or_cache_constructor_pricing
from pricing.apu_matcher import APUMatcher
from core.stage_cache import (
    _STATS,
    cache_get,
    cache_set,
    cached_stage,
    compose_key,
    log_stats_summary,
    reset_stats,
    sha256_bytes,
    sha256_json,
)

import logging

logger = logging.getLogger(__name__)


_STANDARD_DISCIPLINES = ("arquitectura", "estructura", "sanitario", "electrico")
_BASE_EXTRACTION_ALIASES = {
    "",
    "base",
    "base_extraction",
    "classification",
    "clasificacion",
    "extract",
    "extract_only",
}
_ALL_DISCIPLINE_ALIASES = {"all", "todas", "todos", "todo", "*"}
_DISCIPLINE_ALIASES = {
    "arquitectonica": "arquitectura",
    "arquitectonico": "arquitectura",
    "arq": "arquitectura",
    "estructural": "estructura",
    "est": "estructura",
    "volumetria": "estructura",
    "electrica": "electrico",
    "electricidad": "electrico",
    "elec": "electrico",
    "sanitaria": "sanitario",
    "plomeria": "sanitario",
    "hidrosanitario": "sanitario",
}
_EXTRACTION_ARTIFACT_VERSION = "extraction-v1"
_DEFAULT_ARTIFACT_DIR = "/app/artifacts"


@dataclass(frozen=True)
class ExtractionArtifacts:
    artifact_key: str
    artifact_dir: Path
    raw_json_path: Path
    normalized_json_path: Path
    pages_dir: Path
    page_paths: list[Path]
    raw_data: list[dict[str, Any]]
    normalized: dict[str, Any]
    manifest: dict[str, Any]
    cache_hit: bool


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        logger.warning("%s=%r is invalid; using %d", name, raw, default)
        return default


def _safe_upload_name(filename: str | None, fallback: str) -> str:
    value = Path(filename or fallback).name.strip()
    return value or fallback


def _artifact_root() -> Path:
    return Path(os.getenv("DUPLA_ARTIFACT_DIR") or _DEFAULT_ARTIFACT_DIR)


def _artifact_dir(artifact_key: str) -> Path:
    return _artifact_root() / artifact_key[:2] / artifact_key


def _artifact_ready(path: Path) -> bool:
    return (
        path.exists()
        and (path / ".ready").exists()
        and (path / "manifest.json").exists()
        and (path / "raw.json").exists()
        and (path / "normalized.json").exists()
    )


def _build_artifact_key(
    dwg_files: list[tuple[str, bytes]],
    pdf_files: list[tuple[str, bytes]],
    *,
    pdf_dpi: int,
) -> str:
    payload = {
        "version": _EXTRACTION_ARTIFACT_VERSION,
        "aps_views": ["2d"],
        "pdf_dpi": pdf_dpi,
        "dwg_files": [
            {
                "name": _safe_upload_name(name, f"upload_{idx}.dwg"),
                "sha256": sha256_bytes(content),
            }
            for idx, (name, content) in enumerate(dwg_files)
        ],
        "pdf_files": [
            {
                "name": _safe_upload_name(name, f"upload_{idx}.pdf"),
                "sha256": sha256_bytes(content),
            }
            for idx, (name, content) in enumerate(pdf_files)
        ],
    }
    return sha256_json(payload)


def _split_disciplines(raw: str) -> list[str]:
    return [
        _normalize_discipline_token(part)
        for part in raw.replace(";", ",").split(",")
        if part.strip()
    ]


def _normalize_discipline_token(value: str | None) -> str:
    text = (value or "").strip().lower()
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _resolve_target_disciplines(
    discipline_id: str | None,
    filenames: list[str],
) -> tuple[list[str], str]:
    """Resolve requested disciplines.

    Empty/base means extraction-only. Multi-discipline is opt-in because it is
    the x4 multiplier that makes local iteration painful.
    """
    raw = _normalize_discipline_token(discipline_id)
    allow_multi = _env_bool("DUPLA_ALLOW_MULTI_DISCIPLINE", False)

    if raw in _BASE_EXTRACTION_ALIASES:
        return [], "base_extraction"

    if raw in _ALL_DISCIPLINE_ALIASES:
        if allow_multi:
            return list(_STANDARD_DISCIPLINES), "all_explicit"
        inferred = _infer_discipline_from_filenames(filenames)
        logger.warning(
            "Discipline '%s' requested but DUPLA_ALLOW_MULTI_DISCIPLINE is disabled; "
            "running inferred single discipline '%s'.",
            raw,
            inferred,
        )
        return [inferred], "all_limited_to_inferred"

    requested = _split_disciplines(raw)
    if not requested:
        return [], "base_extraction"

    requested = [_DISCIPLINE_ALIASES.get(item, item) for item in requested]

    invalid = [item for item in requested if item not in _STANDARD_DISCIPLINES]
    if invalid:
        raise RuntimeError(
            "Invalid discipline(s): "
            + ", ".join(invalid)
            + ". Expected one of: "
            + ", ".join(_STANDARD_DISCIPLINES)
            + ", or base_extraction."
        )

    unique: list[str] = []
    for item in requested:
        if item not in unique:
            unique.append(item)

    if len(unique) > 1 and not allow_multi:
        logger.warning(
            "Multiple disciplines requested (%s) but DUPLA_ALLOW_MULTI_DISCIPLINE is disabled; "
            "running only '%s'.",
            unique,
            unique[0],
        )
        return [unique[0]], "multi_limited_to_first"

    return unique, "explicit"


# ---------------------------------------------------------------------------
# Training pair quality helpers (ported from dupla_run_nasas.py)
# ---------------------------------------------------------------------------

def _is_likely_valid_code(code: str) -> bool:
    value = (code or "").strip()
    if not value or " " in value:
        return False
    return len(value) <= 32


def _is_likely_valid_unit(unit: str) -> bool:
    value = (unit or "").strip()
    if not value or len(value) > 16 or value.count(" ") > 1:
        return False
    return True


def _source_quality_score(pairs: list) -> float:
    if not pairs:
        return 0.0
    valid = sum(
        1 for p in pairs
        if _is_likely_valid_code(getattr(p, "output_bc3_code", ""))
        and _is_likely_valid_unit(getattr(p, "output_unit", ""))
        and bool(str(getattr(p, "output_description", "")).strip())
    )
    return valid / len(pairs)

def render_pdf_to_images(pdf_path: Path, output_dir: Path, dpi: int = 200) -> list[Path]:
    """Render every PDF page to PNG; cached by content+dpi.

    Cache payload stores per-page filenames + base64-encoded PNG bytes so a hit
    re-materializes the files on disk under `output_dir` without invoking fitz.
    """
    import base64
    import fitz

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_bytes = pdf_path.read_bytes()
    cache_key = compose_key(sha256_bytes(pdf_bytes), f"dpi={dpi}")

    def _render() -> list[dict]:
        doc = fitz.open(pdf_path)
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pages: list[dict] = []
        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png_bytes = pix.tobytes("png")
            pages.append({
                "filename": f"page_{page_index + 1:04d}.png",
                "png_b64": base64.b64encode(png_bytes).decode("ascii"),
            })
        return pages

    pages = cached_stage("pdf_render", cache_key, _render)
    image_paths: list[Path] = []
    for entry in pages:
        path = output_dir / entry["filename"]
        if not path.exists():
            path.write_bytes(base64.b64decode(entry["png_b64"]))
        image_paths.append(path)
    return image_paths

def _merge_cad_facts(base: dict, new: dict) -> None:
    """Merge CAD facts from multiple DWGs into a single unified dict.

    Ported verbatim from dupla_run_nasas.py: accumulates total_objects,
    extends cad_facts collections, merges layers by name and inventory_hints.
    """
    if not base:
        base.update(new)
        return
    base["total_objects"] = base.get("total_objects", 0) + new.get("total_objects", 0)
    if "cad_facts" in new:
        if "cad_facts" not in base:
            base["cad_facts"] = {}
        for key in ["texts", "dimensions", "hatches", "blocks", "geometry_hints"]:
            base["cad_facts"].setdefault(key, []).extend(new["cad_facts"].get(key, []))
        base_layers = base["cad_facts"].setdefault("layers", {})
        for layer, metrics in new["cad_facts"].get("layers", {}).items():
            if layer not in base_layers:
                base_layers[layer] = metrics
            else:
                base_layers[layer]["object_count"] += metrics.get("object_count", 0)
                for et, count in metrics.get("entity_types", {}).items():
                    base_layers[layer]["entity_types"][et] = base_layers[layer]["entity_types"].get(et, 0) + count
                base_layers[layer]["sample_names"] = list(set(base_layers[layer].get("sample_names", []) + metrics.get("sample_names", [])))[:5]
                base_layers[layer]["handles"] = list(set(base_layers[layer].get("handles", []) + metrics.get("handles", [])))[:5]
    if "inventory_hints" in new:
        if "inventory_hints" not in base:
            base["inventory_hints"] = {}
        for key in ["level_markers", "scale_dimensions"]:
            base["inventory_hints"].setdefault(key, []).extend(new["inventory_hints"].get(key, []))
        bf1 = {x["block_name"]: x["count"] for x in base["inventory_hints"].get("block_frequency", [])}
        for x in new["inventory_hints"].get("block_frequency", []):
            bf1[x["block_name"]] = bf1.get(x["block_name"], 0) + x["count"]
        base["inventory_hints"]["block_frequency"] = [{"block_name": k, "count": v} for k, v in sorted(bf1.items(), key=lambda i: i[1], reverse=True)][:25]
        base["inventory_hints"]["layer_names"] = sorted(list(set(base["inventory_hints"].get("layer_names", []) + new["inventory_hints"].get("layer_names", []))))


def _load_extraction_artifacts(artifact_key: str, *, cache_hit: bool) -> ExtractionArtifacts:
    artifact_dir = _artifact_dir(artifact_key)
    manifest_path = artifact_dir / "manifest.json"
    raw_json_path = artifact_dir / "raw.json"
    normalized_json_path = artifact_dir / "normalized.json"
    pages_dir = artifact_dir / "pages"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_data = json.loads(raw_json_path.read_text(encoding="utf-8"))
    normalized = json.loads(normalized_json_path.read_text(encoding="utf-8"))
    page_paths: list[Path] = []
    for page in manifest.get("pages", []):
        rel_path = str(page.get("relative_path") or "").strip()
        if not rel_path:
            continue
        page_path = artifact_dir / rel_path
        if page_path.exists():
            page_paths.append(page_path)

    return ExtractionArtifacts(
        artifact_key=artifact_key,
        artifact_dir=artifact_dir,
        raw_json_path=raw_json_path,
        normalized_json_path=normalized_json_path,
        pages_dir=pages_dir,
        page_paths=page_paths,
        raw_data=raw_data if isinstance(raw_data, list) else [],
        normalized=normalized if isinstance(normalized, dict) else {},
        manifest=manifest if isinstance(manifest, dict) else {},
        cache_hit=cache_hit,
    )


def _render_pdf_artifacts(
    pdf_files: list[tuple[str, bytes]],
    *,
    work_dir: Path,
    pages_dir: Path,
    pdf_dpi: int,
) -> tuple[list[dict[str, Any]], list[Path]]:
    pages_dir.mkdir(parents=True, exist_ok=True)
    pdf_upload_dir = work_dir / "pdf_uploads"
    pdf_upload_dir.mkdir(parents=True, exist_ok=True)
    rendered_work_dir = work_dir / "rendered_work"
    rendered_work_dir.mkdir(parents=True, exist_ok=True)

    page_manifest: list[dict[str, Any]] = []
    page_paths: list[Path] = []
    for pdf_index, (filename, content) in enumerate(pdf_files):
        safe_name = _safe_upload_name(filename, f"upload_{pdf_index}.pdf")
        pdf_path = pdf_upload_dir / safe_name
        pdf_path.write_bytes(content)
        logger.info("Rendering PDF pages from %s", pdf_path.name)

        source_render_dir = rendered_work_dir / f"pdf_{pdf_index + 1:03d}"
        try:
            rendered_pages = render_pdf_to_images(pdf_path, source_render_dir, dpi=pdf_dpi)
        except Exception as exc:
            logger.warning("Failed to render PDF %s: %s", pdf_path.name, exc)
            continue

        for page_index, rendered_page in enumerate(rendered_pages):
            suffix = rendered_page.suffix.lower() or ".png"
            target_name = f"pdf_{pdf_index + 1:03d}_page_{page_index + 1:04d}{suffix}"
            target_path = pages_dir / target_name
            if not target_path.exists():
                shutil.copyfile(rendered_page, target_path)
            page_paths.append(target_path)
            page_manifest.append(
                {
                    "source_pdf": safe_name,
                    "page_index": page_index + 1,
                    "filename": target_name,
                    "relative_path": f"pages/{target_name}",
                }
            )

    return page_manifest, page_paths


def _build_extraction_artifacts(
    dwg_files: list[tuple[str, bytes]],
    pdf_files: list[tuple[str, bytes]],
    *,
    artifact_key: str,
    pdf_dpi: int,
) -> ExtractionArtifacts:
    root = _artifact_root()
    final_dir = _artifact_dir(artifact_key)
    tmp_root = root / "_tmp"
    tmp_dir = tmp_root / f"{artifact_key}-{uuid.uuid4().hex}"

    root.mkdir(parents=True, exist_ok=True)
    tmp_root.mkdir(parents=True, exist_ok=True)
    if final_dir.exists() and not _artifact_ready(final_dir):
        logger.warning("Removing stale incomplete extraction artifact at %s", final_dir)
        shutil.rmtree(final_dir, ignore_errors=True)

    outputs_dir = tmp_dir / "outputs"
    uploads_dir = tmp_dir / "dwg_uploads"
    pages_dir = tmp_dir / "pages"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)

    bucket_name = os.getenv("APS_BUCKET_NAME", "dupla_processing_bucket")
    aps_views_signature = "2d"
    aps_token: list[str] = []
    aps_session_lock = threading.Lock()

    def _ensure_aps_session() -> str:
        with aps_session_lock:
            if not aps_token:
                token = get_aps_token()
                create_bucket(token, bucket_name)
                aps_token.append(token)
        return aps_token[0]

    cad_facts: dict[str, Any] = {}
    all_raw_data: list[dict[str, Any]] = []
    dwg_manifest: list[dict[str, Any]] = []

    async def _extract_all_dwg_raw_data() -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(30)
        work_items: list[dict[str, Any]] = []

        for idx, (filename, content) in enumerate(dwg_files):
            safe_name = _safe_upload_name(filename, f"upload_{idx}.dwg")
            dwg_path = uploads_dir / safe_name
            dwg_path.write_bytes(content)
            dwg_hash = sha256_bytes(content)
            cache_key = compose_key(
                dwg_hash,
                _EXTRACTION_ARTIFACT_VERSION,
                f"views={aps_views_signature}",
            )
            work_items.append(
                {
                    "idx": idx,
                    "safe_name": safe_name,
                    "dwg_path": dwg_path,
                    "dwg_hash": dwg_hash,
                    "cache_key": cache_key,
                }
            )

        async def _upload_one(item: dict[str, Any]) -> dict[str, Any]:
            idx = int(item["idx"])
            dwg_path = item["dwg_path"]
            safe_name = str(item["safe_name"])

            def _upload() -> str:
                logger.info("APS upload (%d/%d): %s", idx + 1, len(dwg_files), dwg_path.name)
                token = _ensure_aps_session()
                object_name = upload_file_to_bucket(
                    token,
                    bucket_name,
                    str(dwg_path),
                    unique_suffix=f"api_job_{idx}",
                )
                if not object_name:
                    raise RuntimeError(f"DWG upload to Autodesk failed: {dwg_path.name}")
                return object_name

            async with semaphore:
                object_name = await asyncio.to_thread(_upload)
            enriched = dict(item)
            enriched["object_name"] = object_name
            enriched["token"] = _ensure_aps_session()
            return enriched

        async def _translate_one(item: dict[str, Any]) -> dict[str, Any]:
            idx = int(item["idx"])
            safe_name = str(item["safe_name"])
            dwg_hash = str(item["dwg_hash"])
            cache_key = str(item["cache_key"])
            object_name = str(item["object_name"])
            token = str(item["token"])

            def _extract_via_aps() -> dict[str, Any]:
                logger.info(
                    "APS translate+poll (%d/%d): %s",
                    idx + 1,
                    len(dwg_files),
                    safe_name,
                )
                return extract_dwg_data(
                    token,
                    bucket_name,
                    object_name,
                    views=("2d",),
                    translation_timeout_seconds=_env_int("APS_TRANSLATION_TIMEOUT_SECONDS", 3600),
                    poll_interval_seconds=_env_int("APS_POLL_INTERVAL_SECONDS", 3),
                    max_property_wait_seconds=_env_int("APS_PROPERTY_WAIT_SECONDS", 3600),
                    failed_manifest_grace_polls=3,
                    failed_manifest_grace_sleep_seconds=20,
                )

            t0 = asyncio.get_running_loop().time()
            async with semaphore:
                raw_data = await asyncio.to_thread(_extract_via_aps)
            _STATS.bump("aps_extract", seconds_saved_estimate=asyncio.get_running_loop().time() - t0)
            cache_set("aps_extract", cache_key, raw_data)
            return {
                "idx": idx,
                "dwg": safe_name,
                "sha256": dwg_hash,
                "data": raw_data,
            }

        logger.info(
            "Launching APS DWG extraction concurrently: files=%d concurrency=30",
            len(work_items),
        )
        cached_results: list[dict[str, Any]] = []
        misses: list[dict[str, Any]] = []
        for item in work_items:
            cache_key = str(item["cache_key"])
            cached = cache_get("aps_extract", cache_key)
            if cached is not None:
                cached_results.append(
                    {
                        "idx": int(item["idx"]),
                        "dwg": str(item["safe_name"]),
                        "sha256": str(item["dwg_hash"]),
                        "data": cached,
                    }
                )
            else:
                _STATS.bump("aps_extract", misses=1)
                misses.append(item)

        if not misses:
            return cached_results

        logger.info("APS upload phase: %d cache misses", len(misses))
        uploaded = list(await asyncio.gather(*[_upload_one(item) for item in misses]))
        logger.info("APS translate phase: %d uploaded DWGs", len(uploaded))
        translated = list(await asyncio.gather(*[_translate_one(item) for item in uploaded]))
        return cached_results + translated

    try:
        extracted_raw_items = sorted(
            asyncio.run(_extract_all_dwg_raw_data()),
            key=lambda item: int(item["idx"]),
        )
        for raw_item in extracted_raw_items:
            idx = int(raw_item["idx"])
            safe_name = str(raw_item["dwg"])
            dwg_hash = str(raw_item["sha256"])
            raw_data = raw_item["data"]
            all_raw_data.append({"dwg": safe_name, "sha256": dwg_hash, "data": raw_data})
            dwg_manifest.append({"filename": safe_name, "sha256": dwg_hash})

            temp_raw_json = outputs_dir / f"raw_{idx}.json"
            temp_raw_json.write_text(
                json.dumps(raw_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            partial_facts = process_autodesk_json(str(temp_raw_json))
            _merge_cad_facts(cad_facts, partial_facts)

        page_manifest, _ = _render_pdf_artifacts(
            pdf_files,
            work_dir=tmp_dir,
            pages_dir=pages_dir,
            pdf_dpi=pdf_dpi,
        )

        raw_json_path = tmp_dir / "raw.json"
        normalized_json_path = tmp_dir / "normalized.json"
        manifest_path = tmp_dir / "manifest.json"

        raw_json_path.write_text(
            json.dumps(all_raw_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        normalized_json_path.write_text(
            json.dumps(cad_facts, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        manifest = {
            "artifact_key": artifact_key,
            "version": _EXTRACTION_ARTIFACT_VERSION,
            "extractor": "aps_model_derivative",
            "aps_views": ["2d"],
            "pdf_dpi": pdf_dpi,
            "dwg_files": dwg_manifest,
            "pdf_files": [
                {
                    "filename": _safe_upload_name(name, f"upload_{idx}.pdf"),
                    "sha256": sha256_bytes(content),
                }
                for idx, (name, content) in enumerate(pdf_files)
            ],
            "raw_json": "raw.json",
            "normalized_json": "normalized.json",
            "pages_dir": "pages",
            "pages": page_manifest,
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (tmp_dir / ".ready").write_text("ok\n", encoding="utf-8")

        final_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp_dir.replace(final_dir)
        except OSError:
            if _artifact_ready(final_dir):
                logger.info("Extraction artifact %s was created by another worker", artifact_key)
                shutil.rmtree(tmp_dir, ignore_errors=True)
            else:
                raise

        return _load_extraction_artifacts(artifact_key, cache_hit=False)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def _load_or_build_extraction_artifacts(
    dwg_files: list[tuple[str, bytes]],
    pdf_files: list[tuple[str, bytes]],
    *,
    pdf_dpi: int,
) -> ExtractionArtifacts:
    forced_key = (os.getenv("DUPLA_USE_ARTIFACT_KEY") or "").strip()
    artifact_key = forced_key or _build_artifact_key(dwg_files, pdf_files, pdf_dpi=pdf_dpi)
    artifact_dir = _artifact_dir(artifact_key)

    if _artifact_ready(artifact_dir):
        logger.info("Extraction artifact HIT: %s", artifact_key)
        return _load_extraction_artifacts(artifact_key, cache_hit=True)

    if forced_key:
        raise RuntimeError(f"DUPLA_USE_ARTIFACT_KEY={forced_key} was requested but no ready artifact exists")
    if _env_bool("DUPLA_SKIP_APS", False):
        raise RuntimeError(
            "DUPLA_SKIP_APS=1 but no extraction artifact exists for these inputs. "
            "Run base_extraction once first or set DUPLA_USE_ARTIFACT_KEY."
        )

    logger.info("Extraction artifact MISS: %s", artifact_key)
    return _build_extraction_artifacts(
        dwg_files,
        pdf_files,
        artifact_key=artifact_key,
        pdf_dpi=pdf_dpi,
    )


def _archive_directory(path: Path) -> str:
    return shutil.make_archive(str(path), "zip", root_dir=str(path))


def _base_extraction_result(
    *,
    artifacts: ExtractionArtifacts,
    project_name: str,
    suggested_discipline: str,
) -> dict[str, Any]:
    archive_path = _archive_directory(artifacts.artifact_dir)
    return {
        "rows": [],
        "domain_validations": [],
        "extraction": {
            "mode": "base_extraction",
            "artifact_key": artifacts.artifact_key,
            "artifact_cache_hit": artifacts.cache_hit,
            "project_name": project_name,
            "suggested_discipline": suggested_discipline,
            "page_count": len(artifacts.page_paths),
            "cad_layer_count": len(artifacts.normalized.get("cad_facts", {}).get("layers", {})),
        },
        "output": {
            "mode": "base_extraction",
            "artifact_key": artifacts.artifact_key,
            "run_dir": str(artifacts.artifact_dir),
            "disciplines": [],
            "archive": archive_path,
            "requires_rerun": True,
            "artifacts": {
                "manifest": str(artifacts.artifact_dir / "manifest.json"),
                "raw_json": str(artifacts.raw_json_path),
                "normalized_json": str(artifacts.normalized_json_path),
                "pages_dir": str(artifacts.pages_dir),
            },
        },
    }


def _vision_artifact_path(
    artifacts: ExtractionArtifacts,
    *,
    discipline_id: str,
    methodology: str | None,
) -> Path:
    cache_key = sha256_json(
        {
            "artifact_key": artifacts.artifact_key,
            "discipline_id": discipline_id,
            "methodology_hash": sha256_json(methodology or "")[:16],
            "vision_model": vision_model_id(),
            "vision_prompt_version": VISION_PROMPT_VERSION,
        }
    )
    return artifacts.artifact_dir / "vision" / f"{discipline_id}_{cache_key[:16]}.json"


def _vision_error_stats(payload: Any) -> tuple[int, int, float]:
    if not isinstance(payload, list):
        return 0, 0, 1.0
    total = len(payload)
    if total == 0:
        return 0, 0, 1.0
    error_count = sum(
        1
        for item in payload
        if isinstance(item, dict) and "error" in item
    )
    return error_count, total, error_count / total


def _load_or_build_vision_results(
    *,
    artifacts: ExtractionArtifacts,
    normalized: dict[str, Any],
    discipline_id: str,
    methodology: str | None,
) -> list[dict[str, Any]]:
    if _env_bool("DUPLA_SKIP_VISION", False):
        logger.warning("DUPLA_SKIP_VISION=1; using CAD-only inventory for %s", discipline_id)
        return []
    if not artifacts.page_paths:
        return []

    vision_path = _vision_artifact_path(
        artifacts,
        discipline_id=discipline_id,
        methodology=methodology,
    )
    if vision_path.exists():
        logger.info("Vision artifact HIT for %s: %s", discipline_id, vision_path)
        payload = json.loads(vision_path.read_text(encoding="utf-8"))
        error_count, total, error_ratio = _vision_error_stats(payload)
        logger.info(
            "Vision artifact HIT stats for %s: errors=%d/%d ratio=%.2f",
            discipline_id,
            error_count,
            total,
            error_ratio,
        )
        if error_ratio >= 0.5:
            logger.error(
                "Vision artifact poisoned for %s: errors=%d/%d ratio=%.2f. "
                "Deleting and rebuilding: %s",
                discipline_id,
                error_count,
                total,
                error_ratio,
                vision_path,
            )
            try:
                vision_path.unlink()
            except FileNotFoundError:
                pass
        else:
            return payload if isinstance(payload, list) else []

    logger.info("Vision artifact MISS for %s", discipline_id)
    vision_results = run_full_vision_analysis(
        str(artifacts.pages_dir),
        normalized,
        office_methodology=methodology,
        upload_discipline_id=discipline_id,
    )
    error_count, total, error_ratio = _vision_error_stats(vision_results)
    logger.info(
        "Vision artifact MISS build stats for %s: errors=%d/%d ratio=%.2f",
        discipline_id,
        error_count,
        total,
        error_ratio,
    )
    if error_ratio >= 0.5:
        logger.error(
            "Skipping poisoned vision artifact write for %s: errors=%d/%d ratio=%.2f path=%s",
            discipline_id,
            error_count,
            total,
            error_ratio,
            vision_path,
        )
        return vision_results

    vision_path.parent.mkdir(parents=True, exist_ok=True)
    vision_path.write_text(
        json.dumps(vision_results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return vision_results


# Discipline inference: ordered (filename keyword tuple) -> canonical discipline id.
# Canonical ids match disciplines/<id>/ folders, domain_rules paths, and the
# vision agent's _UPLOAD_DISCIPLINE_PROMPT keys.
_DISCIPLINE_FILENAME_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("electric", "electr"), "electrico"),
    (("sanitar", "plomer", "hidrosanit", "agua potable", "aguas negras", "drenaje"), "sanitario"),
    (("estructur", "encofrado", "cimiento"), "estructura"),
    (("arquitect", "arq.", "arq-", "arq "), "arquitectura"),
]
_DEFAULT_DISCIPLINE = "arquitectura"


def _infer_discipline_from_filenames(filenames: list[str]) -> str:
    """Infer the canonical discipline id from uploaded file names.

    Names are checked in order (PDF first when the caller passes it first);
    the first file matching any keyword group wins. Falls back to
    'arquitectura' when nothing matches.
    """
    for name in filenames:
        low = (name or "").lower()
        for keywords, discipline in _DISCIPLINE_FILENAME_HINTS:
            if any(kw in low for kw in keywords):
                return discipline
    return _DEFAULT_DISCIPLINE


def _run_dupla_pipeline_legacy(
    dwg_files: list[tuple[str, bytes]],
    pdf_files: list[tuple[str, bytes]] = None,
    discipline_id: str | None = None,
    project_name: str | None = None,
    correlation_id: str = "unknown",
) -> dict:
    """Runs the core budget processing pipeline.

    Args:
        dwg_files: list of (filename, content) tuples. Each DWG is extracted
            via APS independently and merged into a single unified cad_facts.
        pdf_files: list of (filename, content) tuples for PDFs. All PDFs are
            rendered and passed to vision analysis.
        discipline_id: canonical discipline (arquitectura | estructura |
            electrico | sanitario). When None, inferred from the file names.
        project_name: optional project name from the backend; used in exports
            and reports. Defaults to ``"Dupla API Job"`` when not provided.
        correlation_id: request correlation id, propagated for log tracing.
    """
    logger.info(f"Starting pipeline with correlation ID: {correlation_id}")
    reset_stats()

    # Lightweight preflight logging (non-blocking).
    if not os.getenv("CLIENT_ID") or not os.getenv("CLIENT_SECRET"):
        logger.warning("APS credentials may be missing: CLIENT_ID or CLIENT_SECRET not set")
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY not set — PartidaGenerator will be disabled")

    resolved_project_name = (project_name or "").strip() or "Dupla API Job"
    logger.info("Project name: %s | Discipline: %s", resolved_project_name, discipline_id or "(auto-detect)")

    if not dwg_files:
        raise RuntimeError("No DWG files provided")

    # Resolve target disciplines: an explicit specific request wins.
    # If None, empty or "todas", we run all 4 standard disciplines.
    raw_disc = (discipline_id or "").strip().lower()
    
    if raw_disc and raw_disc != "todas":
        # Validate or fallback to inferred if it doesn't make sense?
        # For safety, if they explicitly sent a single one, run just that.
        target_disciplines = [raw_disc]
        inferred = False
    else:
        # Run all disciplines
        target_disciplines = ["arquitectura", "estructura", "sanitario", "electrico"]
        inferred = True

    logger.info("Target disciplines resolved: %s (inferred all: %s)", target_disciplines, inferred)

    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        outputs_dir = base_dir / "outputs"
        outputs_dir.mkdir(exist_ok=True)

        # 1. APS Extraction (multi-DWG -> merged cad_facts) — cached per DWG content hash
        bucket_name = os.getenv("APS_BUCKET_NAME", "dupla_processing_bucket")
        _aps_views_signature = "2d"  # MUST be bumped if extract_dwg_data params change
        _aps_token: list = []  # lazy: only fetch on first miss
        _aps_bucket_created = [False]

        def _ensure_aps_session() -> str:
            if not _aps_token:
                tok = get_aps_token()
                create_bucket(tok, bucket_name)
                _aps_token.append(tok)
                _aps_bucket_created[0] = True
            return _aps_token[0]

        cad_facts: dict = {}
        all_raw_data: list[dict] = []
        for idx, (filename, content) in enumerate(dwg_files):
            dwg_path = base_dir / (filename or f"upload_{idx}.dwg")
            dwg_path.write_bytes(content)
            dwg_hash = sha256_bytes(content)
            cache_key = compose_key(dwg_hash, _aps_views_signature)

            def _extract_via_aps(_idx=idx, _path=dwg_path, _cache_key=cache_key):
                logger.info("APS extraction (%d/%d): %s", _idx + 1, len(dwg_files), _path.name)
                tok = _ensure_aps_session()
                object_name = upload_file_to_bucket(
                    tok, bucket_name, str(_path), unique_suffix=f"api_job_{_idx}"
                )
                if not object_name:
                    raise RuntimeError(f"DWG upload to Autodesk failed: {_path.name}")
                return extract_dwg_data(
                    tok, bucket_name, object_name,
                    views=("2d",),
                    translation_timeout_seconds=3600,
                    poll_interval_seconds=10,
                    max_property_wait_seconds=3600,
                    failed_manifest_grace_polls=3,
                    failed_manifest_grace_sleep_seconds=20,
                )

            raw_data = cached_stage("aps_extract", cache_key, _extract_via_aps)
            all_raw_data.append({"dwg": dwg_path.name, "data": raw_data})

            temp_raw_json = outputs_dir / f"raw_{idx}.json"
            temp_raw_json.write_text(json.dumps(raw_data, indent=2, ensure_ascii=False), encoding="utf-8")
            partial_facts = process_autodesk_json(str(temp_raw_json))
            _merge_cad_facts(cad_facts, partial_facts)

        raw_json_path = outputs_dir / "raw.json"
        raw_json_path.write_text(json.dumps(all_raw_data, indent=2, ensure_ascii=False), encoding="utf-8")

        normalized = cad_facts
        normalized_json_path = outputs_dir / "normalized.json"
        normalized_json_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Merged cad_facts: %d layers", len(normalized.get("cad_facts", {}).get("layers", {})))

        # 2. Vision Pages
        pages_dir = base_dir / "rendered_pages"
        pages_dir.mkdir(exist_ok=True)
        page_paths = []
        
        pdf_files = pdf_files or []
        for idx, (filename, content) in enumerate(pdf_files):
            pdf_path = base_dir / (filename or f"upload_{idx}.pdf")
            pdf_path.write_bytes(content)
            logger.info("Rendering PDF pages from %s", pdf_path.name)
            try:
                paths = render_pdf_to_images(pdf_path, pages_dir)
                page_paths.extend(paths)
            except Exception as exc:
                logger.warning("Failed to render PDF %s: %s", pdf_path.name, exc)
                
        logger.info("Total PDF pages rendered: %d", len(page_paths))

        # 3. Knowledge — multi-BC3 merge (same as NASAS runner)
        data_dir = Path("/app/data")
        bc3_files = sorted(data_dir.glob("*.bc3"))
        if bc3_files:
            catalogs = [parse_bc3(str(p)) for p in bc3_files]
            for p, cat in zip(bc3_files, catalogs):
                logger.info("BC3 loaded: %s (%d items)", p.name, len(cat.get("items", [])))
            bc3_catalog = merge_bc3_catalogs(*catalogs) if len(catalogs) > 1 else catalogs[0]
            logger.info(
                "BC3 combined catalog: %d items from %d file(s)",
                len(bc3_catalog.get("items", [])), len(catalogs),
            )
        else:
            bc3_catalog = {}
            logger.warning("No .bc3 files found in %s", data_dir)

        embedding_index = load_or_build_embeddings(bc3_catalog) if bc3_catalog.get("items") else None

        # Training pairs from the reference PRES.xlsx (few-shot context for BC3 matching).
        pres_path = Path("/app/data/PRES.xlsx")
        training_pairs: list = []
        if pres_path.exists():
            try:
                training_pairs = extract_training_pairs(str(pres_path))
                quality = _source_quality_score(training_pairs)
                logger.info(
                    "Training pairs loaded: %d from %s (quality=%.2f)",
                    len(training_pairs), pres_path.name, quality,
                )
                if training_pairs and quality < 0.75:
                    logger.warning(
                        "Training source quality %.2f below threshold 0.75, discarding",
                        quality,
                    )
                    training_pairs = []
            except Exception as exc:
                logger.warning("Failed to load training pairs from %s: %s", pres_path, exc)
        else:
            logger.warning("PRES.xlsx not found at %s — training pairs empty", pres_path)

        # Constructor Pricing Store and APU Matcher (like NASAS)
        pricing_excel_path = Path("/app/data/Lista de precios-analisis-MO.xlsx")
        pricing_store = None
        apu_matcher = None
        if pricing_excel_path.exists():
            try:
                pricing_store = load_or_cache_constructor_pricing(pricing_excel_path, project_id="api_job")
                apu_matcher = APUMatcher(pricing_store)
                logger.info("Constructor PricingStore & APUMatcher loaded successfully (materials=%d, apus=%d).", 
                            len(pricing_store.materials), len(pricing_store.apus))
            except Exception as exc:
                logger.error("Failed to load Constructor PricingStore: %s", exc)
        else:
            logger.warning("Constructor PricingStore Excel NOT FOUND at %s", pricing_excel_path)

        # Methodology context: auto-generated + manual office methodology (same as NASAS).
        auto_methodology = generate_methodology_context(
            training_pairs=training_pairs or None,
            bc3_catalog=bc3_catalog or None,
            discipline=discipline_id,
        ) or ""

        office_meth_path = Path("/app/knowledge/office_methodology.md")
        office_meth = ""
        if office_meth_path.exists():
            office_meth = office_meth_path.read_text(encoding="utf-8").strip()
            logger.info("Office methodology loaded: %d chars", len(office_meth))

        parts = [p for p in [auto_methodology, office_meth] if p.strip()]
        methodology = "\n\n---\n\n".join(parts) if parts else None
        if methodology:
            logger.info("Combined methodology context: %d chars", len(methodology))

        # Location parsing from uploaded file names (same as NASAS runner).
        building_block, level_id = None, None
        if pdf_files and pdf_files[0][0]:
            building_block, level_id = parse_location_from_filename(pdf_files[0][0])
        if not building_block and dwg_files:
            building_block, level_id = parse_location_from_filename(dwg_files[0][0])

        # 4. Process Disciplines (Loop)
        output_base = os.getenv("DUPLA_OUTPUT_DIR", "/app/output")
        run_dir = RunOutputDir(output_base, resolved_project_name)
        
        master_rows = []
        master_artifacts = {}
        all_domain_validations = []
        
        import asyncio

        for disc_id in target_disciplines:
            logger.info("--- Processing Discipline: %s ---", disc_id)
            
            # 4a. Vision Analysis
            vision_results = []
            if page_paths:
                vision_results = run_full_vision_analysis(
                    str(pages_dir),
                    normalized,
                    office_methodology=methodology,
                    upload_discipline_id=disc_id,
                )

            # 4b. Domain validation against the resolved discipline's rules
            domain_rules = load_domain_rules_for_discipline(disc_id)
            domain_validation_summary: dict | None = None
            validation = None
            if domain_rules and vision_results:
                validation = validate_vision_output(vision_results, domain_rules, resolved_project_name)
                domain_validation_summary = {
                    "discipline_id": domain_rules.discipline_id,
                    "classified": len(validation.classified),
                    "belongs": len(validation.belongs),
                    "not_belongs": len(validation.not_belongs),
                    "unclassified": len(validation.unclassified),
                    "missing_attributes": len(validation.missing_attributes),
                }
                logger.info(
                    "Domain validation [%s]: %d belongs, %d not_belongs, %d unclassified, %d missing attrs",
                    domain_rules.discipline_id,
                    len(validation.belongs), len(validation.not_belongs),
                    len(validation.unclassified), len(validation.missing_attributes),
                )
            elif not domain_rules:
                logger.warning("No domain_rules.yaml for discipline '%s' — skipping domain validation", disc_id)

            # 5. Build Budget
            allowed_types = sorted(domain_rules.budget_item_types) if domain_rules else None
            bc3_path_value = str(bc3_catalog.get("path") or "")

            context = ProjectContext(
                project_id="api_job",
                project_name=resolved_project_name,
                building_block=building_block,
                level_id=level_id,
                source_json_path=str(raw_json_path),
                plan_image_paths=[str(p) for p in page_paths],
                bc3_path=bc3_path_value or None,
                metadata={
                    "discipline_id": disc_id,
                    "allowed_item_types": allowed_types,
                    "xlsx_path": str(pres_path) if pres_path.exists() else None,
                    "pres_template_takeoffs": False,
                    "enable_semantic_layer": True,
                },
            )

            budget = asyncio.run(build_budget_from_sources(
                context=context,
                cad_facts=normalized,
                vision_payloads=vision_results,
                bc3_catalog=bc3_catalog,
                embedding_index=embedding_index,
                training_pairs=training_pairs,
                pricing_store=pricing_store,
                apu_matcher=apu_matcher,
            ))

            if domain_validation_summary is not None:
                budget["domain_validation"] = domain_validation_summary
                all_domain_validations.append(domain_validation_summary)

            if budget.get("rows"):
                master_rows.extend(budget["rows"])

            # 6. Persist individual deliverables to run directory
            budget_json_path = run_dir.discipline_budget_json(disc_id)
            budget_json_path.write_text(json.dumps(budget, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            master_artifacts[f"budget_json_{disc_id}"] = str(budget_json_path)

            vision_json_path = run_dir.discipline_vision_json(disc_id)
            vision_json_path.write_text(json.dumps(vision_results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            master_artifacts[f"vision_json_{disc_id}"] = str(vision_json_path)

            excel_path = None
            try:
                excel_path = export_budget_workbook(
                    context, budget["rows"], run_dir.discipline_excel(disc_id),
                    sheet_name=disc_id.upper(),
                    quality_report=budget.get("quality_report"),
                )
                master_artifacts[f"excel_{disc_id}"] = str(excel_path)
            except Exception as exc:
                logger.error("Excel export failed [%s]: %s", disc_id, exc)

            try:
                bc3_export_path = export_budget_bc3(
                    context, budget["rows"], run_dir.discipline_bc3(disc_id),
                    bc3_catalog=bc3_catalog,
                )
                master_artifacts[f"bc3_{disc_id}"] = str(bc3_export_path)
            except Exception as exc:
                logger.error("BC3 export failed [%s]: %s", disc_id, exc)

            quality_report = budget.get("quality_report")
            if quality_report:
                try:
                    qpath = write_quality_report_json(quality_report, run_dir.discipline_quality_json(disc_id))
                    gpath = write_input_gaps_markdown(quality_report, run_dir.discipline_input_gaps_md(disc_id))
                    master_artifacts[f"quality_report_{disc_id}"] = str(qpath)
                    master_artifacts[f"input_gaps_{disc_id}"] = str(gpath)
                except Exception as exc:
                    logger.warning("Quality report write failed: %s", exc)

            if validation is not None:
                write_unclassified_report(validation, run_dir.unclassified_elements)
                write_missing_attributes_report(validation, run_dir.discipline_missing_attrs(disc_id))

        # Package all deliverables into a single downloadable archive.
        archive_path = shutil.make_archive(str(run_dir.root), "zip", root_dir=str(run_dir.root))

        master_budget = {
            "rows": master_rows,
            "domain_validations": all_domain_validations,
            "output": {
                "run_dir": str(run_dir.root),
                "disciplines": target_disciplines,
                "archive": archive_path,
                "artifacts": master_artifacts,
            }
        }
        
        logger.info("Run artifacts persisted: %s (archive: %s) with %d total rows", run_dir.root, archive_path, len(master_rows))

        log_stats_summary()
        return master_budget


def run_dupla_pipeline(
    dwg_files: list[tuple[str, bytes]],
    pdf_files: list[tuple[str, bytes]] = None,
    discipline_id: str | None = None,
    project_name: str | None = None,
    correlation_id: str = "unknown",
) -> dict:
    """Run the Fase 1/2 pipeline.

    Fase 1:
        - Empty discipline means base_extraction, not "run all four".
        - Multi-discipline runs are blocked unless explicitly enabled with
          DUPLA_ALLOW_MULTI_DISCIPLINE=1.

    Fase 2:
        - APS/PDF extraction is materialized once into a content-addressed
          artifact under DUPLA_ARTIFACT_DIR.
        - Budget iterations reuse that artifact and only run calculation/exports.
        - Vision output is persisted per artifact + discipline + methodology.
    """
    logger.info("Starting Fase 1/2 pipeline with correlation ID: %s", correlation_id)
    reset_stats()

    pdf_files = pdf_files or []
    resolved_project_name = (project_name or "").strip() or "Dupla API Job"
    forced_artifact = bool((os.getenv("DUPLA_USE_ARTIFACT_KEY") or "").strip())
    if not dwg_files and not forced_artifact:
        raise RuntimeError("No DWG files provided")

    if not os.getenv("CLIENT_ID") or not os.getenv("CLIENT_SECRET"):
        logger.warning("APS credentials may be missing: CLIENT_ID or CLIENT_SECRET not set")
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY not set; OpenAI-backed stages will use fallbacks where available")

    filenames = [name for name, _ in [*dwg_files, *pdf_files]]
    target_disciplines, discipline_mode = _resolve_target_disciplines(discipline_id, filenames)
    suggested_discipline = _infer_discipline_from_filenames(filenames)
    logger.info(
        "Project=%s | requested_discipline=%s | resolved=%s | mode=%s | suggested=%s",
        resolved_project_name,
        discipline_id or "(base_extraction)",
        target_disciplines or ["base_extraction"],
        discipline_mode,
        suggested_discipline,
    )

    pdf_dpi = _env_int("DUPLA_PDF_DPI", 200, minimum=72)
    artifacts = _load_or_build_extraction_artifacts(
        dwg_files,
        pdf_files,
        pdf_dpi=pdf_dpi,
    )
    normalized = artifacts.normalized
    raw_json_path = artifacts.raw_json_path
    page_paths = artifacts.page_paths
    logger.info(
        "Extraction artifact ready: key=%s hit=%s pages=%d layers=%d",
        artifacts.artifact_key,
        artifacts.cache_hit,
        len(page_paths),
        len(normalized.get("cad_facts", {}).get("layers", {})),
    )

    if not target_disciplines:
        result = _base_extraction_result(
            artifacts=artifacts,
            project_name=resolved_project_name,
            suggested_discipline=suggested_discipline,
        )
        log_stats_summary()
        return result

    data_dir = Path("/app/data")
    bc3_files = sorted(data_dir.glob("*.bc3"))
    if bc3_files:
        catalogs = [parse_bc3(str(path)) for path in bc3_files]
        for path, catalog in zip(bc3_files, catalogs):
            logger.info("BC3 loaded: %s (%d items)", path.name, len(catalog.get("items", [])))
        bc3_catalog = merge_bc3_catalogs(*catalogs) if len(catalogs) > 1 else catalogs[0]
        logger.info(
            "BC3 combined catalog: %d items from %d file(s)",
            len(bc3_catalog.get("items", [])),
            len(catalogs),
        )
    else:
        bc3_catalog = {}
        logger.warning("No .bc3 files found in %s", data_dir)

    embedding_index = None
    if bc3_catalog.get("items"):
        try:
            embedding_index = load_or_build_embeddings(bc3_catalog)
        except Exception:
            logger.warning("Failed to load/build BC3 embeddings; continuing without them", exc_info=True)

    pres_path = Path("/app/data/PRES.xlsx")
    training_pairs: list = []
    if pres_path.exists():
        try:
            training_pairs = extract_training_pairs(str(pres_path))
            quality = _source_quality_score(training_pairs)
            logger.info(
                "Training pairs loaded: %d from %s (quality=%.2f)",
                len(training_pairs),
                pres_path.name,
                quality,
            )
            if training_pairs and quality < 0.75:
                logger.warning("Training source quality %.2f below threshold 0.75, discarding", quality)
                training_pairs = []
        except Exception as exc:
            logger.warning("Failed to load training pairs from %s: %s", pres_path, exc)
    else:
        logger.warning("PRES.xlsx not found at %s; training pairs empty", pres_path)

    pricing_excel_path = Path("/app/data/Lista de precios-analisis-MO.xlsx")
    pricing_store = None
    apu_matcher = None
    if pricing_excel_path.exists():
        try:
            pricing_store = load_or_cache_constructor_pricing(pricing_excel_path, project_id="api_job")
            apu_matcher = APUMatcher(pricing_store)
            logger.info(
                "Constructor PricingStore & APUMatcher loaded (materials=%d, apus=%d).",
                len(pricing_store.materials),
                len(pricing_store.apus),
            )
        except Exception as exc:
            logger.error("Failed to load Constructor PricingStore: %s", exc)
    else:
        logger.warning("Constructor PricingStore Excel not found at %s", pricing_excel_path)

    methodology_discipline = target_disciplines[0] if len(target_disciplines) == 1 else None
    auto_methodology = generate_methodology_context(
        training_pairs=training_pairs or None,
        bc3_catalog=bc3_catalog or None,
        discipline=methodology_discipline,
    ) or ""

    office_meth_path = Path("/app/knowledge/office_methodology.md")
    office_meth = ""
    if office_meth_path.exists():
        office_meth = office_meth_path.read_text(encoding="utf-8").strip()
        logger.info("Office methodology loaded: %d chars", len(office_meth))

    parts = [part for part in [auto_methodology, office_meth] if part.strip()]
    methodology = "\n\n---\n\n".join(parts) if parts else None
    if methodology:
        logger.info("Combined methodology context: %d chars", len(methodology))

    building_block, level_id = None, None
    source_pdf_names = [name for name, _ in pdf_files] or [
        str(item.get("filename") or "") for item in artifacts.manifest.get("pdf_files", [])
    ]
    source_dwg_names = [name for name, _ in dwg_files] or [
        str(item.get("filename") or "") for item in artifacts.manifest.get("dwg_files", [])
    ]
    if source_pdf_names and source_pdf_names[0]:
        building_block, level_id = parse_location_from_filename(source_pdf_names[0])
    if not building_block and source_dwg_names:
        building_block, level_id = parse_location_from_filename(source_dwg_names[0])

    output_base = os.getenv("DUPLA_OUTPUT_DIR", "/app/output")
    run_dir = RunOutputDir(output_base, resolved_project_name)
    master_rows: list[dict[str, Any]] = []
    master_artifacts: dict[str, str] = {
        "extraction_manifest": str(artifacts.artifact_dir / "manifest.json"),
        "extraction_raw_json": str(artifacts.raw_json_path),
        "extraction_normalized_json": str(artifacts.normalized_json_path),
        "extraction_pages_dir": str(artifacts.pages_dir),
    }
    all_domain_validations: list[dict[str, Any]] = []

    import asyncio

    async def _process_discipline(disc_id: str) -> dict[str, Any]:
        logger.info("--- Processing Discipline: %s ---", disc_id)
        vision_results = await asyncio.to_thread(
            _load_or_build_vision_results,
            artifacts=artifacts,
            normalized=normalized,
            discipline_id=disc_id,
            methodology=methodology,
        )

        domain_rules = load_domain_rules_for_discipline(disc_id)
        domain_validation_summary: dict[str, Any] | None = None
        validation = None
        if domain_rules and vision_results:
            validation = validate_vision_output(vision_results, domain_rules, resolved_project_name)
            domain_validation_summary = {
                "discipline_id": domain_rules.discipline_id,
                "classified": len(validation.classified),
                "belongs": len(validation.belongs),
                "not_belongs": len(validation.not_belongs),
                "unclassified": len(validation.unclassified),
                "missing_attributes": len(validation.missing_attributes),
            }
            logger.info(
                "Domain validation [%s]: %d belongs, %d not_belongs, %d unclassified, %d missing attrs",
                domain_rules.discipline_id,
                len(validation.belongs),
                len(validation.not_belongs),
                len(validation.unclassified),
                len(validation.missing_attributes),
            )
        elif not domain_rules:
            logger.warning("No domain_rules.yaml for discipline '%s'; skipping domain validation", disc_id)

        allowed_types = sorted(domain_rules.budget_item_types) if domain_rules else None
        bc3_path_value = str(bc3_catalog.get("path") or "")
        context = ProjectContext(
            project_id="api_job",
            project_name=resolved_project_name,
            building_block=building_block,
            level_id=level_id,
            source_json_path=str(raw_json_path),
            plan_image_paths=[str(path) for path in page_paths],
            bc3_path=bc3_path_value or None,
            metadata={
                "discipline_id": disc_id,
                "allowed_item_types": allowed_types,
                "xlsx_path": str(pres_path) if pres_path.exists() else None,
                "pres_template_takeoffs": False,
                "enable_semantic_layer": True,
                "extraction_artifact_key": artifacts.artifact_key,
            },
        )

        budget = await build_budget_from_sources(
            context=context,
            cad_facts=normalized,
            vision_payloads=vision_results,
            bc3_catalog=bc3_catalog,
            embedding_index=embedding_index,
            training_pairs=training_pairs,
            pricing_store=pricing_store,
            apu_matcher=apu_matcher,
        )

        if domain_validation_summary is not None:
            budget["domain_validation"] = domain_validation_summary

        export_t0 = asyncio.get_running_loop().time()
        discipline_artifacts: dict[str, str] = {}
        budget_json_path = run_dir.discipline_budget_json(disc_id)
        await asyncio.to_thread(
            budget_json_path.write_text,
            json.dumps(budget, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        discipline_artifacts[f"budget_json_{disc_id}"] = str(budget_json_path)

        vision_json_path = run_dir.discipline_vision_json(disc_id)
        await asyncio.to_thread(
            vision_json_path.write_text,
            json.dumps(vision_results, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        discipline_artifacts[f"vision_json_{disc_id}"] = str(vision_json_path)

        try:
            excel_path = await asyncio.to_thread(
                export_budget_workbook,
                context,
                budget["rows"],
                run_dir.discipline_excel(disc_id),
                sheet_name=disc_id.upper(),
                quality_report=budget.get("quality_report"),
            )
            discipline_artifacts[f"excel_{disc_id}"] = str(excel_path)
        except Exception as exc:
            logger.error("Excel export failed [%s]: %s", disc_id, exc)

        try:
            bc3_export_path = await asyncio.to_thread(
                export_budget_bc3,
                context,
                budget["rows"],
                run_dir.discipline_bc3(disc_id),
                bc3_catalog=bc3_catalog,
            )
            discipline_artifacts[f"bc3_{disc_id}"] = str(bc3_export_path)
        except Exception as exc:
            logger.error("BC3 export failed [%s]: %s", disc_id, exc)

        quality_report = budget.get("quality_report")
        if quality_report:
            try:
                qpath = await asyncio.to_thread(
                    write_quality_report_json,
                    quality_report,
                    run_dir.discipline_quality_json(disc_id),
                )
                gpath = await asyncio.to_thread(
                    write_input_gaps_markdown,
                    quality_report,
                    run_dir.discipline_input_gaps_md(disc_id),
                )
                discipline_artifacts[f"quality_report_{disc_id}"] = str(qpath)
                discipline_artifacts[f"input_gaps_{disc_id}"] = str(gpath)
            except Exception as exc:
                logger.warning("Quality report write failed: %s", exc)

        _STATS.bump("export_total", seconds_saved_estimate=asyncio.get_running_loop().time() - export_t0)
        return {
            "discipline_id": disc_id,
            "budget": budget,
            "rows": budget.get("rows") or [],
            "artifacts": discipline_artifacts,
            "domain_validation": domain_validation_summary,
            "validation": validation,
        }

    async def _process_all_disciplines() -> list[Any]:
        # return_exceptions=True so a single discipline failure (e.g.
        # _assert_unique_takeoff_keys raising on poisoned vision data) does not
        # discard valid budgets from the other disciplines. Failures are
        # reported in master_budget["discipline_errors"].
        return await asyncio.gather(
            *(_process_discipline(disc_id) for disc_id in target_disciplines),
            return_exceptions=True,
        )

    discipline_results = asyncio.run(_process_all_disciplines())
    discipline_errors: list[dict[str, Any]] = []
    for disc_id, result in zip(target_disciplines, discipline_results):
        if isinstance(result, BaseException):
            logger.error(
                "Discipline '%s' failed: %s: %s",
                disc_id,
                type(result).__name__,
                result,
                exc_info=(type(result), result, result.__traceback__),
            )
            discipline_errors.append(
                {
                    "discipline_id": disc_id,
                    "error_type": type(result).__name__,
                    "message": str(result),
                }
            )
            continue
        validation_summary = result.get("domain_validation")
        if validation_summary is not None:
            all_domain_validations.append(validation_summary)
        master_rows.extend(result.get("rows") or [])
        master_artifacts.update(result.get("artifacts") or {})

        validation = result.get("validation")
        if validation is not None:
            write_unclassified_report(validation, run_dir.unclassified_elements)
            write_missing_attributes_report(validation, run_dir.discipline_missing_attrs(disc_id))

    archive_path = _archive_directory(run_dir.root)
    master_budget = {
        "rows": master_rows,
        "domain_validations": all_domain_validations,
        "discipline_errors": discipline_errors,
        "extraction": {
            "artifact_key": artifacts.artifact_key,
            "artifact_cache_hit": artifacts.cache_hit,
            "discipline_mode": discipline_mode,
        },
        "output": {
            "run_dir": str(run_dir.root),
            "disciplines": target_disciplines,
            "succeeded_disciplines": [
                disc for disc, result in zip(target_disciplines, discipline_results)
                if not isinstance(result, BaseException)
            ],
            "archive": archive_path,
            "artifacts": master_artifacts,
        },
    }
    logger.info(
        "Run artifacts persisted: %s (archive: %s) with %d total rows",
        run_dir.root,
        archive_path,
        len(master_rows),
    )
    log_stats_summary()
    return master_budget
