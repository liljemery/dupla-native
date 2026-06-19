"""
(c) Parser de CUADROS estructurales (columnas / vigas / zapatas).

El cuadro de columnas/vigas/zapatas es la AUTORIDAD para seccion, armado y f'c.
En vez de adivinar el acero, lo leemos del despiece. Este modulo corre vision con
salida estructurada estricta sobre las imagenes renderizadas del plano y devuelve
filas tipadas:

    {"filas": [
        {"mark":"C1","element":"columna","section":"0.30x0.60",
         "main_bars":"8#6","stirrups":"#3@0.15","fc":280,"count":12,"length_m":3.0},
        ...
    ]}

De ahi el acero se calcula del despiece (main_bars + stirrups), que es la mayor
ganancia de precision estructural.

Es OPCIONAL y se controla con DUPLA_STRUCTURAL_SCHEDULE (default off) porque corre
vision sobre paginas y tiene costo. Degrada con gracia: sin key / sin imagenes /
si falla -> {}. Cachea por hash del contenido de cada imagen + modelo.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("dupla.structural_schedule")

try:  # optional at runtime
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


_SYSTEM_PROMPT = """\
Ingeniero estructural senior (Republica Dominicana).
Invocacion: tool structural_schedule sobre la lamina adjunta (imagen).

Objetivo: localizar el CUADRO DE COLUMNAS, VIGAS y/o ZAPATAS (tabla con marcas) y devolver una fila por marca.

Reglas:
- Solo filas que aparezcan en el cuadro. No infieras desde simbologia del plano ni cotas sueltas.
- Sin cuadro estructural en la lamina -> filas=[].
- mark: copia literal (C1, C-01, V2, Z3, M1).
- element: columna|viga|zapata|muro|losa|otro segun la fila/seccion del cuadro.
- section: literal del cuadro (0.30x0.60, 40x40, diametro). Formato ancho x alto en metros.
- main_bars: notacion literal del acero principal (8#6, 4#8, 12Ø12, 6 varillas #4). null si vacio.
- stirrups: notacion literal de estribos (#3@0.15, #4@0.10, est #2 @ 0.20). null si vacio.
- fc: f'c entero en kg/cm2 si aparece (210, 280, 350). null si no aparece.
- count: cantidad entera de elementos de esa marca. null si no aparece.
- length_m: longitud o altura en METROS (3.0, 3.50). Convierte cm del cuadro (350 cm -> 3.50).
- null solo si la columna existe y la celda esta vacia, es "-" o "N/A".
- "VER DETALLE" / "VER PLANO": null en ese campo.
- Ignora planta dibujada, leyenda general, membrete, cuadros de acabados/aperturas.

Si hay cuadros separados (columnas, vigas, zapatas) en la misma lamina, une todas las filas.\
"""


def is_enabled() -> bool:
    return (os.getenv("DUPLA_STRUCTURAL_SCHEDULE") or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_schema() -> dict[str, Any]:
    return {
        "name": "structural_schedule",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["filas"],
            "properties": {
                "filas": {
                    "type": "array",
                    "description": (
                        "Filas del cuadro estructural unicamente. "
                        "Vacio si la lamina no contiene cuadro."
                    ),
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "mark", "element", "section", "main_bars",
                            "stirrups", "fc", "count", "length_m",
                        ],
                        "properties": {
                            "mark": {
                                "type": "string",
                                "description": "Marca literal del cuadro (C1, V2, Z3, M1).",
                            },
                            "element": {
                                "type": "string",
                                "enum": ["columna", "viga", "zapata", "muro", "losa", "otro"],
                                "description": "Tipo de elemento segun la fila del cuadro.",
                            },
                            "section": {
                                "type": ["string", "null"],
                                "description": "Seccion literal (0.30x0.60, 40x40). null si vacio.",
                            },
                            "main_bars": {
                                "type": ["string", "null"],
                                "description": "Acero principal literal (8#6, 4#8, 12Ø12). null si vacio.",
                            },
                            "stirrups": {
                                "type": ["string", "null"],
                                "description": "Estribos literales (#3@0.15, #4@0.10). null si vacio.",
                            },
                            "fc": {
                                "type": ["integer", "null"],
                                "description": "f'c en kg/cm2 (210, 280, 350). null si no aparece.",
                            },
                            "count": {
                                "type": ["integer", "null"],
                                "description": "Cantidad de elementos de esta marca. null si no aparece.",
                            },
                            "length_m": {
                                "type": ["number", "null"],
                                "description": "Longitud/altura en metros (convertir cm). null si no aparece.",
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
        (os.getenv("DUPLA_STRUCTURAL_SCHEDULE_MODEL") or "").strip()
        or (os.getenv("OPENAI_MODEL") or "").strip()
        or "gpt-4o-mini"
    )


def _max_pages() -> int:
    raw = (os.getenv("DUPLA_STRUCTURAL_SCHEDULE_MAX_PAGES") or "6").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 6


def _encode(image_path: Path) -> str:
    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


def _cache_path(cache_dir: Path, image_bytes_digest: str, model: str) -> Path:
    digest = hashlib.sha256((model + "\n" + image_bytes_digest).encode("utf-8")).hexdigest()[:16]
    return cache_dir / "structural_schedule" / f"sched_{digest}.json"


def _parse_one(client: "OpenAI", image_path: Path, model: str) -> list[dict[str, Any]]:
    b64 = _encode(image_path)
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


def extract_structural_schedule(
    image_paths: list[str | Path],
    *,
    cache_dir: Path | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Run vision over plan pages and merge structural-schedule rows.

    Returns {"filas": [...], "pages_with_schedule": n}. {} when disabled/no key.
    """
    if not is_enabled():
        return {}
    if OpenAI is None:
        return {}
    api_key = _resolve_openai_key()
    if not api_key:
        logger.info("structural_schedule: no OpenAI key — skipping")
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
                logger.warning("structural_schedule: failed on %s", path.name, exc_info=True)
                rows = []
            if cache_file is not None:
                try:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    logger.warning("structural_schedule: could not write cache", exc_info=True)
        if rows:
            pages_with_schedule += 1
            for r in rows:
                r["source_page"] = path.name
            all_rows.extend(rows)

    logger.info(
        "structural_schedule: %d rows from %d/%d pages",
        len(all_rows), pages_with_schedule, len(paths),
    )
    return {"filas": all_rows, "pages_with_schedule": pages_with_schedule}
