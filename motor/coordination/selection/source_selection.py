"""Source selection and exclusion rules for NASAS coordination runs."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from coordination.core.registry import SourceExcludePattern

MEDIA_SUFFIXES = {".dwg", ".dxf", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}

_DEFAULT_EXCLUDE_PATTERNS = (
    r"(^|/)pdf images(/|$)",
    r"(^|/)revision(/|$)",
    r"vision_merge_",
    r"solapado",
    r"overlay",
    r"solicitud de informacion",
    r"listado de chequeo",
)


def normalize_source_text(value: str) -> str:
    """Lowercase and strip accents to keep regex matching predictable."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_only.lower().replace("\\", "/")


def default_source_exclude_patterns() -> list[SourceExcludePattern]:
    return [SourceExcludePattern(pattern=pattern) for pattern in _DEFAULT_EXCLUDE_PATTERNS]


def relative_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def should_include_source(
    path: Path,
    *,
    nasas_root: Path,
    extra_patterns: list[SourceExcludePattern] | None = None,
    require_planos_recibidos: bool = True,
) -> tuple[bool, str | None]:
    if not path.is_file():
        return (False, "not_file")
    if path.suffix.lower() not in MEDIA_SUFFIXES:
        return (False, "unsupported_suffix")

    rel = relative_posix(path, nasas_root)
    rel_norm = normalize_source_text(rel)
    if require_planos_recibidos and "/planos recibidos/" not in f"/{rel_norm}/":
        return (False, "outside_planos_recibidos")

    patterns = list(extra_patterns or [])
    patterns.extend(default_source_exclude_patterns())

    for rule in patterns:
        if re.search(normalize_source_text(rule.pattern), rel_norm):
            return (False, rule.reason or f"excluded_by_pattern:{rule.pattern}")

    if _is_derived_pdf_image(path, rel_norm):
        return (False, "derived_pdf_image")
    return (True, None)


def _is_derived_pdf_image(path: Path, rel_norm: str) -> bool:
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
        return False
    if "/pdf images/" in f"/{rel_norm}/":
        return True
    stem_norm = normalize_source_text(path.stem)
    if len(stem_norm) > 8 and re.search(r"[0-9a-f]{8}$", stem_norm):
        candidate_prefix = stem_norm[:-8]
        for sibling in path.parent.parent.glob("*.pdf"):
            if normalize_source_text(sibling.stem).startswith(candidate_prefix):
                return True
    return False


def collect_coordination_media(
    nasas_root: Path,
    *,
    extra_patterns: list[SourceExcludePattern] | None = None,
    require_planos_recibidos: bool = True,
) -> tuple[list[Path], dict[str, int]]:
    if not nasas_root.is_dir():
        return ([], {})
    selected: list[Path] = []
    skipped: dict[str, int] = {}
    for path in sorted(nasas_root.rglob("*")):
        if not path.is_file():
            continue
        keep, reason = should_include_source(
            path,
            nasas_root=nasas_root,
            extra_patterns=extra_patterns,
            require_planos_recibidos=require_planos_recibidos,
        )
        if keep:
            selected.append(path)
        elif reason:
            skipped[reason] = skipped.get(reason, 0) + 1
    return (_prefer_dxf_over_dwg(selected, skipped), skipped)


def _prefer_dxf_over_dwg(paths: list[Path], skipped: dict[str, int]) -> list[Path]:
    preferred: dict[tuple[Path, str], Path] = {}
    for path in paths:
        key = (path.parent.resolve(), path.stem.lower())
        current = preferred.get(key)
        if current is None:
            preferred[key] = path
            continue
        if current.suffix.lower() == ".dwg" and path.suffix.lower() == ".dxf":
            preferred[key] = path
            skipped["duplicate_dwg_replaced_by_dxf"] = skipped.get("duplicate_dwg_replaced_by_dxf", 0) + 1
            continue
        if current.suffix.lower() == ".dxf" and path.suffix.lower() == ".dwg":
            skipped["duplicate_dwg_replaced_by_dxf"] = skipped.get("duplicate_dwg_replaced_by_dxf", 0) + 1
            continue
    return sorted(preferred.values())
