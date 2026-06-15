"""
Semantic spatial models used between hybrid inventory and quantification.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping

SemanticSource = Literal["aps", "vision", "manual", "inferred"]


@dataclass(kw_only=True)
class SemanticElement:
    element_id: str
    element_type: str
    discipline: str
    level_id: str | None = None
    unit_id: str | None = None
    space_id: str | None = None
    confidence_score: float = 0.0
    source: SemanticSource = "inferred"
    evidence_refs: list[str] = field(default_factory=list)
    raw_entity_ids: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(kw_only=True)
class SemanticSpace:
    space_id: str
    level_id: str
    unit_id: str | None = None
    name: str = "unknown"
    space_type: str = "unknown"
    confidence_score: float = 0.0
    source: SemanticSource = "inferred"
    evidence_refs: list[str] = field(default_factory=list)
    element_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(kw_only=True)
class SemanticUnit:
    unit_id: str
    level_id: str
    name: str = "unknown"
    confidence_score: float = 0.0
    source: SemanticSource = "inferred"
    evidence_refs: list[str] = field(default_factory=list)
    spaces: list[SemanticSpace] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "level_id": self.level_id,
            "name": self.name,
            "confidence_score": self.confidence_score,
            "source": self.source,
            "evidence_refs": list(self.evidence_refs),
            "spaces": [space.to_dict() for space in self.spaces],
        }


@dataclass(kw_only=True)
class SemanticLevel:
    level_id: str
    level_name: str
    confidence_score: float = 0.0
    source_refs: list[str] = field(default_factory=list)
    units: list[SemanticUnit] = field(default_factory=list)
    orphan_space_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_id": self.level_id,
            "level_name": self.level_name,
            "confidence_score": self.confidence_score,
            "source_refs": list(self.source_refs),
            "units": [unit.to_dict() for unit in self.units],
            "orphan_space_ids": list(self.orphan_space_ids),
        }


@dataclass(kw_only=True)
class SemanticBuilding:
    project_id: str | None = None
    project_name: str | None = None
    discipline: str = "arquitectura"
    confidence_score: float = 0.0
    levels: list[SemanticLevel] = field(default_factory=list)
    spaces: list[SemanticSpace] = field(default_factory=list)
    elements: list[SemanticElement] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "discipline": self.discipline,
            "confidence_score": self.confidence_score,
            "levels": [level.to_dict() for level in self.levels],
            "spaces": [space.to_dict() for space in self.spaces],
            "elements": [element.to_dict() for element in self.elements],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SemanticBuilding":
        spaces = [SemanticSpace(**dict(space)) for space in payload.get("spaces", [])]
        space_by_id = {space.space_id: space for space in spaces}

        levels: list[SemanticLevel] = []
        for level_payload in payload.get("levels", []):
            units: list[SemanticUnit] = []
            for unit_payload in level_payload.get("units", []):
                unit_spaces = [space_by_id[sid] for sid in unit_payload.get("space_ids", []) if sid in space_by_id]
                units.append(
                    SemanticUnit(
                        unit_id=str(unit_payload.get("unit_id", "unknown")),
                        level_id=str(level_payload.get("level_id", "unknown")),
                        name=str(unit_payload.get("name", "unknown")),
                        confidence_score=float(unit_payload.get("confidence_score", 0.0) or 0.0),
                        source=str(unit_payload.get("source", "inferred")),  # type: ignore[arg-type]
                        evidence_refs=list(unit_payload.get("evidence_refs", [])),
                        spaces=unit_spaces,
                    )
                )
            levels.append(
                SemanticLevel(
                    level_id=str(level_payload.get("level_id", "unknown")),
                    level_name=str(level_payload.get("level_name", "unknown")),
                    confidence_score=float(level_payload.get("confidence_score", 0.0) or 0.0),
                    source_refs=list(level_payload.get("source_refs", [])),
                    units=units,
                    orphan_space_ids=list(level_payload.get("orphan_space_ids", [])),
                )
            )

        elements = [SemanticElement(**dict(element)) for element in payload.get("elements", [])]
        return cls(
            project_id=payload.get("project_id"),
            project_name=payload.get("project_name"),
            discipline=str(payload.get("discipline", "arquitectura")),
            confidence_score=float(payload.get("confidence_score", 0.0) or 0.0),
            levels=levels,
            spaces=spaces,
            elements=elements,
            metadata=dict(payload.get("metadata", {})),
        )
