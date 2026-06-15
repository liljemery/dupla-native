"""
Centralized logging setup for the Dupla pipeline.

Usage in any module:
    import logging
    logger = logging.getLogger("dupla.module_name")

Call ``setup_logging()`` once at process start (e.g. in the runner script).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_CONFIGURED = False

LOG_FORMAT = (
    "%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s"
)
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

DEFAULT_CONSOLE_LEVEL = logging.INFO
DEFAULT_FILE_LEVEL = logging.DEBUG


def setup_logging(
    *,
    console_level: int = DEFAULT_CONSOLE_LEVEL,
    log_file: str | Path | None = None,
    file_level: int = DEFAULT_FILE_LEVEL,
) -> None:
    """Configure the ``dupla`` logger hierarchy once per process.

    Parameters
    ----------
    console_level:
        Minimum level for the console (stderr) handler.
    log_file:
        Optional path for a rotating-style log file.  When provided a
        ``FileHandler`` is attached so every DEBUG-level message is
        persisted for post-mortem analysis.
    file_level:
        Minimum level for the file handler (ignored when *log_file* is
        ``None``).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    root_logger = logging.getLogger("dupla")
    root_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(console_level)
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    if log_file is not None:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(path), encoding="utf-8")
        fh.setLevel(file_level)
        fh.setFormatter(formatter)
        root_logger.addHandler(fh)
