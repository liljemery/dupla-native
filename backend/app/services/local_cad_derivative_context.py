"""FOSS CAD layer summary for GA-FO classification (replaces APS derivative context)."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _motor_root() -> Path | None:
    for candidate in (
        Path("/motor"),
        Path(__file__).resolve().parents[2] / "motor",
    ):
        if candidate.is_dir():
            return candidate
    return None


def build_local_cad_context(file_path: Path, *, max_chars: int = 4000) -> str:
    """Return JSON text summarizing DXF/DWG layers for GA-FO prompts."""
    motor = _motor_root()
    if motor is None:
        return "unavailable"
    motor_text = str(motor)
    if motor_text not in sys.path:
        sys.path.insert(0, motor_text)

    suffix = file_path.suffix.lower()
    if suffix not in {".dwg", ".dxf"}:
        return "unavailable"

    try:
        from coordination.extraction.local_cad_pipeline import extract_cad_facts
    except Exception as exc:
        logger.warning("local_cad_pipeline import failed: %s", exc)
        return "unavailable"

    try:
        payload = extract_cad_facts(file_path)
    except Exception as exc:
        logger.warning("local CAD context failed for %s: %s", file_path.name, exc)
        return "unavailable"

    layers = payload.get("cad_facts", {}).get("layers", {})
    layer_rows = [
        {
            "layer": name,
            "object_count": metrics.get("object_count", 0),
            "dominant_entity_type": metrics.get("dominant_entity_type"),
        }
        for name, metrics in sorted(layers.items(), key=lambda item: -int(item[1].get("object_count") or 0))[:40]
    ]
    summary: dict[str, Any] = {
        "extractor": payload.get("extractor", "local_ezdxf"),
        "total_objects": payload.get("total_objects", 0),
        "layer_count": len(layers),
        "layers_sample": layer_rows,
        "inventory_hints": {
            "layer_names": (payload.get("inventory_hints") or {}).get("layer_names", [])[:30],
        },
    }
    text = json.dumps(summary, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."
