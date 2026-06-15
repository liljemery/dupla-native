"""
Base contracts for the multi-discipline engine architecture.

Each discipline (arquitectura, estructura, electrico, sanitario) implements
the ``DisciplineEngine`` protocol.  The classifier remains a shared service
parametrized by ``ChapterConfig``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from core.schemas import LevelInventory, QuantityTakeoff


# ---------------------------------------------------------------------------
# Chapter configuration (consumed by the shared BC3 classifier)
# ---------------------------------------------------------------------------

@dataclass
class ChapterDefinition:
    code: str
    title: str
    desc: str
    tokens: set[str]


@dataclass
class ChapterConfig:
    chapters: dict[str, ChapterDefinition]
    item_type_to_chapter: dict[str, str]
    prefix_to_chapter: list[tuple[str, str]]
    static_guidance: dict[str, str]
    default_chapter: str = "09"

    def assign_chapter(self, item_type: str) -> str:
        item_type = item_type.lower()
        ch = self.item_type_to_chapter.get(item_type)
        if ch:
            return ch
        for prefix, code in self.prefix_to_chapter:
            if item_type.startswith(prefix):
                return code
        return self.default_chapter


# ---------------------------------------------------------------------------
# Discipline configuration
# ---------------------------------------------------------------------------

@dataclass
class DisciplineConfig:
    discipline_id: str
    display_name: str
    prompts_dir: Path
    rules_path: Path | None = None
    chapter_config: ChapterConfig | None = None
    item_types: set[str] = field(default_factory=set)
    bc3_chapter_filter: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Engine protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class DisciplineEngine(Protocol):
    config: DisciplineConfig

    def build_vision_prompt(
        self,
        cad_summary: dict[str, Any],
        methodology: str,
    ) -> tuple[str, str]:
        """Return (system_message, user_message) for OpenAI vision."""
        ...

    def build_inventory(
        self,
        cad_facts: dict[str, Any],
        vision_results: list[dict[str, Any]],
    ) -> list[LevelInventory]:
        """Merge CAD + vision into discipline-specific inventory."""
        ...

    def quantify(
        self,
        levels: list[LevelInventory],
    ) -> list[QuantityTakeoff]:
        """Discipline-specific quantification formulas."""
        ...

    def get_chapter_config(self) -> ChapterConfig:
        """Return chapter config for the shared BC3 classifier."""
        ...
