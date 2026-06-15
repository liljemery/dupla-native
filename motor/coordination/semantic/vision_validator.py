"""Validación visual de clashes y elementos usando modelo de visión."""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, asdict
from time import perf_counter
from typing import Any

from coordination.core.models_25d import Element25D
from coordination.reporting.tile_renderer import RenderedTile

logger = logging.getLogger(__name__)


@dataclass
class VisionElementResult:
    element_id: str
    semantic_type: str
    name: str | None
    confidence: str
    evidence: str


@dataclass
class VisionClashAssessment:
    appears_real: bool
    reason: str
    severity_visual: str


@dataclass
class VisionTileResult:
    tile_id: str
    incident_id: str | None
    elements_identified: list[VisionElementResult]
    clash_assessment: VisionClashAssessment | None
    model_used: str
    raw_response: str
    success: bool
    error: str | None = None


def _svg_to_png_base64(svg_content: str, width: int = 800) -> str:
    """Convert SVG to PNG base64 if optional cairosvg is available."""
    try:
        import cairosvg  # type: ignore
    except Exception:
        logger.debug("cairosvg is not available; falling back to SVG text vision prompt.")
        return ""

    try:
        png_bytes = cairosvg.svg2png(bytestring=svg_content.encode("utf-8"), output_width=width)
    except Exception as exc:
        logger.warning("SVG to PNG conversion failed; falling back to SVG text: %s", exc)
        return ""
    return base64.b64encode(png_bytes).decode("ascii")


def _build_coordination_prompt(
    tile: RenderedTile,
    elements_context: list[Element25D] | list[dict[str, Any]],
    texts_context: list[dict[str, Any]],
) -> str:
    bbox = tile.bbox_cad_mm
    element_rows = [_element_context_row(item) for item in elements_context]
    disciplines = sorted({row["discipline"] for row in element_rows if row.get("discipline")})
    elements_summary = "; ".join(
        f"{row['id']}:{row['discipline']}:{row.get('category') or 'unknown'}"
        for row in element_rows[:20]
    ) or "sin elementos CAD listados"
    texts_summary = "; ".join(
        str(item.get("content") or "") for item in texts_context[:20] if item.get("content")
    ) or "sin textos CAD cercanos"

    return f"""Analiza este recorte de un plano de construcción usado para coordinación técnica entre disciplinas.

Contexto del recorte:
- Área cubierta: ({bbox[0]:.0f}, {bbox[1]:.0f}) a ({bbox[2]:.0f}, {bbox[3]:.0f}) mm en coordenadas CAD
- Disciplinas presentes: {", ".join(disciplines) or "desconocidas"}
- Elementos CAD en la zona: {elements_summary}
- Textos CAD cercanos: {texts_summary}

Los polígonos están coloreados por disciplina. Si hay una zona roja semitransparente, es donde el sistema detectó una intersección geométrica entre disciplinas.

Responde SOLO con JSON válido, sin markdown ni backticks:
{{
  "elements_identified": [
    {{
      "element_id": "ID del Element25D si reconocible, sino null",
      "semantic_type": "puerta|ventana|muro|tubería|columna|ducto|bajante|válvula|switch|luminaria|otro",
      "name": "nombre visible (P-01, TUB-AF-3/4) o null",
      "confidence": "high|medium|low",
      "evidence": "razón breve"
    }}
  ],
  "clash_assessment": {{
    "appears_real": true,
    "reason": "explicación breve de por qué el clash es real o ruido",
    "severity_visual": "critical|major|minor|noise"
  }}
}}"""


