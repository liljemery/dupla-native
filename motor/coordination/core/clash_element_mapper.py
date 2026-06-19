"""Conservative spatial mapper from primary incidents to exact CAD entities."""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

from coordination.semantic.semantic_elements import SemanticElement25D

ANNOTATION_LAYER_TOKENS = ("TITULOS", "ESCALA_HUMANA", "TEXT", "ANNO", "DIM", "LABEL")
LOW_TRUST_LAYER_TOKENS = ("MARCO", "EST_PROYECCION")
PROXY_GEOMETRY_SOURCES = ("dwg_accore_bbox", "dwg_com_bbox", "proxy_FALLBACK")


def map_primary_incidents_to_elements(
    *,
    generated_at: str,
    project_name: str,
    run_label: str,
    primary_payload: dict[str, Any],
    elements_by_dwg_payload: dict[str, Any],
    margin_mm: float = 250.0,
) -> dict[str, Any]:
    semantic_by_file = _semantic_elements_by_file(elements_by_dwg_payload)
    pair_lookup = _pair_id_lookup(primary_payload)
    mapped: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    confidence_mix: Counter[str] = Counter()

    for incident in primary_payload.get("incidents") or []:
        result = _map_single_incident(
            incident=incident,
            semantic_by_file=semantic_by_file,
            pair_lookup=pair_lookup,
            margin_mm=margin_mm,
        )
        confidence_mix[result["mapping_confidence"]] += 1
        if result["status"] == "mapped":
            mapped.append(result)
        else:
            unmapped.append(result)

    return {
        "generated_at": generated_at,
        "project_name": project_name,
        "run_label": run_label,
        "mapped_incidents_count": len(mapped),
        "unmapped_incidents_count": len(unmapped),
        "mapping_confidence_mix": dict(confidence_mix),
        "mapped": mapped,
        "unmapped": unmapped,
    }


def _map_single_incident(
    *,
    incident: dict[str, Any],
    semantic_by_file: dict[str, list[SemanticElement25D]],
    pair_lookup: dict[tuple[str, str], str],
    margin_mm: float,
) -> dict[str, Any]:
    incident_id = str(incident.get("incident_id") or "unknown")
    file_pair = tuple(str(item) for item in incident.get("file_pair") or [])
    pair_id = pair_lookup.get(tuple(sorted(file_pair)))
    representative = incident.get("representative_conflict") or {}
    plan_bounds = tuple(
        float(value)
        for value in (
            incident.get("plan_bounds_mm")
            or representative.get("plan_intersection_bounds_mm")
            or (0.0, 0.0, 0.0, 0.0)
        )
    )
    plan_centroid = tuple(
        float(value)
        for value in (
            incident.get("plan_centroid_mm")
            or representative.get("plan_intersection_centroid_mm")
            or (0.0, 0.0)
        )
    )
    source_refs = list(representative.get("source_refs") or [])
    side_results: list[dict[str, Any] | None] = []

    for index, source_file in enumerate(file_pair):
        source_ref = source_refs[index] if index < len(source_refs) else ""
        candidates = semantic_by_file.get(source_file, [])
        side_results.append(
            _best_candidate_for_side(
                source_file=source_file,
                source_layer=_layer_from_source_ref(source_ref),
                source_handle=_handle_from_source_ref(source_ref),
                source_ref=source_ref,
                candidates=candidates,
                incident_bbox=plan_bounds,
                incident_centroid=plan_centroid,
                margin_mm=margin_mm,
            )
        )

    if not side_results or any(side is None for side in side_results):
        return {
            "status": "unmapped",
            "incident_id": incident_id,
            "pair_id": pair_id,
            "mapping_confidence": "unmapped",
            "score": 0.0,
            "distance_mm": None,
            "mapping_reason_codes": ["missing_entity_side"],
            "human_sentence": _human_sentence_unmapped(
                incident_id=incident_id,
                file_pair=file_pair,
                level_id=str(incident.get("level_id") or "mixed"),
                centroid=plan_centroid,
            ),
            "location": {
                "level": str(incident.get("level_id") or "mixed"),
                "x": plan_centroid[0] if len(plan_centroid) > 0 else 0.0,
                "y": plan_centroid[1] if len(plan_centroid) > 1 else 0.0,
                "unit": "mm",
            },
            "file_sides": [side for side in side_results if side is not None],
            "reason": "No semantic element found near clash bounds for both files.",
        }

    left, right = side_results[0], side_results[1]
    assert left is not None and right is not None
    score = round(min(float(left["score"]), float(right["score"])), 3)
    mapping_confidence, mapping_reason_codes = _mapping_confidence(left=left, right=right, score=score)
    distance_mm = max(float(left["distance_mm"]), float(right["distance_mm"]))
    status = "mapped" if mapping_confidence != "unmapped" else "unmapped"

    payload = {
        "status": status,
        "incident_id": incident_id,
        "pair_id": pair_id,
        "mapping_confidence": mapping_confidence,
        "score": score,
        "distance_mm": distance_mm,
        "mapping_reason_codes": mapping_reason_codes,
        "human_sentence": _human_sentence(
            incident_id=incident_id,
            level_id=str(incident.get("level_id") or "mixed"),
            centroid=plan_centroid,
            left=left,
            right=right,
            mapping_confidence=mapping_confidence,
        ),
        "location": {
            "level": str(incident.get("level_id") or "mixed"),
            "x": plan_centroid[0] if len(plan_centroid) > 0 else 0.0,
            "y": plan_centroid[1] if len(plan_centroid) > 1 else 0.0,
            "unit": "mm",
        },
        "file_a": left,
        "file_b": right,
        "relationship": {
            "type": "bbox_first_centroid_second",
            "score": score,
            "distance_mm": distance_mm,
        },
    }
    if status != "mapped":
        payload["reason"] = "Mapping confidence stayed below defendable threshold."
    return payload


