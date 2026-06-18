"""
Extrae CONFIG DURA del proyecto desde las notas/leyendas del plano.

Hoy ``methodology`` es contexto blando: un texto que se inyecta en el prompt de
vision con la esperanza de que el modelo lo respete. Este modulo lo convierte en
configuracion dura: corre un LLM con *salida estructurada estricta*
(``json_schema`` strict) sobre el texto OCR de notas/leyendas y devuelve un JSON
con los parametros globales que las reglas/cuantificadores pueden consumir:

    f'c, fy, recubrimiento, bloque por defecto, mortero, impermeabilizacion,
    abundamiento de excavacion y factores de desperdicio.

Degrada con gracia: si no hay OPENAI_API_KEY/DUPLA_OPENAI_KEYS, si no hay texto
de notas, o si la llamada falla, devuelve los defaults de
``project_parameters_defaults.yaml`` (globales + override por disciplina).
El resultado se cachea en disco por hash del texto + disciplina + modelo.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("dupla.project_parameters")

_DEFAULTS_PATH = Path(__file__).resolve().parent / "project_parameters_defaults.yaml"

try:  # optional at runtime
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ProjectParameters:
    """Hard, machine-readable project configuration derived from plan notes."""

    fc_default: int = 280
    fy: int = 4200
    recubrimiento_cm: float = 4.0
    bloque_default: str = "block_6in"
    mortero: str = "1:3"
    impermeabilizacion: str | None = None
    abundamiento: float = 1.25
    excavacion_margen_m: float = 0.10
    desperdicios: dict[str, float] = field(default_factory=dict)
    # Provenance — not part of the LLM schema, set by this module.
    source: str = "defaults"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectParameters":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        clean = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**clean)


# Fields the LLM is asked to fill. desperdicios is a nested object.
_WASTE_KEYS = ["hormigon", "acero", "mamposteria", "mortero", "acabados", "pintura"]


def _json_schema() -> dict[str, Any]:
    """Strict json_schema for OpenAI structured outputs."""
    return {
        "name": "project_parameters",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "fc_default",
                "fy",
                "recubrimiento_cm",
                "bloque_default",
                "mortero",
                "impermeabilizacion",
                "abundamiento",
                "excavacion_margen_m",
                "desperdicios",
            ],
            "properties": {
                "fc_default": {
                    "type": ["integer", "null"],
                    "description": "f'c del hormigon estructural en kg/cm2 (p.ej. 210, 280). null si la nota no lo indica.",
                },
                "fy": {
                    "type": ["integer", "null"],
                    "description": "Fluencia del acero de refuerzo en kg/cm2 (p.ej. 4200). null si no se indica.",
                },
                "recubrimiento_cm": {
                    "type": ["number", "null"],
                    "description": "Recubrimiento de armadura en cm. null si no se indica.",
                },
                "bloque_default": {
                    "type": ["string", "null"],
                    "description": "Bloque por defecto: block_4in, block_6in, block_8in. null si no se indica.",
                },
                "mortero": {
                    "type": ["string", "null"],
                    "description": "Proporcion de mortero (p.ej. '1:3', '1:4'). null si no se indica.",
                },
                "impermeabilizacion": {
                    "type": ["string", "null"],
                    "description": "Sistema/descripcion de impermeabilizacion si la nota lo menciona; si no, null.",
                },
                "abundamiento": {
                    "type": ["number", "null"],
                    "description": "Factor de esponjamiento de tierra excavada (p.ej. 1.25). null si no se indica.",
                },
                "excavacion_margen_m": {
                    "type": ["number", "null"],
                    "description": "Sobre-ancho de excavacion por cara en metros. null si no se indica.",
                },
                "desperdicios": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": _WASTE_KEYS,
                    "properties": {
                        k: {
                            "type": ["number", "null"],
                            "description": f"Factor de desperdicio para {k} (fraccion, p.ej. 0.05). null si no se indica.",
                        }
                        for k in _WASTE_KEYS
                    },
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def _load_defaults_file() -> dict[str, Any]:
    if not _DEFAULTS_PATH.exists():
        return {}
    try:
        return yaml.safe_load(_DEFAULTS_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.warning("Could not parse %s; using built-in defaults", _DEFAULTS_PATH, exc_info=True)
        return {}


def load_defaults(discipline: str | None = None) -> dict[str, Any]:
    """Global defaults merged with the per-discipline override block."""
    data = _load_defaults_file()
    merged: dict[str, Any] = copy.deepcopy(data.get("defaults") or {})
    if not merged:
        merged = ProjectParameters().to_dict()
        merged.pop("source", None)
    if discipline:
        disc_block = (data.get("disciplines") or {}).get(discipline) or {}
        merged = _deep_merge(merged, disc_block)
    merged.setdefault("desperdicios", {})
    return merged


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _apply_extracted_over_defaults(
    defaults: dict[str, Any],
    extracted: dict[str, Any],
) -> dict[str, Any]:
    """Extracted (non-null) values win; null/missing fall back to defaults."""
    out = copy.deepcopy(defaults)
    for key, value in (extracted or {}).items():
        if key == "desperdicios" and isinstance(value, dict):
            waste = dict(out.get("desperdicios") or {})
            for wk, wv in value.items():
                if wv is not None:
                    waste[wk] = wv
            out["desperdicios"] = waste
        elif value is not None:
            out[key] = value
    return out


# ---------------------------------------------------------------------------
# Notes collection
# ---------------------------------------------------------------------------

def collect_notes_text(
    cad_facts: dict[str, Any] | None = None,
    *,
    legend_page_map: dict[str, Any] | None = None,
    extra: str | None = None,
    max_chars: int = 16000,
) -> str:
    """Gather plan note/legend text from CAD facts + legend OCR into one block.

    Defensive: scans common text containers without assuming an exact schema.
    """
    chunks: list[str] = []

    def _push(value: Any) -> None:
        if isinstance(value, str):
            v = value.strip()
            if v:
                chunks.append(v)

    facts = cad_facts or {}
    # Common containers produced by json_processor / inventory hints.
    for container_key in ("texts", "notes", "annotations"):
        container = facts.get(container_key)
        if isinstance(container, list):
            for item in container:
                if isinstance(item, dict):
                    _push(item.get("content") or item.get("text"))
                else:
                    _push(item)

    hints = facts.get("inventory_hints")
    if isinstance(hints, dict):
        markers = hints.get("level_markers")
        if isinstance(markers, list):
            for m in markers:
                if isinstance(m, dict):
                    _push(m.get("content"))
                else:
                    _push(m)

    if legend_page_map:
        for entry in legend_page_map.values():
            if isinstance(entry, dict):
                _push(entry.get("floor_label"))

    _push(extra)

    # De-dup preserving order; cap length.
    seen: set[str] = set()
    unique: list[str] = []
    for c in chunks:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    text = "\n".join(unique)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


# ---------------------------------------------------------------------------
# OpenAI key + model
# ---------------------------------------------------------------------------

def _resolve_openai_key() -> str | None:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if api_key:
        return api_key
    csv_keys = (os.getenv("DUPLA_OPENAI_KEYS") or "").strip()
    if csv_keys:
        for candidate in csv_keys.split(","):
            candidate = candidate.strip()
            if candidate:
                return candidate
    return None


def _params_model() -> str:
    return (
        (os.getenv("DUPLA_PARAMS_MODEL") or "").strip()
        or (os.getenv("OPENAI_MODEL") or "").strip()
        or "gpt-4o-mini"
    )


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_path(cache_dir: Path, notes_text: str, discipline: str | None, model: str) -> Path:
    payload = json.dumps(
        {"notes": notes_text, "discipline": discipline or "", "model": model},
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return cache_dir / "project_parameters" / f"params_{digest}.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_project_parameters(
    notes_text: str | None,
    *,
    discipline: str | None = None,
    cache_dir: Path | None = None,
    model: str | None = None,
) -> ProjectParameters:
    """Return hard project parameters from plan notes, with graceful fallback.

    Resolution order:
      1. defaults (global + discipline) from project_parameters_defaults.yaml
      2. cached extraction if present
      3. fresh OpenAI structured-output extraction (extracted values win)
    """
    defaults = load_defaults(discipline)
    text = (notes_text or "").strip()

    if not text:
        logger.info("project_parameters: no notes text — using defaults (discipline=%s)", discipline)
        params = ProjectParameters.from_dict(defaults)
        params.source = "defaults"
        return params

    api_key = _resolve_openai_key()
    if OpenAI is None or not api_key:
        logger.info(
            "project_parameters: no OpenAI key/package — using defaults (discipline=%s)", discipline
        )
        params = ProjectParameters.from_dict(defaults)
        params.source = "defaults"
        return params

    resolved_model = (model or _params_model())

    # Disk cache.
    cache_file: Path | None = None
    if cache_dir is not None:
        cache_file = _cache_path(Path(cache_dir), text, discipline, resolved_model)
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                merged = _apply_extracted_over_defaults(defaults, cached)
                params = ProjectParameters.from_dict(merged)
                params.source = "cache"
                logger.info("project_parameters: cache HIT %s", cache_file.name)
                return params
            except Exception:
                logger.warning("project_parameters: bad cache %s; re-extracting", cache_file, exc_info=True)

    try:
        extracted = _call_openai(text, api_key=api_key, model=resolved_model, discipline=discipline)
    except Exception:
        logger.warning("project_parameters: extraction failed — using defaults", exc_info=True)
        params = ProjectParameters.from_dict(defaults)
        params.source = "defaults"
        return params

    if cache_file is not None:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("project_parameters: could not write cache %s", cache_file, exc_info=True)

    merged = _apply_extracted_over_defaults(defaults, extracted)
    params = ProjectParameters.from_dict(merged)
    params.source = "extracted"
    logger.info(
        "project_parameters: extracted (discipline=%s, model=%s): f'c=%s fy=%s bloque=%s",
        discipline, resolved_model, params.fc_default, params.fy, params.bloque_default,
    )
    return params


def _call_openai(
    notes_text: str,
    *,
    api_key: str,
    model: str,
    discipline: str | None,
) -> dict[str, Any]:
    client = OpenAI(api_key=api_key)
    disc_hint = f" Disciplina objetivo: {discipline}." if discipline else ""
    system = (
        "Eres un presupuestista senior de construccion en Republica Dominicana. "
        "Lee las NOTAS y LEYENDAS de un plano y extrae los parametros tecnicos globales "
        "del proyecto. Devuelve SOLO los valores que aparezcan explicitamente en el texto; "
        "si un valor no aparece, devuelve null (no inventes)." + disc_hint
    )
    user = "NOTAS / LEYENDAS DEL PLANO:\n\n" + notes_text

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_schema", "json_schema": _json_schema()},
        temperature=0,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)
