"""Headless APS Viewer screenshot renderer for clash review.

This is the visual counterpart to the fragment extractor:
- `extract_fragments.js` writes real APS fragment geometry.
- `capture.js` writes a real screenshot of the translated APS viewable.

The wrapper keeps the process model simple: one URN, one viewer load, one image.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).resolve().parents[4] / "viewer-engine"
CAPTURE_SCRIPT = ENGINE_DIR / "capture.js"


def engine_available() -> bool:
    if not CAPTURE_SCRIPT.is_file():
        logger.debug("viewer-engine capture.js missing: %s", CAPTURE_SCRIPT)
        return False
    if not shutil.which("node"):
        logger.debug("node not found in PATH")
        return False
    return True


def render_plan_screenshot(
    *,
    urn: str,
    aps_token: str,
    output_path: str | Path,
    sheet: str = "",
    view: str = "",
    viewable_guid: str = "",
    width: int = 3000,
    height: int = 2200,
    timeout_s: int = 180,
    clashes: list[dict[str, Any]] | None = None,
) -> str | None:
    if not engine_available():
        logger.warning("APS viewer engine unavailable; screenshot skipped")
        return None
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clashes_file = None
    if clashes:
        clashes_file = output_path.with_suffix(".clashes.json")
        clashes_file.write_text(__import__("json").dumps(clashes, ensure_ascii=False, indent=2), encoding="utf-8")
    cmd = [
        "node",
        str(CAPTURE_SCRIPT),
        "--urn",
        urn,
        "--token",
        aps_token,
        "--output",
        str(output_path),
        "--width",
        str(width),
        "--height",
        str(height),
        "--timeout",
        str(timeout_s * 1000),
    ]
    if clashes_file:
        cmd.extend(["--clashes-file", str(clashes_file)])
    if sheet:
        cmd.extend(["--sheet", sheet])
    if view:
        cmd.extend(["--view", view])
    if viewable_guid:
        cmd.extend(["--viewable-guid", viewable_guid])
    logger.info("Running APS viewer screenshot -> %s", output_path)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ENGINE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("APS viewer screenshot failed before completion: %s", exc)
        return None
    if result.stdout:
        for line in result.stdout.splitlines():
            if line.strip():
                logger.info("viewer-engine: %s", line)
    if result.stderr:
        for line in result.stderr.splitlines():
            if line.strip():
                logger.warning("viewer-engine: %s", line)
    if result.returncode != 0:
        logger.warning("APS viewer screenshot exited with code %s", result.returncode)
        return None
    return str(output_path)