def _best_candidate_for_side(
    *,
    source_file: str,
    source_layer: str | None,
    source_handle: str | None,
    source_ref: str,
    candidates: list[SemanticElement25D],
    incident_bbox: tuple[float, float, float, float],
    incident_centroid: tuple[float, float],
    margin_mm: float,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    expanded_bbox = _expand_bbox(incident_bbox, margin_mm=margin_mm)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for element in candidates:
        if element.bbox_mm is None or element.centroid_mm is None:
            continue
        if not _bbox_intersects(expanded_bbox, element.bbox_mm):
            continue

        reason_codes: list[str] = []
        overlap_score = _bbox_overlap_score(incident_bbox, element.bbox_mm)
        if overlap_score >= 0.85:
            reason_codes.append("bbox_overlap_strong")
        elif overlap_score > 0.0:
            reason_codes.append("bbox_overlap_partial")

        distance_mm = _centroid_distance(incident_centroid, element.centroid_mm)
        distance_score = _distance_score(distance_mm, margin_mm=margin_mm)
        if distance_score >= 0.95:
            reason_codes.append("centroid_near")
        elif distance_score >= 0.45:
            reason_codes.append("centroid_acceptable")

        layer_score = 1.0 if source_layer and source_layer == element.layer else 0.35
        if layer_score >= 1.0:
            reason_codes.append("layer_match")

        handle_score = 1.0 if source_handle and source_handle == element.cad_handle else 0.0
        if handle_score >= 1.0:
            reason_codes.append("handle_match")

        geometry_score = {"high": 1.0, "medium": 0.7, "low": 0.35}.get(element.geometry_confidence, 0.5)
        geometry_source = str(element.geometry_source or "unknown")
        geometry_role = str(element.geometry_role or "primary")
        if geometry_role != "primary":
            reason_codes.append("suppressed_geometry_penalty")
        if geometry_source in PROXY_GEOMETRY_SOURCES:
            reason_codes.append("proxy_geometry_penalty")

        score = round(
            (0.35 * overlap_score)
            + (0.25 * distance_score)
            + (0.15 * layer_score)
            + (0.15 * geometry_score)
            + (0.10 * handle_score),
            3,
        )
        ranked.append(
            (
                score,
                {
                    "source_file": source_file,
                    "semantic_element_id": element.semantic_element_id,
                    "source_element_id": element.source_element_id,
                    "element_name": element.element_name,
                    "element_type": element.element_type,
                    "layer": element.layer,
                    "cad_handle": element.cad_handle,
                    "entity_type": element.entity_type,
                    "bbox_mm": element.bbox_mm,
                    "centroid_mm": element.centroid_mm,
                    "geometry_source": geometry_source,
                    "geometry_role": geometry_role,
                    "score": score,
                    "distance_mm": round(distance_mm, 3),
                    "source_ref": source_ref,
                    "geometry_confidence": element.geometry_confidence,
                    "semantic_type_confidence": element.semantic_type_confidence,
                    "semantic_type_reason": element.semantic_type_reason,
                    "classification_signals": list(element.classification_signals),
                    "name_confidence": element.name_confidence,
                    "mapping_reason_codes": reason_codes,
                },
            )
        )
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1]["distance_mm"]))
    return ranked[0][1]


