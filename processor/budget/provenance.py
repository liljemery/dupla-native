"""Deterministic provenance suffixes for budget line summaries."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.schemas import QuantityTakeoff

_UUID_PREFIX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_",
    re.I,
)
_CAD_INTERNAL = re.compile(r"^(json|vis)-", re.I)


def display_source_file(name: str | None) -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    return _UUID_PREFIX.sub("", Path(text).name)


def _level_label(takeoff: QuantityTakeoff) -> str:
    level_name = str(takeoff.inputs.get("level_name") or "").strip()
    if level_name:
        return level_name
    level_id = str(takeoff.level_id or "").strip()
    if not level_id:
        return ""
    if level_id.lower().startswith("level_"):
        num = level_id.split("_", 1)[-1]
        if num.isdigit():
            return f"N{int(num)}"
    return level_id


def _layer_label(takeoff: QuantityTakeoff) -> str:
    layer = str(takeoff.inputs.get("source_layer") or takeoff.trace.metadata.get("source_layer") or "").strip()
    if layer and not _CAD_INTERNAL.match(layer):
        return layer
    for ref in takeoff.source_refs:
        if ref.startswith("geometry:"):
            token = ref.split(":", 1)[1]
            if token and not re.fullmatch(r"[0-9A-Fa-f]+", token):
                return token
    return ""


def source_file_from_takeoff(takeoff: QuantityTakeoff) -> str:
    direct = display_source_file(str(takeoff.inputs.get("source_file") or ""))
    if direct:
        return direct
    for ref in takeoff.source_refs:
        if ref.startswith("file:"):
            return display_source_file(ref.split(":", 1)[1])
        if ref.startswith("vision:"):
            return display_source_file(ref.split(":", 1)[1])
    return ""


def format_provenance_suffix(takeoff: QuantityTakeoff, *, max_len: int = 48) -> str:
    parts: list[str] = []
    level = _level_label(takeoff)
    if level:
        parts.append(level)
    source = source_file_from_takeoff(takeoff)
    if source:
        parts.append(source)
    item_type = takeoff.item_type.lower()
    if item_type.startswith(("beam_", "column_", "slab_", "structural_", "footing_")):
        layer = _layer_label(takeoff)
        if layer and layer not in parts:
            parts.insert(0, layer)
    suffix = " · ".join(parts)
    if len(suffix) > max_len:
        return suffix[: max_len - 3] + "..."
    return suffix


def summary_has_provenance(summary: str, takeoff: QuantityTakeoff) -> bool:
    text = summary.lower()
    source = source_file_from_takeoff(takeoff).lower()
    if source and source in text:
        return True
    level = _level_label(takeoff).lower()
    return bool(level and level in text)


def append_provenance(summary: str, takeoff: QuantityTakeoff, *, max_total: int = 120) -> str:
    base = str(summary or "").strip()
    if not base:
        base = str(takeoff.inputs.get("takeoff_description") or takeoff.item_type.replace("_", " ")).strip()
    if summary_has_provenance(base, takeoff):
        return base[:max_total]
    suffix = format_provenance_suffix(takeoff)
    if not suffix:
        return base[:max_total]
    combined = f"{base} · {suffix}"
    if len(combined) <= max_total:
        return combined
    room = max_total - len(suffix) - 3
    if room > 20:
        return f"{base[:room].rstrip()} · {suffix}"
    return combined[:max_total]


def provenance_payload(takeoff: QuantityTakeoff) -> dict[str, Any]:
    return {
        "source_file": source_file_from_takeoff(takeoff),
        "provenance_suffix": format_provenance_suffix(takeoff),
        "level_name": _level_label(takeoff),
        "source_layer": _layer_label(takeoff),
    }


def enrich_takeoff_description(base: str, *, level_name: str = "", source_file: str = "", ubicacion: str = "") -> str:
    parts = [p for p in [base.strip(), ubicacion.strip(), level_name.strip(), display_source_file(source_file)] if p]
    return " · ".join(dict.fromkeys(parts))
