"""
(b) Parser del CUADRO DE ACABADOS -> mapa cuarto -> acabado.

El cuadro de acabados de un plano arquitectonico dice, por ambiente, que lleva
en piso, zocalo, pared y cielo. Hoy el pipeline tiene floor_finishes /
ceiling_finishes sueltos pero falta el *binding* ambiente -> acabado. Este modulo
corre un LLM con salida estructurada estricta sobre el texto del cuadro y devuelve:

    { "ambientes": [
        {"ambiente":"bano", "piso":"porcelanato", "zocalo":"porcelanato",
         "pared":"ceramica h=1.80", "cielo":"pvc"},
        ...
    ]}

y un helper para cruzarlo con los ambientes/areas detectados en el inventario
(best-effort por nombre de ambiente) para asignar areas de acabado por cuarto.

Degrada con gracia: sin OpenAI key / sin texto / si falla -> {} (no rompe el run).
El resultado se cachea en disco por hash del texto + modelo.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("dupla.finishes_schedule")

try:  # optional at runtime
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


_SURFACES = ["piso", "zocalo", "pared", "cielo"]


def _json_schema() -> dict[str, Any]:
    return {
        "name": "finishes_schedule",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["ambientes"],
            "properties": {
                "ambientes": {
                    "type": "array",
                    "description": "Una fila por ambiente del cuadro de acabados.",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["ambiente", "piso", "zocalo", "pared", "cielo"],
                        "properties": {
                            "ambiente": {
                                "type": "string",
                                "description": "Nombre del ambiente (sala, bano, cocina, dormitorio 1, ...).",
                            },
                            "piso": {"type": ["string", "null"], "description": "Acabado de piso o null."},
                            "zocalo": {"type": ["string", "null"], "description": "Acabado de zocalo o null."},
                            "pared": {"type": ["string", "null"], "description": "Acabado de pared o null."},
                            "cielo": {"type": ["string", "null"], "description": "Acabado de cielo raso o null."},
                        },
                    },
                }
            },
        },
    }


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


def _model() -> str:
    return (
        (os.getenv("DUPLA_FINISHES_MODEL") or "").strip()
        or (os.getenv("OPENAI_MODEL") or "").strip()
        or "gpt-4o-mini"
    )


def _cache_path(cache_dir: Path, notes_text: str, model: str) -> Path:
    digest = hashlib.sha256((model + "\n" + notes_text).encode("utf-8")).hexdigest()[:16]
    return cache_dir / "finishes_schedule" / f"finishes_{digest}.json"


def extract_finishes_schedule(
    notes_text: str | None,
    *,
    cache_dir: Path | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Return {"ambientes": [...]} parsed from the finishes table, or {} on miss."""
    text = (notes_text or "").strip()
    if not text:
        return {}

    api_key = _resolve_openai_key()
    if OpenAI is None or not api_key:
        logger.info("finishes_schedule: no OpenAI key/package — skipping")
        return {}

    resolved_model = model or _model()

    cache_file: Path | None = None
    if cache_dir is not None:
        cache_file = _cache_path(Path(cache_dir), text, resolved_model)
        if cache_file.exists():
            try:
                logger.info("finishes_schedule: cache HIT %s", cache_file.name)
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("finishes_schedule: bad cache %s; re-extracting", cache_file, exc_info=True)

    try:
        client = OpenAI(api_key=api_key)
        system = (
            "Eres un presupuestista senior. Lee el CUADRO DE ACABADOS de un plano "
            "arquitectonico y devuelve una fila por ambiente con su acabado de piso, "
            "zocalo, pared y cielo. Usa null cuando el cuadro no especifique ese campo. "
            "No inventes ambientes que no aparezcan."
        )
        response = client.chat.completions.create(
            model=resolved_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "CUADRO DE ACABADOS / NOTAS:\n\n" + text},
            ],
            response_format={"type": "json_schema", "json_schema": _json_schema()},
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content or "{}")
    except Exception:
        logger.warning("finishes_schedule: extraction failed — skipping", exc_info=True)
        return {}

    if cache_file is not None:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("finishes_schedule: could not write cache", exc_info=True)

    n = len(data.get("ambientes") or [])
    logger.info("finishes_schedule: parsed %d ambientes", n)
    return data


def _norm(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[áàä]", "a", text)
    text = re.sub(r"[éèë]", "e", text)
    text = re.sub(r"[íìï]", "i", text)
    text = re.sub(r"[óòö]", "o", text)
    text = re.sub(r"[úùü]", "u", text)
    text = re.sub(r"\s+", " ", text)
    return text


def bind_finishes_to_rooms(
    schedule: dict[str, Any],
    room_names: list[str],
) -> dict[str, dict[str, Any]]:
    """Best-effort match of schedule rows to detected room names.

    Returns {room_name: {piso, zocalo, pared, cielo}}. Matching is by normalized
    substring (ambiente token contained in room name or vice versa).
    """
    rows = (schedule or {}).get("ambientes") or []
    if not rows or not room_names:
        return {}
    bound: dict[str, dict[str, Any]] = {}
    for room in room_names:
        room_n = _norm(room)
        best: dict[str, Any] | None = None
        for row in rows:
            amb_n = _norm(str(row.get("ambiente", "")))
            if not amb_n:
                continue
            if amb_n in room_n or room_n in amb_n:
                best = row
                break
        if best:
            bound[room] = {s: best.get(s) for s in _SURFACES}
    return bound
