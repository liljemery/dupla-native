"""Formatting helpers for clash PDF reports."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

# Severity thresholds (rule-based, transparent in technical report).
SEVERITY_HIGH_Z_MM = 150.0
SEVERITY_HIGH_AREA_M2 = 0.20
SEVERITY_MEDIUM_Z_MM = 50.0
SEVERITY_MEDIUM_AREA_M2 = 0.05

ZOOM_BOUNDS_MARGIN_FACTOR = 0.25
ZOOM_BOUNDS_MIN_MARGIN_MM = 5000.0
ZOOM_CENTER_RADIUS_MM = 5000.0

_BUCKET_TO_DISCIPLINE = {
    "arquitectura": "ARQUITECTURA",
    "estructura": "ESTRUCTURA",
    "electrica": "ELECTRICA",
    "mecanica": "MECANICA",
    "plomeria": "PLOMERIA",
}

_NA = "no disponible"

_DISCIPLINE_PREFIX: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"ARQ|ARQUIT", re.I), "ARQ"),
    (re.compile(r"EST|ESTRUC", re.I), "EST"),
    (re.compile(r"ELEC|EL[EÉ]CT", re.I), "ELC"),
    (re.compile(r"MEC|CLIMA|HVAC", re.I), "MEC"),
    (re.compile(r"PLO|SAN|HIDRO|FONT", re.I), "PLO"),
)

_MONTH_MAP = {
    "ENE": "ENE",
    "FEB": "FEB",
    "MAR": "MAR",
    "ABR": "ABR",
    "MAY": "MAY",
    "JUN": "JUN",
    "JUL": "JUL",
    "AGO": "AGO",
    "SEP": "SEP",
    "OCT": "OCT",
    "NOV": "NOV",
    "DIC": "DIC",
}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return True
    if isinstance(value, str):
        v = value.strip()
        return not v or v in {"?", "-", "—", "unknown", "null", "None"}
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return True
    return False


def format_optional(value: Any, suffix: str = "") -> str:
    if _is_missing(value):
        return _NA
    if isinstance(value, float):
        if value == int(value):
            text = str(int(value))
        else:
            text = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        text = str(value).strip()
    return f"{text}{suffix}" if suffix else text


def format_area_m2(area_mm2: Any) -> str:
    if _is_missing(area_mm2):
        return _NA
    try:
        m2 = float(area_mm2) / 1_000_000.0
    except (TypeError, ValueError):
        return _NA
    return f"{m2:.2f} m2"


def format_mm(value: Any) -> str:
    if _is_missing(value):
        return _NA
    try:
        num = float(value)
    except (TypeError, ValueError):
        return _NA
    return f"{int(round(num)):,} mm".replace(",", ".")


def format_point(x: Any, y: Any) -> str:
    if _is_missing(x) or _is_missing(y):
        return _NA
    try:
        xf = float(x)
        yf = float(y)
    except (TypeError, ValueError):
        return _NA
    if xf == 0.0 and yf == 0.0:
        return _NA
    return f"X: {int(round(xf)):,} mm; Y: {int(round(yf)):,} mm".replace(",", ".")


def format_bounds(bounds: Any) -> str:
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        return _NA
    try:
        x1, y1, x2, y2 = (float(v) for v in bounds)
    except (TypeError, ValueError):
        return _NA
    if x1 == x2 == y1 == y2 == 0.0:
        return _NA
    return (
        f"x_min={int(round(x1)):,}; y_min={int(round(y1)):,}; "
        f"x_max={int(round(x2)):,}; y_max={int(round(y2)):,} mm"
    ).replace(",", ".")


def compute_severity(*, area_mm2: Any, z_depth_mm: Any) -> str:
    area_m2 = 0.0
    z_depth = 0.0
    try:
        area_m2 = float(area_mm2 or 0) / 1_000_000.0
    except (TypeError, ValueError):
        pass
    try:
        z_depth = float(z_depth_mm or 0)
    except (TypeError, ValueError):
        pass
    if z_depth >= SEVERITY_HIGH_Z_MM or area_m2 >= SEVERITY_HIGH_AREA_M2:
        return "Alta"
    if z_depth >= SEVERITY_MEDIUM_Z_MM or area_m2 >= SEVERITY_MEDIUM_AREA_M2:
        return "Media"
    return "Baja"


def confidence_es(value: Any) -> str:
    mapping = {"high": "Alta", "medium": "Media", "low": "Baja"}
    if _is_missing(value):
        return _NA
    key = str(value).strip().lower()
    return mapping.get(key, str(value).capitalize())


def make_zoom_command(
    bounds: Any = None,
    *,
    center: Any = None,
    padding_mm: float | None = None,
    center_radius_mm: float = ZOOM_CENTER_RADIUS_MM,
) -> tuple[str | None, str | None]:
    """Return (command, fallback_text). Matches Dupla revision_report margin rules."""
    if isinstance(bounds, (list, tuple)) and len(bounds) == 4:
        try:
            x1, y1, x2, y2 = (float(v) for v in bounds)
        except (TypeError, ValueError):
            x1 = y1 = x2 = y2 = 0.0
        if not (x1 == y1 == x2 == y2 == 0.0):
            w = max(x2 - x1, 1)
            h = max(y2 - y1, 1)
            if padding_mm is not None:
                mx = my = float(padding_mm)
            else:
                mx = max(w * ZOOM_BOUNDS_MARGIN_FACTOR, ZOOM_BOUNDS_MIN_MARGIN_MM)
                my = max(h * ZOOM_BOUNDS_MARGIN_FACTOR, ZOOM_BOUNDS_MIN_MARGIN_MM)
            return (
                f"Z W {int(round(x1 - mx))},{int(round(y1 - my))} "
                f"{int(round(x2 + mx))},{int(round(y2 + my))}",
                None,
            )

    if isinstance(center, (list, tuple)) and len(center) >= 2:
        try:
            cx, cy = float(center[0]), float(center[1])
        except (TypeError, ValueError):
            cx = cy = 0.0
        if not (cx == 0.0 and cy == 0.0):
            r = float(center_radius_mm)
            return (
                f"Z W {int(round(cx - r))},{int(round(cy - r))} "
                f"{int(round(cx + r))},{int(round(cy + r))}",
                None,
            )

    return (
        None,
        "Limites de zoom no disponibles; use Z E e inspeccione manualmente el nivel y las capas indicadas.",
    )


def basename(path: Any) -> str:
    if _is_missing(path):
        return _NA
    return Path(str(path)).name


def layers_from_incident(incident: dict[str, Any]) -> tuple[str | None, str | None]:
    rep = incident.get("representative_conflict") or {}
    refs = rep.get("source_refs") or []
    layers: list[str | None] = []
    for ref in refs[:2]:
        if not isinstance(ref, str):
            layers.append(None)
            continue
        parts = ref.split("|")
        layer = parts[1].strip() if len(parts) > 1 else None
        layers.append(layer if layer and layer != "?" else None)
    while len(layers) < 2:
        layers.append(None)
    return layers[0], layers[1]


def handles_from_incident(incident: dict[str, Any]) -> tuple[str | None, str | None]:
    rep = incident.get("representative_conflict") or {}
    refs = rep.get("source_refs") or []
    handles: list[str | None] = []
    for ref in refs[:2]:
        if not isinstance(ref, str):
            handles.append(None)
            continue
        parts = ref.split("|")
        handle = parts[-1].strip() if parts else None
        handles.append(handle if handle else None)
    while len(handles) < 2:
        handles.append(None)
    return handles[0], handles[1]


def _resolve_discipline_label(discipline: str | None) -> str:
    if _is_missing(discipline):
        return _NA
    key = str(discipline).strip().lower()
    if key in _BUCKET_TO_DISCIPLINE:
        return _BUCKET_TO_DISCIPLINE[key]
    return str(discipline).strip().upper() if len(str(discipline).strip()) > 3 else str(discipline).strip()


def format_alias_for_pdf(alias: str) -> str:
    """Keep alias tokens intact in ReportLab Paragraph cells."""
    safe = alias.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<font face="Courier" size="6">{safe}</font>'


def format_alias_pair_for_pdf(alias_a: str, alias_b: str) -> str:
    """Render file pair aliases on two lines to avoid horizontal overflow."""
    a = format_alias_for_pdf(alias_a.strip())
    b = format_alias_for_pdf(alias_b.strip())
    return f"{a}<br/>{b}"


def _discipline_prefix(filename: str, discipline: str | None) -> str:
    text = f"{filename} {discipline or ''}"
    for pattern, prefix in _DISCIPLINE_PREFIX:
        if pattern.search(text):
            return prefix
    return "DWG"


def _date_token(filename: str) -> str:
    name = filename.upper()
    m = re.search(r"(20\d{6})", name)
    if m:
        return m.group(1)
    m = re.search(r"20(\d{2})[-_/ ]?(\d{2})[-_/ ]?(\d{2})", name)
    if m:
        return f"20{m.group(1)}{m.group(2)}{m.group(3)}"
    m = re.search(r"\b(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)[^\d]{0,6}(20\d{2})", name)
    if m:
        return f"{_MONTH_MAP.get(m.group(1), m.group(1))}{m.group(2)}"
    stem = Path(filename).stem
    token = re.sub(r"[^A-Z0-9]", "", stem.upper())[-8:]
    return token or "FILE"


class FilenameAliasRegistry:
    """Maps long DWG names to short stable aliases."""

    def __init__(self) -> None:
        self._alias_by_full: dict[str, str] = {}
        self._entries: list[dict[str, str]] = []

    def alias_for(
        self,
        filename: str,
        *,
        discipline: str | None = None,
        level: str | None = None,
    ) -> str:
        full = basename(filename)
        if full in self._alias_by_full:
            return self._alias_by_full[full]
        prefix = _discipline_prefix(full, discipline)
        token = _date_token(full)
        base = f"{prefix}_{token}"
        candidate = base
        n = 2
        used = set(self._alias_by_full.values())
        while candidate in used:
            candidate = f"{base}_{n}"
            n += 1
        self._alias_by_full[full] = candidate
        self._entries.append(
            {
                "alias": candidate,
                "full_name": full,
                "discipline": _resolve_discipline_label(discipline),
                "level": format_optional(level) if level else _NA,
            }
        )
        return candidate

    @property
    def legend(self) -> list[dict[str, str]]:
        return list(self._entries)


def wrap_filename_alias(
    filename: str,
    registry: FilenameAliasRegistry,
    *,
    discipline: str | None = None,
    level: str | None = None,
) -> str:
    return registry.alias_for(filename, discipline=discipline, level=level)


def what_to_check_text(layer_a: str | None, layer_b: str | None) -> str:
    la = format_optional(layer_a) if layer_a else _NA
    lb = format_optional(layer_b) if layer_b else _NA
    if la == _NA and lb == _NA:
        return (
            "Active solo las capas indicadas en el par. Verifique si las geometrias se solapan "
            "y si corresponden a elementos constructivos (muros, losas, vigas) o anotacion."
        )
    return (
        f"Active solo las capas {la} y {lb}. Verifique si los elementos de ambos planos se solapan "
        f"en el area indicada y si la geometria es constructiva o anotacion (marcos, cotas, simbolos)."
    )
