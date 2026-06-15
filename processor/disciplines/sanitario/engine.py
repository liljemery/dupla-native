"""
Sanitary/plumbing discipline engine.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core.inventory_builder import build_level_inventory
from core.schemas import LevelInventory, QuantityTakeoff, level_inventory_from_dict
from disciplines.base import ChapterConfig, DisciplineConfig
from disciplines.registry import register_engine
from rules_engine import RulesEngine, default_rules_engine

from .chapters import build_chapter_config
from .quantifier import quantify

logger = logging.getLogger("dupla.disciplines.sanitario")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PROMPTS_DIR = _REPO_ROOT / "knowledge" / "prompts" / "sanitario"


class SanitarioEngine:
    """Sanitary/plumbing discipline engine."""

    def __init__(self) -> None:
        self.config = DisciplineConfig(
            discipline_id="sanitario",
            display_name="Sanitario / Plomer\u00eda",
            prompts_dir=_PROMPTS_DIR,
            chapter_config=build_chapter_config(),
            item_types={"wet_area_count", "wet_area_area", "fixture_count", "floor_waterproofing"},
            bc3_chapter_filter={"01", "02", "03", "04", "05", "06", "09"},
        )

    def build_vision_prompt(self, cad_summary: dict[str, Any], methodology: str) -> tuple[str, str]:
        base_path = self.config.prompts_dir.parent / "base_system.md"
        user_path = self.config.prompts_dir / "user_prompt.md"
        system_msg = base_path.read_text(encoding="utf-8") if base_path.exists() else ""
        user_template = user_path.read_text(encoding="utf-8") if user_path.exists() else ""
        return system_msg, user_template

    def build_inventory(self, cad_facts: dict[str, Any], vision_results: list[dict[str, Any]]) -> list[LevelInventory]:
        if not vision_results:
            fallback = str(cad_facts.get("project") or "level_01")
            return [build_level_inventory(cad_facts, None, level_id="level_01", level_name=fallback)]
        levels: list[LevelInventory] = []
        for i, payload in enumerate(vision_results, start=1):
            if isinstance(payload, dict) and "error" in payload:
                continue
            if isinstance(payload, LevelInventory):
                vision_level = payload
            else:
                d = dict(payload)
                d.setdefault("level_id", f"level_{i:02d}")
                d.setdefault("level_name", d["level_id"])
                vision_level = level_inventory_from_dict(d, default_source="vision")
            levels.append(build_level_inventory(cad_facts, vision_level, level_id=vision_level.level_id, level_name=vision_level.level_name))
        return levels

    def quantify(self, levels: list[LevelInventory]) -> list[QuantityTakeoff]:
        return quantify(levels)

    def get_rules_engine(self) -> RulesEngine:
        return default_rules_engine()

    def get_chapter_config(self) -> ChapterConfig:
        return build_chapter_config()


register_engine("sanitario", SanitarioEngine)
