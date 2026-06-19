"""
(P1.5) Parser de CUADROS de puertas y ventanas.

El cuadro de puertas/ventanas es la autoridad de conteo, tipo y dimensiones.
Corre vision con salida estructurada estricta sobre las laminas renderizadas y
devuelve filas tipadas:

    {"filas": [
        {"mark":"P1","kind":"puerta","type":"principal","material":"madera",
         "width_m":0.90,"height_m":2.10,"count":1},
        {"mark":"V2","kind":"ventana","type":"corrediza","material":"aluminio",
         "width_m":1.20,"height_m":1.10,"count":6},
    ]}

Opt-in con DUPLA_OPENINGS_SCHEDULE (default off). Degrada con gracia y cachea por
hash de imagen + modelo, igual que structural_schedule.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("dupla.openings_schedule")

try:  # optional at runtime
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


_SYSTEM_PROMPT = """\
Presupuestista senior (arquitectura, Republica Dominicana).
Invocacion: tool openings_schedule sobre la lamina adjunta (imagen).

Objetivo: localizar el CUADRO DE PUERTAS y/o VENTANAS (tabla con marcas) y devolver una fila por marca.

Reglas:
- Solo filas que aparezcan en el cuadro. No infieras desde simbologia del plano ni cotas sueltas.
- Sin cuadro de puertas/ventanas en la lamina -> filas=[].
- mark: copia literal (P1, P-01, V2, VE-3). Una fila por marca unica del cuadro.
- kind: "puerta" o "ventana" segun la fila/seccion del cuadro (marcas P* vs V* ayudan pero no bastan solas).
- type y material: literal del cuadro (principal, interior, corrediza, fija, madera, aluminio, pvc, vidrio).
- width_m / height_m: en METROS. Convierte cm/mm del cuadro (90 cm -> 0.90, 2.10 m -> 2.10).
- count: cantidad entera de esa marca segun el cuadro; null si no aparece.
- null solo si la columna existe y la celda esta vacia, es "-" o "N/A".
- "VER DETALLE" / "VER PLANO": null en ese campo.
- Ignora planta dibujada, leyenda general, membrete, cuadros de acabados u otros.

Si hay cuadros separados de puertas y ventanas en la misma lamina, une todas las filas.\
"""


def is_enabled() -> bool:
    return (os.getenv("DUPLA_OPENINGS_SCHEDULE") or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_schema() -> dict[str, Any]:
    return {
        "name": "openings_schedule",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["filas"],
            "properties": {
                "filas": {
                    "type": "array",
                    "description": (
                        "Filas del cuadro de puertas/ventanas unicamente. "
                        "Vacio si la lamina no contiene cuadro."
                    ),
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["mark", "kind", "type", "material", "width_m", "height_m", "count"],
                        "properties": {
                            "mark": {
                                "type": "string",
                                "description": "Marca literal del cuadro (P1, P-01, V2, VE-3).",
                            },
                            "kind": {
                                "type": "string",
                                "enum": ["puerta", "ventana"],
                                "description": "puerta o ventana segun la fila del cuadro.",
                            },
                            "type": {
                                "type": ["string", "null"],
                                "description": "Tipo literal (principal, interior, corrediza, fija, oscilobatiente). null si vacio.",
                            },
                            "material": {
                                "type": ["string", "null"],
                                "description": "Material literal (madera, aluminio, pvc, metal, vidrio). null si vacio.",
                            },
                            "width_m": {
                                "type": ["number", "null"],
                                "description": "Ancho en metros (convertir cm/mm del cuadro). null si no aparece.",
                            },
                            "height_m": {
                                "type": ["number", "null"],
                                "description": "Alto en metros (convertir cm/mm del cuadro). null si no aparece.",
                            },
                            "count": {
                                "type": ["integer", "null"],
                                "description": "Cantidad de unidades de esta marca. null si no aparece.",
                            },
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
        (os.getenv("DUPLA_OPENINGS_SCHEDULE_MODEL") or "").strip()
        or (os.getenv("OPENAI_MODEL") or "").strip()
        or "gpt-4o-mini"
    )


def _max_pages() -> int:
    raw = (os.getenv("DUPLA_OPENINGS_SCHEDULE_MAX_PAGES") or "6").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 6


def _cache_path(cache_dir: Path, image_bytes_digest: str, model: str) -> Path:
    digest = hashlib.sha256((model + "\n" + image_bytes_digest).encode("utf-8")).hexdigest()[:16]
    return cache_dir / "openings_schedule" / f"openings_{digest}.json"


def _parse_one(client: "OpenAI", image_path: Path, model: str) -> list[dict[str, Any]]:
    b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            },
        ],
        response_format={"type": "json_schema", "json_schema": _json_schema()},
        temperature=0,
    )
    data = json.loads(response.choices[0].message.content or "{}")
    return list(data.get("filas") or [])


def extract_openings_schedule(
    image_paths: list[str | Path],
    *,
    cache_dir: Path | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Run vision over plan pages and merge door/window schedule rows."""
    if not is_enabled() or OpenAI is None:
        return {}
    api_key = _resolve_openai_key()
    if not api_key:
        logger.info("openings_schedule: no OpenAI key — skipping")
        return {}
    paths = [Path(p) for p in (image_paths or []) if Path(p).exists()][: _max_pages()]
    if not paths:
        return {}

    resolved_model = model or _model()
    client = OpenAI(api_key=api_key)

    all_rows: list[dict[str, Any]] = []
    pages_with_schedule = 0
    for path in paths:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception:
            continue
        rows: list[dict[str, Any]] | None = None
        cache_file = _cache_path(Path(cache_dir), digest, resolved_model) if cache_dir else None
        if cache_file and cache_file.exists():
            try:
                rows = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                rows = None
        if rows is None:
            try:
                rows = _parse_one(client, path, resolved_model)
            except Exception:
                logger.warning("openings_schedule: failed on %s", path.name, exc_info=True)
                rows = []
            if cache_file is not None:
                try:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    logger.warning("openings_schedule: could not write cache", exc_info=True)
        if rows:
            pages_with_schedule += 1
            for r in rows:
                r["source_page"] = path.name
            all_rows.extend(rows)

    logger.info(
        "openings_schedule: %d rows from %d/%d pages",
        len(all_rows), pages_with_schedule, len(paths),
    )
    return {"filas": all_rows, "pages_with_schedule": pages_with_schedule}
