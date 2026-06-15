"""Normalize clash incident data from all upstream sources for PDF reports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.clash_reports.formatting import (
    basename,
    compute_severity,
    confidence_es,
    format_area_m2,
    format_bounds,
    format_optional,
    format_point,
    handles_from_incident,
    layers_from_incident,
    what_to_check_text,
)

_NA = "no disponible"

_BUCKET_TO_DISCIPLINE = {
    "arquitectura": "ARQUITECTURA",
    "estructura": "ESTRUCTURA",
    "electrica": "ELECTRICA",
    "mecanica": "MECANICA",
    "plomeria": "Plomería",
    "fontaneria": "Plomería",
}


@dataclass
class FieldProvenance:
    layers_source: str = "unavailable"
    center_source: str = "unavailable"
    bounds_source: str = "unavailable"
    zoom_source: str = "unavailable"
    discipline_source: str = "unavailable"
    level_source: str = "unavailable"


@dataclass
class NormalizedIncident:
    incident_id: str
    human_code: str
    group_code: str
    layer_a: str | None
    layer_b: str | None
    file_a_full: str
    file_b_full: str
    discipline_a: str
    discipline_b: str
    level_id: str
    severity: str
    confidence: str
    area_mm2: float
    area_m2_text: str
    z_depth_mm: float | None
    z_depth_text: str
    center: tuple[float, float] | None
    center_text: str
    bounds: tuple[float, float, float, float] | None
    bounds_text: str
    zoom_command: str | None
    zoom_fallback: str | None
    member_count: int
    clash_type: str
    handle_a: str | None
    handle_b: str | None
    what_to_check: str
    provenance: FieldProvenance = field(default_factory=FieldProvenance)
    warnings: list[str] = field(default_factory=list)


def _is_valid_bounds(raw: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        vals = tuple(float(v) for v in raw)
    except (TypeError, ValueError):
        return None
    if vals == (0.0, 0.0, 0.0, 0.0):
        return None
    return vals


def _is_valid_center(raw: Any) -> tuple[float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        x, y = float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return None
    return (x, y)


def _parse_layer_pair_text(text: str) -> tuple[str | None, str | None]:
    if not text or text.strip() in {_NA, "?", "-", ""}:
        return None, None
    parts = re.split(r"\s*/\s*", text.strip())
    if len(parts) >= 2:
        return parts[0].strip() or None, parts[1].strip() or None
    return text.strip() or None, None


def _parse_number_token(raw: str) -> float:
    s = raw.strip().replace(" ", "")
    if not s:
        raise ValueError("empty")
    if s.count(",") >= 2 or ("," in s and "." not in s and len(s.split(",")[-1]) == 3):
        s = s.replace(",", "")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    return float(s)


def _parse_center_text(text: str) -> tuple[float, float] | None:
    if not text:
        return None
    mx = re.search(r"X:\s*([-\d.,]+)", text, re.I)
    my = re.search(r"Y:\s*([-\d.,]+)", text, re.I)
    if mx and my:
        try:
            return (_parse_number_token(mx.group(1)), _parse_number_token(my.group(1)))
        except ValueError:
            pass
    m = re.search(r"\(([\d,.\-]+),\s*([\d,.\-]+)\)", text)
    if m:
        try:
            return (_parse_number_token(m.group(1)), _parse_number_token(m.group(2)))
        except ValueError:
            pass
    return None


def _parse_bounds_short(text: str) -> tuple[float, float, float, float] | None:
    if not text:
        return None
    parts = re.split(r",\s+", text.strip())
    if len(parts) >= 4:
        try:
            return tuple(_parse_number_token(p) for p in parts[:4])  # type: ignore[return-value]
        except ValueError:
            return None
    return None


def _zoom_from_bounds(bounds: tuple[float, float, float, float]) -> str:
    x1, y1, x2, y2 = bounds
    w = max(x2 - x1, 1)
    h = max(y2 - y1, 1)
    mx = max(w * 0.25, 5000)
    my = max(h * 0.25, 5000)
    return f"Z W {round(x1 - mx)},{round(y1 - my)} {round(x2 + mx)},{round(y2 + my)}"


def _zoom_from_center(center: tuple[float, float], radius: float = 5000) -> str:
    cx, cy = center
    r = float(radius)
    return f"Z W {round(cx - r)},{round(cy - r)} {round(cx + r)},{round(cy + r)}"


def merge_enriched_cards(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key in ("all_incidents", "defendable_incidents", "validation_incidents"):
        for card in context.get(key) or []:
            if isinstance(card, dict) and card.get("incident_id"):
                out[str(card["incident_id"])] = card
    return out


def parse_revision_md_incidents(revision_md: str) -> dict[str, dict[str, Any]]:
    """Extract per-incident fields from REVISION_CLASHES markdown cards."""
    if not revision_md:
        return {}
    out: dict[str, dict[str, Any]] = {}
    chunks = re.split(r"\n###\s+", revision_md)
    for chunk in chunks[1:]:
        header = chunk.split("\n", 1)[0]
        m_id = re.search(r"`(incident_[^`]+)`", header)
        if not m_id:
            continue
        inc_id = m_id.group(1)
        layer_m = re.search(
            r"\*\*Capas\*\*\s*\|\s*`([^`]+)`[^|]*vs\s*`([^`]+)`",
            chunk,
            re.I,
        )
        center_m = re.search(
            r"\*\*Centro del clash\*\*\s*\|\s*X:\s*([^\n|]+)",
            chunk,
            re.I,
        )
        zoom_m = re.search(r"```\s*\n(Z W[^\n`]+)", chunk)
        parsed: dict[str, Any] = {}
        if layer_m:
            parsed["layer_a"] = layer_m.group(1).strip()
            parsed["layer_b"] = layer_m.group(2).strip()
        if center_m:
            parsed["center_text"] = center_m.group(0)
            parsed["center"] = _parse_center_text(center_m.group(0))
        if zoom_m:
            parsed["zoom_command"] = zoom_m.group(1).strip()
        out[inc_id] = parsed
    return out


def _disciplines_from_enriched(card: dict[str, Any]) -> tuple[str | None, str | None]:
    d = card.get("disciplines")
    if isinstance(d, (list, tuple)) and len(d) >= 2:
        return str(d[0] or ""), str(d[1] or "")
    dp = card.get("discipline_pair")
    if isinstance(dp, str) and "/" in dp:
        parts = [p.strip() for p in dp.split("/")]
        if len(parts) >= 2:
            return parts[0], parts[1]
    return None, None


def _layers_from_enriched(card: dict[str, Any]) -> tuple[str | None, str | None]:
    lp = card.get("layer_pair")
    if isinstance(lp, str):
        la, lb = _parse_layer_pair_text(lp)
        if la or lb:
            return la, lb
    layers = card.get("layers")
    if isinstance(layers, (list, tuple)) and len(layers) >= 2:
        return str(layers[0] or "") or None, str(layers[1] or "") or None
    return None, None


def normalize_incident_for_reports(
    *,
    raw: dict[str, Any],
    human_code: str,
    group_code: str,
    enriched: dict[str, Any] | None = None,
    revision_parsed: dict[str, Any] | None = None,
    file_discipline_hints: dict[str, str] | None = None,
) -> NormalizedIncident:
    """Merge incident fields using explicit fallback order across sources."""
    enriched = enriched or {}
    revision_parsed = revision_parsed or {}
    file_discipline_hints = file_discipline_hints or {}
    prov = FieldProvenance()
    rep = raw.get("representative_conflict") or {}
    inc_id = str(raw.get("incident_id") or _NA)

    pair = raw.get("file_pair") or enriched.get("file_names") or []
    if isinstance(pair, tuple):
        pair = list(pair)
    file_a_full = basename(pair[0] if len(pair) > 0 else "")
    file_b_full = basename(pair[1] if len(pair) > 1 else "")

    # Layers
    la, lb = layers_from_incident(raw)
    if la or lb:
        prov.layers_source = "source_refs"
    if (la is None or lb is None) and enriched:
        ela, elb = _layers_from_enriched(enriched)
        if la is None and ela:
            la, prov.layers_source = ela, "coordination_context.layer_pair"
        if lb is None and elb:
            lb, prov.layers_source = elb, "coordination_context.layer_pair"
    if (la is None or lb is None) and revision_parsed:
        if la is None and revision_parsed.get("layer_a"):
            la = revision_parsed["layer_a"]
            prov.layers_source = "revision_md"
        if lb is None and revision_parsed.get("layer_b"):
            lb = revision_parsed["layer_b"]
            prov.layers_source = "revision_md"

    # Disciplines
    disc_a = str(rep.get("discipline_a") or "")
    disc_b = str(rep.get("discipline_b") or "")
    if disc_a:
        prov.discipline_source = "representative_conflict"
    eda, edb = _disciplines_from_enriched(enriched)
    if not disc_a and eda:
        disc_a, prov.discipline_source = eda, "coordination_context.disciplines"
    if not disc_b and edb:
        disc_b, prov.discipline_source = edb, "coordination_context.disciplines"
    if not disc_a and file_a_full in file_discipline_hints:
        disc_a = file_discipline_hints[file_a_full]
        prov.discipline_source = "analyzed_documents"
    if not disc_b and file_b_full in file_discipline_hints:
        disc_b = file_discipline_hints[file_b_full]
        prov.discipline_source = "analyzed_documents"
    disc_a = disc_a or _NA
    disc_b = disc_b or _NA

    # Level
    level = raw.get("level_id") or enriched.get("level_id")
    if raw.get("level_id"):
        prov.level_source = "incident.level_id"
    elif enriched.get("level_id"):
        prov.level_source = "coordination_context.level_id"
    level_id = format_optional(level)

    # Bounds
    bounds = _is_valid_bounds(raw.get("plan_bounds_mm"))
    if bounds:
        prov.bounds_source = "incident.plan_bounds_mm"
    if bounds is None:
        bounds = _is_valid_bounds(rep.get("plan_intersection_bounds_mm"))
        if bounds:
            prov.bounds_source = "representative_conflict.plan_intersection_bounds_mm"
    if bounds is None and enriched.get("bounds_short"):
        bounds = _parse_bounds_short(str(enriched["bounds_short"]))
        if bounds:
            prov.bounds_source = "coordination_context.bounds_short"

    # Center
    center = _is_valid_center(raw.get("plan_centroid_mm"))
    if center:
        prov.center_source = "incident.plan_centroid_mm"
    if center is None:
        center = _is_valid_center(rep.get("plan_intersection_centroid_mm"))
        if center:
            prov.center_source = "representative_conflict.plan_intersection_centroid_mm"
    if center is None and enriched.get("location_short"):
        center = _parse_center_text(str(enriched["location_short"]))
        if center:
            prov.center_source = "coordination_context.location_short"
    if center is None and revision_parsed.get("center"):
        center = revision_parsed["center"]
        prov.center_source = "revision_md"
    if center is None and bounds:
        center = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
        prov.center_source = "bbox_centroid"

    # Zoom
    zoom_cmd: str | None = None
    zoom_fb: str | None = None
    if revision_parsed.get("zoom_command"):
        zoom_cmd = str(revision_parsed["zoom_command"]).strip()
        prov.zoom_source = "revision_md"
    elif bounds:
        zoom_cmd = _zoom_from_bounds(bounds)
        prov.zoom_source = "generated_from_bounds"
    elif center:
        zoom_cmd = _zoom_from_center(center)
        prov.zoom_source = "generated_from_center"
    else:
        zoom_fb = (
            "Limites de zoom no disponibles; use Z E e inspeccione manualmente "
            "el nivel y las capas indicadas."
        )
        prov.zoom_source = "fallback_manual"

    area_mm2 = float(rep.get("plan_intersection_area_mm2") or enriched.get("area_mm2") or 0)
    z_raw = rep.get("overlap_depth_z_mm", enriched.get("overlap_depth_mm"))
    try:
        z_val = float(z_raw) if z_raw is not None else None
    except (TypeError, ValueError):
        z_val = None

    severity = str(enriched.get("severity") or compute_severity(area_mm2=area_mm2, z_depth_mm=z_val))
    confidence = confidence_es(raw.get("confidence") or rep.get("confidence") or enriched.get("report_confidence"))
    ha, hb = handles_from_incident(raw)

    warnings: list[str] = []
    if la is None or lb is None:
        warnings.append(f"{human_code}: capas no disponibles tras revisar todas las fuentes")
    if center is None:
        warnings.append(f"{human_code}: centro XY no disponible tras revisar todas las fuentes")
    if bounds is None:
        warnings.append(f"{human_code}: limites no disponibles tras revisar todas las fuentes")
    if zoom_cmd is None:
        warnings.append(f"{human_code}: comando Z W no generado (fallback manual)")

    return NormalizedIncident(
        incident_id=inc_id,
        human_code=human_code,
        group_code=group_code,
        layer_a=la,
        layer_b=lb,
        file_a_full=file_a_full,
        file_b_full=file_b_full,
        discipline_a=disc_a,
        discipline_b=disc_b,
        level_id=level_id,
        severity=severity.capitalize() if severity.islower() else severity,
        confidence=confidence,
        area_mm2=area_mm2,
        area_m2_text=format_area_m2(area_mm2),
        z_depth_mm=z_val,
        z_depth_text=format_optional(z_val, " mm") if z_val is not None else _NA,
        center=center,
        center_text=format_point(center[0], center[1]) if center else _NA,
        bounds=bounds,
        bounds_text=format_bounds(bounds),
        zoom_command=zoom_cmd,
        zoom_fallback=zoom_fb,
        member_count=int(raw.get("member_count") or enriched.get("member_count") or 1),
        clash_type=str(rep.get("clash_type") or _NA),
        handle_a=ha,
        handle_b=hb,
        what_to_check=str(enriched.get("human_description") or what_to_check_text(la, lb)),
        provenance=prov,
        warnings=warnings,
    )


def file_discipline_hints_from_documents(documents: list[dict[str, Any]]) -> dict[str, str]:
    hints: dict[str, str] = {}
    for doc in documents:
        name = basename(doc.get("original_name") or doc.get("file_name"))
        if name == _NA:
            continue
        bucket = str(doc.get("discipline_bucket") or doc.get("discipline") or "").lower()
        disc = doc.get("discipline") or _BUCKET_TO_DISCIPLINE.get(bucket)
        if disc:
            hints[name] = str(disc).upper() if len(str(disc)) > 3 else str(disc)
        elif bucket in _BUCKET_TO_DISCIPLINE:
            hints[name] = _BUCKET_TO_DISCIPLINE[bucket]
    return hints
