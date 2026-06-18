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
                    "description": "Una fila por elemento del cuadro estructural. Vacio si la pagina no tiene cuadro.",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "mark", "element", "section", "main_bars",
                            "stirrups", "fc", "count", "length_m",
                        ],
                        "properties": {
                            "mark": {"type": "string", "description": "Marca del elemento (C1, V2, Z3, ...)."},
                            "element": {
                                "type": "string",
                                "enum": ["columna", "viga", "zapata", "muro", "losa", "otro"],
                                "description": "Tipo de elemento estructural.",
                            },
                            "section": {"type": ["string", "null"], "description": "Seccion p.ej. '0.30x0.60' o diametro."},
                            "main_bars": {"type": ["string", "null"], "description": "Acero principal p.ej. '8#6'."},
                            "stirrups": {"type": ["string", "null"], "description": "Estribos p.ej. '#3@0.15'."},
                            "fc": {"type": ["integer", "null"], "description": "f'c en kg/cm2 si aparece."},
                            "count": {"type": ["integer", "null"], "description": "Cantidad de elementos de esta marca."},
                            "length_m": {"type": ["number", "null"], "description": "Longitud/altura en metros si aparece."},
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
    system = (
        "Eres un ingeniero estructural. Te paso la imagen de una lamina de planos. "
        "Si contiene un CUADRO de columnas, vigas o zapatas, extrae cada fila con su "
        "marca, seccion, acero principal, estribos, f'c, cantidad y longitud. Usa null "
        "donde el dato no aparezca. Si la lamina NO tiene cuadro estructural, devuelve "
        "filas vacio. No inventes."
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extrae el cuadro estructural de esta lamina."},
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
