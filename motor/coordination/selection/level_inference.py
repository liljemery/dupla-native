"""Level inference helpers for PDF pages, APS views, and file names."""

from __future__ import annotations

import re
from dataclasses import dataclass

from coordination.core.registry import ProjectLevelRegistryDocument, ViewLevelPattern
from coordination.selection.source_selection import normalize_source_text


@dataclass(frozen=True)
class LevelResolution:
    level_id: str
    source: str
    matched_pattern: str | None = None


def infer_level_from_text(
    text: str,
    *,
    doc: ProjectLevelRegistryDocument | None,
    default_level_id: str,
    fallback_source: str = "default_level",
) -> LevelResolution:
    normalized = normalize_source_text(text)
    if doc is not None:
        for rule in doc.view_level_patterns:
            compiled = _compile_pattern(rule)
            if compiled.search(normalized):
                return LevelResolution(
                    level_id=rule.level_id,
                    source=rule.source or f"pattern:{rule.level_id}",
                    matched_pattern=rule.pattern,
                )
    return LevelResolution(level_id=default_level_id, source=fallback_source)


def infer_level_from_pdf_page(
    *,
    page_text: str,
    page_label: str,
    file_name: str,
    doc: ProjectLevelRegistryDocument | None,
    default_level_id: str,
    page_index: int,
    page_z_step_mm: float,
) -> tuple[LevelResolution, float]:
    joined = "\n".join(part for part in (file_name, page_label, page_text) if part)
    resolution = infer_level_from_text(
        joined,
        doc=doc,
        default_level_id=default_level_id,
        fallback_source="page_index_fallback" if page_z_step_mm > 0 else "default_level",
    )
    if resolution.source == "page_index_fallback":
        return (resolution, float(page_index) * page_z_step_mm)
    return (resolution, 0.0)


def infer_level_from_view_name(
    view_name: str,
    *,
    doc: ProjectLevelRegistryDocument | None,
    default_level_id: str,
) -> LevelResolution:
    return infer_level_from_text(
        view_name,
        doc=doc,
        default_level_id=default_level_id,
        fallback_source="default_level",
    )


def extract_sheet_name(text: str, *, fallback: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line:
            return line[:160]
    return fallback


def _compile_pattern(rule: ViewLevelPattern) -> re.Pattern[str]:
    flags = 0
    if "i" in rule.flags.lower():
        flags |= re.IGNORECASE
    return re.compile(normalize_source_text(rule.pattern), flags=flags)
