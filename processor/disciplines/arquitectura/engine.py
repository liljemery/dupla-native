"""
Architectural discipline engine.

Wraps the existing pipeline logic (vision, inventory builder, quantifier)
into the ``DisciplineEngine`` protocol for the multi-discipline architecture.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core.inventory_builder import build_level_inventory
from core.schemas import LevelInventory, QuantityTakeoff, level_inventory_from_dict
from disciplines.base import ChapterConfig, DisciplineConfig, DisciplineEngine
from disciplines.registry import register_engine
from rules_engine import RulesEngine, default_rules_engine

from .chapters import build_chapter_config
from .quantifier import quantify

logger = logging.getLogger("dupla.disciplines.arquitectura")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PROMPTS_DIR = _REPO_ROOT / "knowledge" / "prompts" / "arquitectura"
_RULES_PATH = Path(__file__).resolve().parent / "rules.json"


class ArquitecturaEngine:
    """Architectural discipline engine implementing DisciplineEngine protocol."""

    def __init__(self) -> None:
        self.config = DisciplineConfig(
            discipline_id="arquitectura",
            display_name="Arquitectura",
            prompts_dir=_PROMPTS_DIR,
            rules_path=_RULES_PATH if _RULES_PATH.exists() else None,
            chapter_config=build_chapter_config(),
            item_types={
                "wall_length", "wall_gross_area", "wall_net_area", "wall_volume",
                "wall_finish_paint", "wall_finish_plaster", "wall_waterproofing",
                "floor_area", "floor_finish", "floor_waterproofing", "floor_screed",
                "ceiling_area", "ceiling_finish_paint", "ceiling_finish_plaster",
                "door_count", "door_leaf_wood_count", "door_frame_count",
                "door_hardware_set_count",
                "window_count", "window_area",
                "wet_area_count", "wet_area_area", "wet_area_fixture_count",
                "kitchen_count", "kitchen_area",
                "stair_count", "fixture_count",
                "pres_reference_line",
            },
            bc3_chapter_filter={"03", "04", "05", "06", "07", "08", "09"},
        )

    def build_vision_prompt(
        self,
        cad_summary: dict[str, Any],
        methodology: str,
    ) -> tuple[str, str]:
        """Load prompts from disk and return (system_message, user_template)."""
        base_system_path = self.config.prompts_dir.parent / "base_system.md"
        user_prompt_path = self.config.prompts_dir / "user_prompt.md"

        system_msg = ""
        if base_system_path.exists():
            system_msg = base_system_path.read_text(encoding="utf-8")
        else:
            from agents.vision_agent import _SIMPLE_SYSTEM_PROMPT
            system_msg = _SIMPLE_SYSTEM_PROMPT

        user_template = ""
        if user_prompt_path.exists():
            user_template = user_prompt_path.read_text(encoding="utf-8")

        return system_msg, user_template

    def build_inventory(
        self,
        cad_facts: dict[str, Any],
        vision_results: list[dict[str, Any]],
    ) -> list[LevelInventory]:
        """Merge CAD + vision results into hybrid inventory levels."""
        if not vision_results:
            fallback_name = str(cad_facts.get("project") or "level_01")
            return [
                build_level_inventory(
                    cad_facts, None,
                    level_id="level_01",
                    level_name=fallback_name,
                )
            ]

        levels: list[LevelInventory] = []
        for i, payload in enumerate(vision_results, start=1):
            if isinstance(payload, dict) and "error" in payload:
                logger.warning("Vision payload %d has error, skipping: %s", i, payload.get("error"))
                continue

            if isinstance(payload, LevelInventory):
                vision_level = payload
            else:
                d = dict(payload)
                d.setdefault("level_id", f"level_{i:02d}")
                d.setdefault("level_name", d["level_id"])
                vision_level = level_inventory_from_dict(d, default_source="vision")

            levels.append(
                build_level_inventory(
                    cad_facts,
                    vision_level,
                    level_id=vision_level.level_id,
                    level_name=vision_level.level_name,
                )
            )

        return levels

    def quantify(self, levels: list[LevelInventory]) -> list[QuantityTakeoff]:
        return quantify(levels)

    def get_rules_engine(self) -> RulesEngine:
        if self.config.rules_path and self.config.rules_path.exists():
            return default_rules_engine(self.config.rules_path)
        return default_rules_engine()

    def get_chapter_config(self) -> ChapterConfig:
        return build_chapter_config()


register_engine("arquitectura", ArquitecturaEngine)
