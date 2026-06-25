"""Import motor local CAD pipeline from processor (Docker: /motor on PYTHONPATH)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_MOTOR_CANDIDATES = (
    Path(os.getenv("DUPLA_ROOT", "/motor")),
    Path(__file__).resolve().parents[1] / "motor",
)
for _candidate in _MOTOR_CANDIDATES:
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))
        break

from coordination.extraction.local_cad_pipeline import (  # noqa: E402
    LOCAL_EXTRACTOR,
    extract_cad_facts,
)
from coordination.extraction.libredwg_convert import display_name_from_storage  # noqa: E402

__all__ = ["LOCAL_EXTRACTOR", "extract_cad_facts", "display_name_from_storage"]