def _mapping_confidence(*, left: dict[str, Any], right: dict[str, Any], score: float) -> tuple[str, list[str]]:
    blocked_layers = {
        _normalize_token(str(left.get("layer") or "")),
        _normalize_token(str(right.get("layer") or "")),
    }
    reason_codes = _merge_reason_codes(left, right)
    if any(_contains_blocked_annotation(layer) for layer in blocked_layers):
        return ("unmapped", reason_codes + ["annotation_blocked"])

    confidence = "high" if score >= 0.75 else "medium" if score >= 0.55 else "low"
    if _has_proxy_geometry(left) and _has_proxy_geometry(right):
        confidence = "low"
        reason_codes.append("double_proxy_geometry_cap")
    elif _has_proxy_geometry(left) or _has_proxy_geometry(right):
        if confidence == "high":
            confidence = "medium"
        reason_codes.append("single_proxy_geometry_cap")

    if str(left.get("geometry_role") or "primary") != "primary" or str(right.get("geometry_role") or "primary") != "primary":
        if confidence == "high":
            confidence = "medium"
        reason_codes.append("suppressed_geometry_cap")

    if any(_contains_low_trust_token(layer) for layer in blocked_layers):
        confidence = "medium" if confidence == "high" else "low"
        reason_codes.append("low_trust_layer_capped")

    if confidence == "low" and score < 0.35:
        return ("unmapped", reason_codes + ["score_below_publishable_threshold"])
    return (confidence, reason_codes)


def _semantic_elements_by_file(elements_by_dwg_payload: dict[str, Any]) -> dict[str, list[SemanticElement25D]]:
    out: dict[str, list[SemanticElement25D]] = {}
    for file_payload in elements_by_dwg_payload.get("files") or []:
        source_file = str(file_payload.get("source_file") or "")
        out[source_file] = [
            SemanticElement25D.model_validate(item)
            for item in file_payload.get("elements") or []
        ]
    return out


def _pair_id_lookup(primary_payload: dict[str, Any]) -> dict[tuple[str, str], str]:
    pairs: dict[tuple[str, str], str] = {}
    ordered_pairs = sorted(
        {
            tuple(sorted(tuple(str(item) for item in incident.get("file_pair") or ())))
            for incident in primary_payload.get("incidents") or []
        }
    )
    for index, pair in enumerate(ordered_pairs, start=1):
        pairs[pair] = f"pair_{index:03d}"
    return pairs


def _expand_bbox(bbox: tuple[float, float, float, float], *, margin_mm: float) -> tuple[float, float, float, float]:
    return (bbox[0] - margin_mm, bbox[1] - margin_mm, bbox[2] + margin_mm, bbox[3] + margin_mm)


