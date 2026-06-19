import logging
from pathlib import Path
from typing import Any

from runtime_paths import coordination_output_root
from wrapper.run_clash_analysis import run_clash_analysis

logger = logging.getLogger(__name__)


def run_clash_job(
    file_entries: list[dict[str, Any]],
    profile_slug: str,
    project_name: str,
    correlation_id: str,
    control_points: list[dict[str, Any]] | None = None,
    reanalysis_clash_code: str | None = None,
) -> dict[str, Any]:
    output_root = coordination_output_root()
    job_dir = output_root / correlation_id
    logger.info(
        "Starting clash job %s profile=%s files=%d control_points=%d",
        correlation_id,
        profile_slug,
        len(file_entries),
        len(control_points or []),
    )

    result = run_clash_analysis(
        file_entries=file_entries,
        profile_slug=profile_slug,
        project_name=project_name,
        output_dir=job_dir,
        control_points=control_points or [],
        reanalysis_clash_code=reanalysis_clash_code,
    )
    return result