def _call_vision_model(
    prompt: str,
    image_base64: str | None = None,
    svg_text: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Call the configured vision model and return parsed JSON plus debug metadata."""
    model_id = model or os.environ.get("COORDINATION_VISION_MODEL", "gpt-5.1")
    start = perf_counter()
    try:
        from openai import OpenAI

        client = OpenAI()
        user_text = prompt
        content: str | list[dict[str, Any]]
        if image_base64:
            content = [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_base64}",
                        "detail": "high",
                    },
                },
            ]
        else:
            content = (
                f"{user_text}\n\nEl siguiente SVG representa el plano; interpretalo como imagen vectorial:\n"
                f"{svg_text or ''}"
            )

        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "system",
                    "content": "Eres un validador técnico de coordinación BIM/CAD. Respondes solo JSON válido.",
                },
                {"role": "user", "content": content},
            ],
            timeout=60,
        )
        raw_text = response.choices[0].message.content or ""
        parsed = _extract_json(raw_text)
        usage = getattr(response, "usage", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "completion_tokens", None)
            total_tokens = getattr(usage, "total_tokens", None)
            estimated_cost = _estimate_cost_usd(prompt_tokens, completion_tokens)
            logger.info(
                "Vision model %s usage: prompt=%s completion=%s total=%s estimated_cost_usd=%s",
                model_id,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                f"{estimated_cost:.6f}" if estimated_cost is not None else "not_configured",
            )
        logger.info("Vision model %s responded in %.2fs", model_id, perf_counter() - start)
        parsed["_raw_response"] = raw_text
        parsed["_model_used"] = model_id
        return parsed
    except Exception as exc:
        logger.warning("Vision model call failed for %s: %s", model_id, exc)
        return {"_error": str(exc), "_raw_response": "", "_model_used": model_id}


def validate_tile(
    tile: RenderedTile,
    all_elements: list[Element25D],
    model: str | None = None,
) -> VisionTileResult:
    """Validate one rendered clash tile with the configured vision model."""
    element_lookup = {element.id: element for element in all_elements}
    elements_context = [element_lookup[element_id] for element_id in tile.elements_in_tile if element_id in element_lookup]
    prompt = _build_coordination_prompt(tile, elements_context, tile.texts_in_tile)
    image_base64 = _svg_to_png_base64(tile.svg_content, width=tile.width_px)
    payload = _call_vision_model(
        prompt,
        image_base64=image_base64 or None,
        svg_text=None if image_base64 else tile.svg_content,
        model=model,
    )
    return _parse_vision_payload(
        payload,
        tile_id=tile.tile_id,
        incident_id=tile.incident_id,
        model_used=model or payload.get("_model_used") or os.environ.get("COORDINATION_VISION_MODEL", "gpt-5.1"),
    )


def validate_incident_tiles(
    tiles: list[RenderedTile],
    all_elements: list[Element25D],
    max_tiles: int | None = None,
    model: str | None = None,
) -> list[VisionTileResult]:
    """Validate rendered incident tiles with a vision model."""
    selected = tiles[:max_tiles] if max_tiles is not None else tiles
    results: list[VisionTileResult] = []
    for index, tile in enumerate(selected, start=1):
        logger.info("Validating tile %d/%d: incident %s", index, len(selected), tile.incident_id)
        results.append(validate_tile(tile, all_elements, model=model))
    success_count = sum(1 for item in results if item.success)
    logger.info(
        "Vision validation summary: processed=%d successful=%d failed=%d",
        len(results),
        success_count,
        len(results) - success_count,
    )
    return results


def apply_vision_results(
    results: list[VisionTileResult],
    semantic_elements_by_id: dict[str, Any] | None = None,
) -> dict[str, VisionTileResult]:
    """Build incident-level vision overrides and optionally attach evidence to semantic metadata."""
    overrides: dict[str, VisionTileResult] = {}
    for result in results:
        if result.incident_id:
            overrides[result.incident_id] = result
        if not semantic_elements_by_id:
            continue
        for element_result in result.elements_identified:
            semantic_element = semantic_elements_by_id.get(element_result.element_id)
            if semantic_element is None:
                continue
            metadata = getattr(semantic_element, "metadata", None)
            if isinstance(metadata, dict):
                metadata.setdefault("vision_evidence", []).append(asdict(element_result))
    return overrides


def vision_tile_result_to_dict(result: VisionTileResult) -> dict[str, Any]:
    """Serialize a vision result for JSON output."""
    return {
        "tile_id": result.tile_id,
        "incident_id": result.incident_id,
        "success": result.success,
        "error": result.error,
        "model_used": result.model_used,
        "elements": [asdict(element) for element in result.elements_identified],
        "clash_assessment": asdict(result.clash_assessment) if result.clash_assessment else None,
        "raw_response": result.raw_response,
    }


def _parse_vision_payload(
    payload: dict[str, Any],
    *,
    tile_id: str,
    incident_id: str | None,
    model_used: str,
) -> VisionTileResult:
    error = payload.get("_error")
    raw_response = str(payload.get("_raw_response") or "")
    if error:
        return VisionTileResult(
            tile_id=tile_id,
            incident_id=incident_id,
            elements_identified=[],
            clash_assessment=None,
            model_used=model_used,
            raw_response=raw_response,
            success=False,
            error=str(error),
        )

    try:
        elements = [
            VisionElementResult(
                element_id=str(item.get("element_id") or ""),
                semantic_type=str(item.get("semantic_type") or "otro"),
                name=str(item["name"]) if item.get("name") is not None else None,
                confidence=str(item.get("confidence") or "low"),
                evidence=str(item.get("evidence") or ""),
            )
            for item in payload.get("elements_identified") or []
            if isinstance(item, dict)
        ]
        assessment_payload = payload.get("clash_assessment")
        assessment = None
        if isinstance(assessment_payload, dict):
            assessment = VisionClashAssessment(
                appears_real=bool(assessment_payload.get("appears_real")),
                reason=str(assessment_payload.get("reason") or ""),
                severity_visual=str(assessment_payload.get("severity_visual") or "noise"),
            )
        return VisionTileResult(
            tile_id=tile_id,
            incident_id=incident_id,
            elements_identified=elements,
            clash_assessment=assessment,
            model_used=model_used,
            raw_response=raw_response,
            success=True,
        )
    except Exception as exc:
        return VisionTileResult(
            tile_id=tile_id,
            incident_id=incident_id,
            elements_identified=[],
            clash_assessment=None,
            model_used=model_used,
            raw_response=raw_response,
            success=False,
            error=str(exc),
        )


def _extract_json(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return {"_error": f"invalid_json: {exc}", "_raw_response": raw_text}
    if not isinstance(parsed, dict):
        return {"_error": "invalid_json: root is not an object", "_raw_response": raw_text}
    parsed["_raw_response"] = raw_text
    return parsed


def _element_context_row(element: Element25D | dict[str, Any]) -> dict[str, Any]:
    if isinstance(element, dict):
        return element
    return {
        "id": element.id,
        "discipline": element.discipline.value,
        "category": element.category,
        "source_ref": element.source_ref,
        "level_id": element.metadata.get("level_id") or element.metadata.get("file_level_id") or element.z_data.level_id,
    }


def _estimate_cost_usd(prompt_tokens: Any, completion_tokens: Any) -> float | None:
    try:
        prompt_rate = float(os.environ.get("COORDINATION_VISION_PROMPT_USD_PER_1K") or "")
        completion_rate = float(os.environ.get("COORDINATION_VISION_COMPLETION_USD_PER_1K") or "")
        prompt_count = float(prompt_tokens or 0)
        completion_count = float(completion_tokens or 0)
    except ValueError:
        return None
    return (prompt_count / 1000.0 * prompt_rate) + (completion_count / 1000.0 * completion_rate)