def _bbox_intersects(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> bool:
    return not (left[2] < right[0] or right[2] < left[0] or left[3] < right[1] or right[3] < left[1])


def _bbox_overlap_score(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    ix0 = max(left[0], right[0])
    iy0 = max(left[1], right[1])
    ix1 = min(left[2], right[2])
    iy1 = min(left[3], right[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    left_area = max((left[2] - left[0]) * (left[3] - left[1]), 1.0)
    right_area = max((right[2] - right[0]) * (right[3] - right[1]), 1.0)
    return min(1.0, intersection / min(left_area, right_area))


def _centroid_distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.sqrt(((left[0] - right[0]) ** 2) + ((left[1] - right[1]) ** 2))


def _distance_score(distance_mm: float, *, margin_mm: float) -> float:
    if distance_mm <= margin_mm:
        return 1.0
    if distance_mm <= margin_mm * 2.0:
        return 0.75
    if distance_mm <= margin_mm * 4.0:
        return 0.45
    return 0.1


def _layer_from_source_ref(source_ref: str) -> str | None:
    parts = source_ref.split("|")
    return parts[1] if len(parts) > 1 else None


def _handle_from_source_ref(source_ref: str) -> str | None:
    parts = source_ref.split("|")
    return parts[3] if len(parts) > 3 else None


def _normalize_token(value: str) -> str:
    return value.strip().upper()


def _contains_blocked_annotation(value: str) -> bool:
    return any(token in value for token in ANNOTATION_LAYER_TOKENS)


def _contains_low_trust_token(value: str) -> bool:
    return any(token in value for token in LOW_TRUST_LAYER_TOKENS)


def _has_proxy_geometry(side: dict[str, Any]) -> bool:
    return str(side.get("geometry_source") or "") in PROXY_GEOMETRY_SOURCES


def _merge_reason_codes(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for code in list(left.get("mapping_reason_codes") or []) + list(right.get("mapping_reason_codes") or []):
        token = str(code)
        if token and token not in seen:
            seen.add(token)
            merged.append(token)
    return merged


def _human_sentence(
    *,
    incident_id: str,
    level_id: str,
    centroid: tuple[float, float],
    left: dict[str, Any],
    right: dict[str, Any],
    mapping_confidence: str,
) -> str:
    left_name = _publishable_semantic_name(left)
    right_name = _publishable_semantic_name(right)
    if mapping_confidence in {"medium", "high"} and left_name and right_name:
        return (
            f"Posible inconsistencia entre {left_name} y {right_name}, ubicada en {level_id} "
            f"cerca de X={round(centroid[0])}, Y={round(centroid[1])} mm. Requiere validacion manual."
        )

    left_type = _publishable_semantic_type(left)
    right_type = _publishable_semantic_type(right)
    if mapping_confidence in {"medium", "high"} and left_type and right_type:
        return (
            f"Incidencia {incident_id} vinculada a entidad CAD exacta `{left.get('cad_handle')}` "
            f"tipificada como `{left_type}` y entidad CAD exacta `{right.get('cad_handle')}` "
            f"tipificada como `{right_type}`, ubicada en {level_id} cerca de "
            f"X={round(centroid[0])}, Y={round(centroid[1])} mm. Requiere validacion manual."
        )

    return (
        f"Incidencia {incident_id} vinculada de forma conservadora a entidades CAD "
        f"`{left.get('cad_handle')}`/{left.get('entity_type')} en `{left.get('layer')}` y "
        f"`{right.get('cad_handle')}`/{right.get('entity_type')} en `{right.get('layer')}`, "
        f"ubicada en {level_id} cerca de X={round(centroid[0])}, Y={round(centroid[1])} mm. "
        f"No se afirma nombre constructivo; requiere validacion manual."
    )


def _human_sentence_unmapped(
    *,
    incident_id: str,
    file_pair: tuple[str, ...],
    level_id: str,
    centroid: tuple[float, float],
) -> str:
    names = " vs ".join(Path(path).name for path in file_pair)
    return (
        f"Incidencia {incident_id} en {names}, ubicada en {level_id} cerca de "
        f"X={round(centroid[0])}, Y={round(centroid[1])} mm. No se encontro mapping espacial suficiente."
    )


def _publishable_semantic_type(side: dict[str, Any]) -> str | None:
    confidence = str(side.get("semantic_type_confidence") or "unknown")
    element_type = str(side.get("element_type") or "")
    if confidence not in {"medium", "high"}:
        return None
    if element_type.startswith("unknown_"):
        return None
    return element_type


def _publishable_semantic_name(side: dict[str, Any]) -> str | None:
    confidence = str(side.get("name_confidence") or "low")
    name = side.get("element_name")
    if confidence not in {"medium", "high"}:
        return None
    return str(name) if name else None
