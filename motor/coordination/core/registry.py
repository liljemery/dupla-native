"""Registry models for project levels and coordination source rules."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from coordination.core.models_25d import Discipline, ProjectLevel

logger = logging.getLogger("dupla.coordination.registry")


class ViewLevelPattern(BaseModel):
    """Regex rule that maps page or view text to a canonical level id."""

    model_config = ConfigDict(extra="forbid")

    pattern: str
    level_id: str
    flags: str = "i"
    source: str | None = None


class SourceExcludePattern(BaseModel):
    """Regex rule used while scanning project sources."""

    model_config = ConfigDict(extra="forbid")

    pattern: str
    reason: str | None = None


class ProjectLevelRegistry(RootModel[dict[str, ProjectLevel]]):
    """Map level_id -> ProjectLevel."""

    @model_validator(mode="after")
    def _keys_match_ids(self) -> ProjectLevelRegistry:
        for key, lvl in self.root.items():
            if key != lvl.id:
                raise ValueError(f"Clave {key!r} debe coincidir con ProjectLevel.id {lvl.id!r}")
        return self

    def offset_mm(self, level_id: str, *, strict: bool = False) -> float:
        lvl = self.root.get(level_id)
        if lvl is None:
            msg = f"Nivel no registrado: {level_id!r}"
            if strict:
                raise KeyError(msg)
            logger.warning("%s - usando offset 0.0 (posible falso clash)", msg)
            return 0.0
        return lvl.offset_to_project_zero_mm

    def offsets_map(self) -> dict[str, float]:
        return {k: v.offset_to_project_zero_mm for k, v in self.root.items()}

    @classmethod
    def from_llm_rows(
        cls,
        rows: Iterable[dict[str, Any]],
        *,
        provisional: bool = True,
    ) -> ProjectLevelRegistry:
        out: dict[str, ProjectLevel] = {}
        for raw in rows:
            pid = str(raw["id"])
            disc: Discipline | None = None
            if raw.get("discipline_origin"):
                disc = Discipline(str(raw["discipline_origin"]))
            prov = bool(raw.get("provisional", provisional))
            out[pid] = ProjectLevel(
                id=pid,
                name=str(raw.get("name", pid)),
                offset_to_project_zero_mm=float(raw["offset_to_project_zero_mm"]),
                discipline_origin=disc,
                provisional=prov,
            )
        return cls(out)


class ProjectLevelRegistryDocument(BaseModel):
    """Optional wrapper used to serialize the registry plus run metadata."""

    model_config = ConfigDict(extra="allow")

    project_name: str | None = None
    levels: list[ProjectLevel]
    level_aliases: dict[str, str] = Field(
        default_factory=dict,
        description="alias_id -> canonical level id present in levels",
    )
    view_level_patterns: list[ViewLevelPattern] = Field(default_factory=list)
    source_exclude_patterns: list[SourceExcludePattern] = Field(default_factory=list)

    def to_registry(self) -> ProjectLevelRegistry:
        by_id = {lvl.id: lvl for lvl in self.levels}
        for alias, canonical in self.level_aliases.items():
            if alias in by_id:
                raise ValueError(f"Alias {alias!r} ya existe como id propio en levels")
            if canonical not in by_id:
                raise ValueError(f"Alias {alias!r} -> {canonical!r}: canonico inexistente")
            base = by_id[canonical]
            by_id[alias] = base.model_copy(update={"id": alias})
        return ProjectLevelRegistry(by_id)
