"""
Per-discipline pipeline metrics tracking.

Collects timing, counts, and quality indicators for each discipline
run so they can be included in the pipeline report.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DisciplineMetrics:
    discipline_id: str
    display_name: str = ""
    status: str = "pending"

    # Timing
    start_time: float = 0.0
    end_time: float = 0.0

    # Counts
    vision_pages: int = 0
    vision_errors: int = 0
    inventory_levels: int = 0
    base_takeoffs: int = 0
    expanded_takeoffs: int = 0
    budget_lines: int = 0
    budget_chapters: int = 0
    matched_candidates: int = 0
    unmatched_takeoffs: int = 0

    # Quality
    avg_candidate_score: float = 0.0
    total_amount: float = 0.0

    # Warnings
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.status = "running"
        self.start_time = time.time()

    def finish(self, status: str = "success") -> None:
        self.status = status
        self.end_time = time.time()

    @property
    def duration_s(self) -> float:
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "discipline_id": self.discipline_id,
            "display_name": self.display_name,
            "status": self.status,
            "duration_s": round(self.duration_s, 2),
            "vision_pages": self.vision_pages,
            "vision_errors": self.vision_errors,
            "inventory_levels": self.inventory_levels,
            "base_takeoffs": self.base_takeoffs,
            "expanded_takeoffs": self.expanded_takeoffs,
            "budget_lines": self.budget_lines,
            "budget_chapters": self.budget_chapters,
            "matched_candidates": self.matched_candidates,
            "unmatched_takeoffs": self.unmatched_takeoffs,
            "avg_candidate_score": round(self.avg_candidate_score, 4),
            "total_amount": round(self.total_amount, 2),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@dataclass
class PipelineMetrics:
    """Aggregates metrics across all disciplines in a pipeline run."""

    project_name: str = ""
    disciplines: dict[str, DisciplineMetrics] = field(default_factory=dict)
    total_start: float = 0.0
    total_end: float = 0.0

    def get_or_create(self, discipline_id: str, display_name: str = "") -> DisciplineMetrics:
        if discipline_id not in self.disciplines:
            self.disciplines[discipline_id] = DisciplineMetrics(
                discipline_id=discipline_id,
                display_name=display_name or discipline_id,
            )
        return self.disciplines[discipline_id]

    def start(self) -> None:
        self.total_start = time.time()

    def finish(self) -> None:
        self.total_end = time.time()

    @property
    def total_duration_s(self) -> float:
        if self.total_end and self.total_start:
            return self.total_end - self.total_start
        return 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "total_duration_s": round(self.total_duration_s, 2),
            "disciplines_count": len(self.disciplines),
            "disciplines_succeeded": sum(
                1 for m in self.disciplines.values() if m.status == "success"
            ),
            "disciplines_failed": sum(
                1 for m in self.disciplines.values() if m.status == "error"
            ),
            "total_budget_lines": sum(m.budget_lines for m in self.disciplines.values()),
            "total_amount": sum(m.total_amount for m in self.disciplines.values()),
            "per_discipline": {
                disc_id: metrics.to_dict()
                for disc_id, metrics in sorted(self.disciplines.items())
            },
        }
