"""Build staging layout and runner arguments for Dupla coordination."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VALID_PROFILES = frozenset({"tortuga_c40", "serena18", "nasas09"})

PROFILE_ALIASES: dict[str, str] = {
    "tortuga_c40": "tortuga_c40",
    "tortuga-c40": "tortuga_c40",
    "tortuga": "tortuga_c40",
    "serena_18": "serena18",
    "serena18": "serena18",
    "serena": "serena18",
    "nasas_09": "nasas09",
    "nasas09": "nasas09",
    "nasas": "nasas09",
}

PROFILE_PROJECT_NAMES: dict[str, str] = {
    "tortuga_c40": "TORTUGA C40 — coordinación 2.5D",
    "serena18": "SERENA 18 — registro provisional de niveles para coordinacion 2.5D",
    "nasas09": "NASAS 09 — registro de niveles (cotas N extraídas del CAD normalizado)",
}

DISCIPLINE_STAGING_DIRS: dict[str, str] = {
    "arquitectura": "PLANOS RECIBIDOS/ARQUITECTONICOS",
    "estructura": "PLANOS RECIBIDOS/TECNICOS/ESTRUCTURAL",
    "mecanica": "PLANOS RECIBIDOS/TECNICOS/MECANICA",
    "electrica": "PLANOS RECIBIDOS/TECNICOS/ELECTRICO",
    "plomeria": "PLANOS RECIBIDOS/TECNICOS/SANITARIO",
    "sin_clasificar": "PLANOS RECIBIDOS/SIN_CLASIFICAR",
}

DISCIPLINE_LABELS: dict[str, str] = {
    "arquitectura": "Arquitectura",
    "estructura": "Estructura",
    "mecanica": "Mecánica",
    "electrica": "Eléctrica",
    "plomeria": "Plomería",
    "sin_clasificar": "Sin clasificar",
}


def normalize_profile_slug(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    key = re.sub(r"[^a-z0-9]+", "_", str(raw).strip().lower()).strip("_")
    key = key.replace("_c_40", "_c40")
    if key in PROFILE_ALIASES:
        return PROFILE_ALIASES[key]
    if key in VALID_PROFILES:
        return key
    return None


def resolve_profile_slug(
    explicit: str | None,
    project_code: str | None,
    project_name: str | None,
) -> str | None:
    slug = normalize_profile_slug(explicit)
    if slug:
        return slug
    for candidate in (project_code, project_name):
        if not candidate or not str(candidate).strip():
            continue
        text = str(candidate)
        for pattern, profile in (
            (re.compile(r"\btortuga\b", re.I), "tortuga_c40"),
            (re.compile(r"\bserena\b", re.I), "serena18"),
            (re.compile(r"\bnasas\b", re.I), "nasas09"),
        ):
            if pattern.search(text):
                return profile
    default = os.getenv("COORDINATION_DEFAULT_PROFILE", "").strip()
    return normalize_profile_slug(default) if default else None


def _dupla_root() -> Path:
    return Path(os.getenv("DUPLA_ROOT", "/dupla"))


def registry_path_for_profile(profile_slug: str) -> Path | None:
    root = _dupla_root()
    candidates = {
        "nasas09": root / "var" / "fixtures" / "nasas09" / "coordination" / "sample_project_levels.json",
        "serena18": root / "repositorios" / "SERENA 18" / "coordination" / "serena18_project_levels.json",
        "tortuga_c40": root / "repositorios" / "TORTUGA C40" / "coordination" / "tortuga_c40_project_levels.json",
    }
    path = candidates.get(profile_slug)
    return path if (path and path.is_file()) else None


def _minimal_registry(project_name: str) -> dict[str, Any]:
    return {
        "project_name": project_name,
        "view_level_patterns": [
            {"pattern": "planta|nivel|piso|floor", "level_id": "GENERAL", "source": "pattern:generic"},
            {"pattern": "cimientos|fundacion|foundation", "level_id": "CIMENTACION", "source": "pattern:cimentacion"},
            {"pattern": "techo|losa|roof", "level_id": "TECHO", "source": "pattern:techo"},
        ],
        "levels": [
            {
                "id": "GENERAL",
                "name": "Nivel general",
                "offset_to_project_zero_mm": 0.0,
                "discipline_origin": "ARQUITECTURA",
                "provisional": True,
            }
        ],
    }


def _resolve_staging_bucket(entry: dict[str, Any]) -> str:
    bucket = str(entry.get("discipline_bucket") or entry.get("discipline") or "").strip().lower()
    if bucket in DISCIPLINE_STAGING_DIRS:
        return bucket
    return "sin_clasificar"


def _runner_disciplines_from_buckets(buckets_present: set[str]) -> list[str]:
    order = ("arquitectura", "estructura", "electrica", "mecanica", "plomeria")
    out: list[str] = []
    mapping = {
        "arquitectura": "ARQUITECTURA",
        "estructura": "ESTRUCTURA",
        "electrica": "ELECTRICIDAD",
        "mecanica": "CLIMATIZACION",
        "plomeria": "FONTANERIA",
    }
    for bucket in order:
        if bucket in buckets_present and bucket in mapping:
            out.append(mapping[bucket])
    return out


def _stage_companion_pdf(dest_dir: Path, source_path: Path | None, original_name: str) -> None:
    """Copy companion PDF next to staged DWG so extraction/export can find it."""
    if source_path is None or not source_path.is_file():
        return
    try:
        dupla_root = _dupla_root()
        root_str = str(dupla_root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        from coordination.extraction.companion_pdf import resolve_companion_pdf

        pdf = resolve_companion_pdf(source_path)
        if pdf is not None and pdf.is_file():
            shutil.copy2(pdf, dest_dir / pdf.name)
            logger.info("PDF compañero copiado: %s -> %s", pdf.name, dest_dir)
    except Exception as exc:
        logger.warning("No se pudo copiar PDF compañero para %s: %s", original_name, exc)


def stage_project_inputs(
    *,
    file_entries: list[dict[str, Any]],
    output_dir: Path,
    project_name: str,
    profile_slug: str | None = None,
) -> dict[str, Any]:
    inputs_dir = output_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    staged: list[dict[str, str]] = []
    analyzed_documents: list[dict[str, Any]] = []
    has_explicit_pdf_entries = any(
        str(entry.get("original_name") or "").lower().endswith(".pdf")
        for entry in file_entries
    )

    for idx, entry in enumerate(file_entries):
        original_name = str(entry.get("original_name") or f"file_{idx + 1}.dwg")
        content = entry.get("content")
        file_path = entry.get("path")

        if isinstance(content, (bytes, bytearray)):
            file_bytes: bytes | None = bytes(content)
        elif file_path and Path(file_path).is_file():
            file_bytes = Path(file_path).read_bytes()
        else:
            logger.warning("Skipping entry %s: no content or valid path", original_name)
            continue

        bucket = _resolve_staging_bucket(entry)
        rel_dir = DISCIPLINE_STAGING_DIRS.get(bucket, DISCIPLINE_STAGING_DIRS["sin_clasificar"])
        dest_dir = inputs_dir / rel_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(original_name).name
        dest = dest_dir / safe_name
        dest.write_bytes(file_bytes)
        source_path = Path(file_path) if file_path and Path(file_path).is_file() else None
        if safe_name.lower().endswith(".dwg") and source_path is not None and not has_explicit_pdf_entries:
            _stage_companion_pdf(dest_dir, source_path, safe_name)
        staged.append({"file_name": safe_name, "path": str(dest), "discipline_bucket": bucket})
        analyzed_documents.append(
            {
                "id": f"doc-{idx + 1}",
                "file_name": safe_name,
                "discipline_label": DISCIPLINE_LABELS.get(bucket, bucket.title()),
                "status": "ok",
                "retryable": False,
            }
        )

    registry_path = output_dir / "project_levels.json"
    effective_profile = resolve_profile_slug(profile_slug, None, project_name)
    if not effective_profile or effective_profile in ("folder", "auto"):
        effective_profile = resolve_profile_slug(None, None, project_name)

    if effective_profile and effective_profile not in ("folder", "auto"):
        source_registry = registry_path_for_profile(effective_profile)
        if source_registry is not None:
            shutil.copy2(source_registry, registry_path)
            try:
                reg = json.loads(registry_path.read_text(encoding="utf-8"))
                if isinstance(reg, dict):
                    reg["project_name"] = project_name
                    registry_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
            except (json.JSONDecodeError, OSError):
                pass
        else:
            registry_path.write_text(
                json.dumps(_minimal_registry(project_name), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    else:
        registry_path.write_text(
            json.dumps(_minimal_registry(project_name), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    buckets_present = {s["discipline_bucket"] for s in staged if s["discipline_bucket"] != "sin_clasificar"}
    include_disciplines = _runner_disciplines_from_buckets(buckets_present)

    return {
        "inputs_dir": str(inputs_dir),
        "registry_path": str(registry_path),
        "analyzed_documents": analyzed_documents,
        "staged_files": staged,
        "include_disciplines": include_disciplines,
    }
