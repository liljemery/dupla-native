"""
Stage-based pipeline execution with timing, error capture, and reporting.

Each pipeline step is wrapped in a ``StageResult`` that records duration,
status, warnings, errors, and arbitrary metrics so that debugging a failed
or slow run becomes straightforward.
"""

from __future__ import annotations

import json
import logging
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal

logger = logging.getLogger("dupla.stage")

StageStatus = Literal["success", "warning", "error", "skipped"]


@dataclass
class StageResult:
    """Immutable record of a single pipeline stage execution."""

    stage_name: str
    status: StageStatus
    started_at: str
    finished_at: str
    duration_seconds: float
    output: Any = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in ("success", "warning")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("output", None)
        return data


@dataclass
class PipelineReport:
    """Aggregated report for a full pipeline run."""

    started_at: str
    finished_at: str
    total_duration_seconds: float
    stages: list[dict[str, Any]]
    final_status: StageStatus
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return out


class PipelineRunner:
    """Orchestrates pipeline stages with automatic timing and error capture.

    Usage::

        runner = PipelineRunner("my_pipeline")
        s1 = runner.run_stage("aps_extraction", do_aps, dwg_path, bucket)
        if not s1.ok:
            return runner.report()
        s2 = runner.run_stage("vision", do_vision, s1.output)
        ...
        report = runner.report()
        report.save("outputs/pipeline_report.json")
    """

    def __init__(self, name: str = "dupla_pipeline") -> None:
        self.name = name
        self.stages: list[StageResult] = []
        self._started_at = datetime.now()

    def run_stage(
        self,
        name: str,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> StageResult:
        """Execute *fn* as a named stage, capturing timing and errors."""
        logger.info("Stage [%s] started", name)
        start = datetime.now()

        try:
            output = fn(*args, **kwargs)
            finished = datetime.now()
            duration = (finished - start).total_seconds()

            warnings: list[str] = []
            if isinstance(output, tuple) and len(output) == 2 and isinstance(output[1], list):
                output, warnings = output

            status: StageStatus = "warning" if warnings else "success"
            result = StageResult(
                stage_name=name,
                status=status,
                started_at=start.isoformat(),
                finished_at=finished.isoformat(),
                duration_seconds=round(duration, 3),
                output=output,
                warnings=warnings,
            )
            logger.info(
                "Stage [%s] completed (%s) in %.2fs",
                name, status, duration,
            )

        except Exception as exc:
            finished = datetime.now()
            duration = (finished - start).total_seconds()
            tb = traceback.format_exc()
            result = StageResult(
                stage_name=name,
                status="error",
                started_at=start.isoformat(),
                finished_at=finished.isoformat(),
                duration_seconds=round(duration, 3),
                errors=[str(exc), tb],
            )
            logger.error(
                "Stage [%s] FAILED after %.2fs: %s",
                name, duration, exc,
            )
            logger.debug("Traceback:\n%s", tb)

        self.stages.append(result)
        return result

    def skip_stage(self, name: str, reason: str = "") -> StageResult:
        """Record a stage as intentionally skipped."""
        now = datetime.now().isoformat()
        result = StageResult(
            stage_name=name,
            status="skipped",
            started_at=now,
            finished_at=now,
            duration_seconds=0.0,
            warnings=[reason] if reason else [],
        )
        logger.info("Stage [%s] skipped%s", name, f": {reason}" if reason else "")
        self.stages.append(result)
        return result

    def add_metrics(self, stage_name: str, metrics: dict[str, Any]) -> None:
        """Attach metrics to the most recent stage with *stage_name*."""
        for stage in reversed(self.stages):
            if stage.stage_name == stage_name:
                stage.metrics.update(metrics)
                return

    def report(self, summary: dict[str, Any] | None = None) -> PipelineReport:
        """Build the final pipeline report."""
        finished = datetime.now()
        total = (finished - self._started_at).total_seconds()

        has_error = any(s.status == "error" for s in self.stages)
        has_warning = any(s.status == "warning" for s in self.stages)
        if has_error:
            final_status: StageStatus = "error"
        elif has_warning:
            final_status = "warning"
        else:
            final_status = "success"

        return PipelineReport(
            started_at=self._started_at.isoformat(),
            finished_at=finished.isoformat(),
            total_duration_seconds=round(total, 3),
            stages=[s.to_dict() for s in self.stages],
            final_status=final_status,
            summary=summary or {},
        )

    def last_ok_output(self, stage_name: str) -> Any | None:
        """Retrieve the output of the last successful run of *stage_name*."""
        for stage in reversed(self.stages):
            if stage.stage_name == stage_name and stage.ok:
                return stage.output
        return None
