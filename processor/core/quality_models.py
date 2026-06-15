"""
Quality models for semantic interpretation and quantification readiness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

QualityStatus = Literal["OK", "WARNING", "BLOCKED"]


@dataclass(kw_only=True)
class QualityIssue:
    status: QualityStatus
    code: str
    message: str
    discipline: str
    element_id: str | None = None
    level_id: str | None = None
    unit_id: str | None = None
    space_id: str | None = None
    confidence_score: float | None = None
    evidence_refs: list[str] = field(default_factory=list)
    raw_entity_ids: list[str] = field(default_factory=list)
    suggested_action: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(kw_only=True)
class QualityReport:
    discipline: str
    total_elements: int = 0
    ok_count: int = 0
    warning_count: int = 0
    blocked_count: int = 0
    issues: list[QualityIssue] = field(default_factory=list)

    @property
    def blocked_items(self) -> list[QualityIssue]:
        return [issue for issue in self.issues if issue.status == "BLOCKED"]

    @property
    def warnings(self) -> list[QualityIssue]:
        return [issue for issue in self.issues if issue.status == "WARNING"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "discipline": self.discipline,
            "summary": {
                "total_elements": self.total_elements,
                "ok_count": self.ok_count,
                "warning_count": self.warning_count,
                "blocked_count": self.blocked_count,
            },
            "issues": [issue.to_dict() for issue in self.issues],
            "blocked_items": [issue.to_dict() for issue in self.blocked_items],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }
