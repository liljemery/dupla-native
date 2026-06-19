"""
GPT-4o partida generator: creates project-specific budget line descriptions
from quantity takeoffs.

BC3 and PRES are used as few-shot formatting references only — not as a lookup
catalog. Every partida description is specific to this project.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from budget.provenance import format_provenance_suffix, source_file_from_takeoff
from core.api_key_manager import APIKeyManager
from core.schemas import QuantityTakeoff, QuantityTrace
from knowledge.training_data import TrainingPair

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger("dupla.partida_generator")

try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        logger.warning("%s=%r is invalid; using %d", name, raw, default)
        return default


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        logger.warning("%s=%r is invalid; using %.2f", name, raw, default)
        return default


# ---------------------------------------------------------------------------
# Chapter catalog — 24 chapters across 4 disciplines
# Maps chapter_code -> (chapter_name, discipline)
# ---------------------------------------------------------------------------

CHAPTER_CATALOG: dict[str, tuple[str, str]] = {
    "01": ("MOVIMIENTO DE TIERRAS Y FUNDACIONES", "estructural"),
    "02": ("HORMIGON ARMADO - COLUMNAS Y VIGAS", "estructural"),
    "03": ("HORMIGON ARMADO - LOSAS Y ENTREPISO", "estructural"),
    "04": ("ACERO DE REFUERZO", "estructural"),
    "05": ("ENCOFRADOS", "estructural"),
    "06": ("MUROS Y DIVISIONES", "arquitectura"),
    "07": ("PANETE Y REVESTIMIENTO DE MUROS", "arquitectura"),
    "08": ("PISOS Y CERAMICA", "arquitectura"),
    "09": ("CIELOS Y TECHOS", "arquitectura"),
    "10": ("PUERTAS Y MARCOS", "arquitectura"),
    "11": ("VENTANAS Y FACHADA", "arquitectura"),
    "12": ("PINTURA INTERIOR Y EXTERIOR", "arquitectura"),
    "13": ("IMPERMEABILIZACION", "arquitectura"),
    "14": ("ESCALERAS Y BARANDAS", "arquitectura"),
    "15": ("GABINETES Y COCINAS", "arquitectura"),
    "16": ("OBRAS EXTERIORES Y PAISAJISMO", "arquitectura"),
    "17": ("INSTALACIONES SANITARIAS - AGUA FRIA", "sanitario"),
    "18": ("INSTALACIONES SANITARIAS - AGUAS NEGRAS", "sanitario"),
    "19": ("PIEZAS SANITARIAS Y ACCESORIOS", "sanitario"),
    "20": ("CISTERNA Y SISTEMA DE BOMBEO", "sanitario"),
    "21": ("INSTALACIONES ELECTRICAS - DISTRIBUCION", "electrico"),
    "22": ("TABLEROS Y PROTECCIONES", "electrico"),
    "23": ("LUMINARIAS Y TOMACORRIENTES", "electrico"),
    "24": ("GASTOS GENERALES E INDIRECTOS", "arquitectura"),
}

# item_type -> default chapter_code
_ITEM_TYPE_TO_CHAPTER: dict[str, str] = {
    # Estructural — fundaciones
    "footing_concrete_volume": "01",
    "footing_volume": "01",
    "footing_area": "01",
    "footing_perimeter": "01",
    "excavation_volume": "01",
    # Estructural — columnas/vigas
    "column_concrete_volume": "02",
    "column_volume": "02",
    "beam_concrete_volume": "02",
    "beam_volume": "02",
    "structural_concrete_volume": "02",
    "structural_volume": "02",
    "structural_count": "02",
    "structural_area": "02",
    "structural_length": "02",
    # Estructural — losas
    "slab_concrete_volume": "03",
    "slab_volume": "03",
    "slab_area": "03",
    # Acero de refuerzo
    "footing_reinforcement_kg": "04",
    "beam_reinforcement_kg": "04",
    "column_reinforcement_kg": "04",
    "slab_reinforcement_kg": "04",
    "reinforcement_kg": "04",
    # Encofrado
    "footing_formwork_area_hint": "05",
    "beam_formwork_area_hint": "05",
    "column_formwork_area_hint": "05",
    "slab_formwork_area_hint": "05",
    "formwork_area": "05",
    # Arquitectura — muros
    "wall_net_area": "06",
    "wall_gross_area": "06",
    "wall_volume": "06",
    "wall_length": "06",
    # Arquitectura — panete/acabados muros
    "wall_finish_plaster": "07",
    "wall_finish_tile": "07",
    "wall_finish_stucco": "07",
    # Arquitectura — pisos
    "floor_area": "08",
    "floor_finish": "08",
    "floor_tile_area": "08",
    "floor_epoxy_area": "08",
    # Arquitectura — cielos
    "ceiling_area": "09",
    "ceiling_finish": "09",
    # Arquitectura — puertas
    "door_count": "10",
    "door_leaf_wood_count": "10",
    "door_frame_count": "10",
    # Arquitectura — ventanas
    "window_count": "11",
    "window_frame_count": "11",
    "window_glazing_area": "11",
    "window_area": "11",
    # Arquitectura — pintura
    "wall_finish_paint": "12",
    "ceiling_finish_paint": "12",
    "paint_area": "12",
    # Arquitectura — impermeabilización
    "floor_waterproofing": "13",
    "wall_waterproofing": "13",
    "waterproofing_area": "13",
    # Arquitectura — escaleras
    "stair_count": "14",
    "stair_area": "14",
    "stair_railing_length": "14",
    # Arquitectura — gabinetes
    "kitchen_count": "15",
    "kitchen_area": "15",
    "cabinet_count": "15",
    # Sanitario — piezas sanitarias
    "wet_area_fixture_count": "19",
    "fixture_count_plumbing": "19",
    # Eléctrico
    "fixture_count_electrical": "23",
}

# Prefix fallback table (checked in order when item_type not in _ITEM_TYPE_TO_CHAPTER)
_PREFIX_TABLE: list[tuple[str, str]] = [
    ("footing_", "01"),
    ("beam_", "02"),
    ("column_", "02"),
    ("slab_", "03"),
    ("structural_", "02"),
    ("reinforcement_", "04"),
    ("formwork_", "05"),
    ("wall_finish_paint", "12"),
    ("wall_finish_", "07"),
    ("wall_", "06"),
    ("floor_waterproof", "13"),
    ("floor_", "08"),
    ("ceiling_finish_paint", "12"),
    ("ceiling_", "09"),
    ("door_", "10"),
    ("window_", "11"),
    ("paint_", "12"),
    ("waterproof_", "13"),
    ("stair_", "14"),
    ("kitchen_", "15"),
    ("cabinet_", "15"),
    ("wet_area_", "19"),
]

BATCH_SIZE = _env_int("DUPLA_PARTIDA_BATCH_SIZE", 20)
OPENAI_CONCURRENCY = 30
OPENAI_MAX_RETRIES = _env_int("DUPLA_OPENAI_MAX_RETRIES", 4)
OPENAI_RETRY_BASE_SECONDS = _env_float("DUPLA_OPENAI_RETRY_BASE_SECONDS", 0.75)
_MODEL = os.getenv("DUPLA_PARTIDA_MODEL", "gpt-4o")
_TEMPERATURE = 0.2

# Bump when system prompt or batch format changes; invalidates cache.
PARTIDA_PROMPT_VERSION = "v4-provenance"

_SYSTEM_PROMPT = """\
Eres un presupuestista dominicano senior especializado en proyectos residenciales
y comerciales en República Dominicana (zona Punta Cana).

Tu tarea: dado un lote de mediciones (takeoffs) de un proyecto de construcción,
genera una partida presupuestaria específica y detallada para CADA medición.

REGLAS ABSOLUTAS:
1. Describe el trabajo REAL del proyecto, no categorías genéricas.
   MAL: "Hormigon armado"
   BIEN: "Hormigón f'c=280 en viga V1 0.25×0.45 m · N2 · ES 01 General Details.dwg"
2. La descripcion debe incluir especificaciones técnicas cuando el takeoff las
   proporciona (dimensiones, resistencia del concreto, tipo de bloque, acabado, etc.).
3. Mantén la descripción concisa (≤ 90 caracteres de trabajo) e incluye origen al final
   con separador " · ": nivel (si aplica) y nombre del plano (source_file / provenance_hint).
4. La unidad DEBE coincidir exactamente con la unidad del takeoff de entrada.
5. El chapter_code y chapter_name deben tomarse del capitulo asignado al lote.
6. El partida_code se forma como: {chapter_code}.{orden_dentro_capitulo:03d}
7. Devuelve SOLO un JSON object con la forma {"items":[...]}, sin texto adicional.
8. El campo source_takeoff_key debe ser el item_key exacto del takeoff de entrada.
9. Genera EXACTAMENTE una partida por takeoff recibido, usando el mismo orden.
10. NUNCA uses slugs CAD internos (json-wall-*, capas crudas como a-wall) en la descripción.\
"""

_PARTIDA_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "dupla_partida_batch",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["items"],
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "chapter_code",
                            "chapter_name",
                            "discipline",
                            "partida_code",
                            "partida_description",
                            "unit",
                            "quantity",
                            "source_takeoff_key",
                        ],
                        "properties": {
                            "chapter_code": {
                                "type": "string",
                                "description": "Two-digit budget chapter code.",
                            },
                            "chapter_name": {
                                "type": "string",
                                "description": "Budget chapter display name.",
                            },
                            "discipline": {
                                "type": "string",
                                "enum": ["arquitectura", "estructural", "sanitario", "electrico"],
                            },
                            "partida_code": {
                                "type": "string",
                                "description": "Code in format XX.NNN.",
                            },
                            "partida_description": {
                                "type": "string",
                                "description": "Project-specific budget line description.",
                            },
                            "unit": {
                                "type": "string",
                                "description": "Unit copied exactly from the input takeoff.",
                            },
                            "quantity": {
                                "type": "number",
                                "description": "Quantity copied from the input takeoff.",
                            },
                            "source_takeoff_key": {
                                "type": "string",
                                "description": "Exact key copied from the input takeoff.",
                            },
                        },
                    },
                },
            },
        },
    },
}


def _infer_discipline(takeoff: QuantityTakeoff) -> str:
    """Return one of: arquitectura | estructural | sanitario | electrico."""
    stamped = str(takeoff.trace.metadata.get("source_discipline") or "").strip()
    _alias: dict[str, str] = {
        "arquitectonica": "arquitectura",
        "arquitectura": "arquitectura",
        "estructural": "estructural",
        "estructura": "estructural",
        "electrica": "electrico",
        "electrico": "electrico",
        "sanitaria": "sanitario",
        "sanitario": "sanitario",
    }
    if stamped in _alias:
        return _alias[stamped]

    it = takeoff.item_type.lower()
    if it.startswith(("beam_", "column_", "slab_", "footing_", "structural_", "reinforcement_", "formwork_")):
        return "estructural"
    if it == "wet_area_fixture_count" or "plumbing" in str(takeoff.inputs.get("discipline") or "").lower():
        return "sanitario"
    if it == "fixture_count":
        disc = str(takeoff.inputs.get("discipline") or "").lower()
        if disc in ("plumbing", "sanitaria", "sanitario"):
            return "sanitario"
        return "electrico"
    return "arquitectura"


def _assign_chapter(takeoff: QuantityTakeoff) -> str:
    """Return chapter_code from the 24-chapter catalog."""
    it = takeoff.item_type.lower()

    # Special branching for fixture_count based on inputs.discipline
    if it == "fixture_count":
        disc = str(takeoff.inputs.get("discipline") or "").lower()
        if disc in ("plumbing", "sanitaria", "sanitario"):
            return "19"
        return "23"

    if it in _ITEM_TYPE_TO_CHAPTER:
        return _ITEM_TYPE_TO_CHAPTER[it]

    for prefix, ch in _PREFIX_TABLE:
        if it.startswith(prefix):
            return ch

    return "24"  # catch-all: gastos generales


def _build_few_shot_block(
    training_pairs: list[TrainingPair],
    discipline: str,
    max_examples: int = 6,
) -> str:
    """Pick real PRES examples matching the discipline and format as few-shot text."""
    _disc_kw: dict[str, set[str]] = {
        "estructural": {"hormig", "viga", "colum", "losa", "zapata", "acero", "encof", "fundam"},
        "arquitectura": {"muro", "panete", "piso", "puerta", "pintura", "ventana", "bloque", "cielo", "pared"},
        "sanitario": {"sanitar", "tuberia", "inodor", "lavam", "ducha", "drenaj", "agua", "plomer"},
        "electrico": {"electr", "tomacorr", "interrup", "luminaria", "panel", "switch", "circuito"},
    }
    keywords = _disc_kw.get(discipline, set())

    def _matches(pair: TrainingPair) -> bool:
        desc = pair.output_description.lower()
        return any(kw in desc for kw in keywords)

    filtered = [p for p in training_pairs if _matches(p)][:max_examples]
    if not filtered:
        filtered = training_pairs[:max_examples]

    if not filtered:
        return ""

    lines = ["EJEMPLOS DE PARTIDAS REALES (solo para formato y nivel de detalle):"]
    for p in filtered:
        lines.append(
            f'- "{p.output_description}" | Ud: {p.output_unit} | Precio ref: RD${p.output_price:.0f}'
        )
    return "\n".join(lines)


def _extract_json_list(text: str) -> list[dict[str, Any]]:
    """Extract a JSON array from GPT-4o text output (copied from classifier_agent)."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "items" in parsed:
            return list(parsed["items"])
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            cleaned = re.sub(r",\s*([}\]])", r"\1", text[start : end + 1])
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

    return []


def _fallback_partida_description(takeoff: QuantityTakeoff, chapter_name: str) -> str:
    desc = str(takeoff.inputs.get("takeoff_description") or "").strip()
    if desc:
        return desc[:800]
    return f"{chapter_name.title()} - {takeoff.item_type.replace('_', ' ')}"


def _normalize_generated_partidas(
    partidas: list[dict[str, Any]],
    takeoffs: list[QuantityTakeoff],
    *,
    chapter_code: str,
    chapter_name: str,
    discipline: str,
    partida_offset: int,
) -> list[dict[str, Any]]:
    """Return exactly one validated partida per takeoff, in input order."""
    by_key: dict[str, dict[str, Any]] = {}
    for partida in partidas:
        source_key = str(partida.get("source_takeoff_key") or "").strip()
        if source_key and source_key not in by_key:
            by_key[source_key] = partida

    normalized: list[dict[str, Any]] = []
    for idx, takeoff in enumerate(takeoffs, start=1):
        code = f"{chapter_code}.{partida_offset + idx:03d}"
        partida = dict(by_key.get(takeoff.item_key) or {})
        normalized.append(
            {
                "chapter_code": str(partida.get("chapter_code") or chapter_code),
                "chapter_name": str(partida.get("chapter_name") or chapter_name),
                "discipline": str(partida.get("discipline") or discipline),
                "partida_code": str(partida.get("partida_code") or code),
                "partida_description": str(
                    partida.get("partida_description")
                    or _fallback_partida_description(takeoff, chapter_name)
                ),
                "unit": str(takeoff.unit),
                "quantity": float(takeoff.quantity),
                "source_takeoff_key": takeoff.item_key,
            }
        )
    return normalized


class PartidaGenerator:
    """
    Generates project-specific budget partidas from quantity takeoffs using GPT-4o.

    Groups takeoffs by chapter, batches them, calls GPT-4o once per batch, and
    returns a flat list of partida dicts that the adapter converts to BudgetCandidates.
    """

    def __init__(self) -> None:
        if not HAS_OPENAI:
            raise ImportError("openai package is required for PartidaGenerator")
        self._key_manager = APIKeyManager()
        self._clients: dict[str, AsyncOpenAI] = {}
        self._semaphore = asyncio.Semaphore(OPENAI_CONCURRENCY)
        logger.info(
            "PartidaGenerator initialized: model=%s batch_size=%d concurrency=%d keys=%d",
            _MODEL,
            BATCH_SIZE,
            OPENAI_CONCURRENCY,
            self._key_manager.key_count,
        )

    def _client_for_next_key(self) -> "AsyncOpenAI":
        api_key = self._key_manager.next_key()
        client = self._clients.get(api_key)
        if client is None:
            client = AsyncOpenAI(api_key=api_key)
            self._clients[api_key] = client
        return client

    def _client_and_key_for_next_key(self) -> tuple["AsyncOpenAI", str]:
        api_key = self._key_manager.next_key()
        client = self._clients.get(api_key)
        if client is None:
            client = AsyncOpenAI(api_key=api_key)
            self._clients[api_key] = client
        return client, api_key

    async def generate(
        self,
        takeoffs: list[QuantityTakeoff],
        training_pairs: list[TrainingPair] | None = None,
        bc3_catalog: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Main entry point.

        Groups takeoffs by chapter_code, batches at BATCH_SIZE, calls GPT-4o
        per batch, and returns a flat list of generated partida dicts.

        pres_reference_line takeoffs are skipped (they already have descriptions).
        """
        non_pres_raw = [t for t in takeoffs if t.item_type != "pres_reference_line"]
        seen_item_keys: set[str] = set()
        non_pres: list[QuantityTakeoff] = []
        duplicate_count = 0
        for takeoff in non_pres_raw:
            if takeoff.item_key in seen_item_keys:
                duplicate_count += 1
                continue
            seen_item_keys.add(takeoff.item_key)
            non_pres.append(takeoff)

        if duplicate_count:
            logger.warning(
                "PartidaGenerator collapsed %d duplicate takeoffs by item_key (%d -> %d)",
                duplicate_count,
                len(non_pres_raw),
                len(non_pres),
            )
        if not non_pres:
            return []

        # Group by chapter_code
        groups: dict[str, list[QuantityTakeoff]] = {}
        for t in non_pres:
            ch = _assign_chapter(t)
            groups.setdefault(ch, []).append(t)

        results: list[dict[str, Any]] = []
        chapter_offsets: dict[str, int] = {}

        tasks = []
        for chapter_code in sorted(groups.keys()):
            chapter_takeoffs = groups[chapter_code]
            chapter_name, discipline = CHAPTER_CATALOG.get(
                chapter_code, ("PARTIDAS GENERALES", "arquitectura")
            )
            few_shot = _build_few_shot_block(training_pairs or [], discipline)

            for batch_start in range(0, len(chapter_takeoffs), BATCH_SIZE):
                batch = chapter_takeoffs[batch_start : batch_start + BATCH_SIZE]
                offset = chapter_offsets.get(chapter_code, 0)
                
                tasks.append(
                    self._generate_batch(
                        batch,
                        chapter_code=chapter_code,
                        chapter_name=chapter_name,
                        discipline=discipline,
                        few_shot_block=few_shot,
                        partida_offset=offset,
                    )
                )
                chapter_offsets[chapter_code] = offset + len(batch)

        if tasks:
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for partidas in batch_results:
                if isinstance(partidas, Exception):
                    logger.warning("PartidaGenerator batch task failed: %s", partidas)
                    continue
                results.extend(partidas)

        logger.info(
            "PartidaGenerator: %d takeoffs -> %d partidas generated",
            len(non_pres),
            len(results),
        )
        return results

    async def _create_structured_completion(
        self,
        *,
        messages: list[dict[str, str]],
        chapter_code: str,
        takeoff_count: int,
    ) -> str:
        retryable_statuses = {408, 409, 429, 500, 502, 503, 504}
        last_exc: Exception | None = None

        async with self._semaphore:
            for attempt in range(1, max(1, OPENAI_MAX_RETRIES) + 1):
                client, api_key = self._client_and_key_for_next_key()
                try:
                    resp = await client.chat.completions.create(
                        model=_MODEL,
                        max_tokens=4000,
                        temperature=_TEMPERATURE,
                        response_format=_PARTIDA_RESPONSE_FORMAT,
                        messages=messages,
                    )
                    return resp.choices[0].message.content or ""
                except Exception as exc:
                    last_exc = exc
                    status_code = getattr(exc, "status_code", None)
                    response = getattr(exc, "response", None)
                    if status_code is None and response is not None:
                        status_code = getattr(response, "status_code", None)

                    if status_code == 429:
                        self._key_manager.mark_rate_limited(api_key)

                    is_retryable = status_code in retryable_statuses or status_code is None
                    if attempt >= OPENAI_MAX_RETRIES or not is_retryable:
                        raise

                    delay = min(
                        20.0,
                        OPENAI_RETRY_BASE_SECONDS * (2 ** (attempt - 1)) + random.random(),
                    )
                    logger.warning(
                        "PartidaGenerator retry %d/%d in %.2fs "
                        "(chapter=%s takeoffs=%d status=%s)",
                        attempt,
                        OPENAI_MAX_RETRIES,
                        delay,
                        chapter_code,
                        takeoff_count,
                        status_code or "unknown",
                    )
                    await asyncio.sleep(delay)

        raise RuntimeError("PartidaGenerator structured completion failed") from last_exc

    async def _generate_batch(
        self,
        takeoffs: list[QuantityTakeoff],
        *,
        chapter_code: str,
        chapter_name: str,
        discipline: str,
        few_shot_block: str,
        partida_offset: int,
    ) -> list[dict[str, Any]]:
        """Single GPT-4o call for one batch within a chapter (cached)."""
        from core.stage_cache import (
            cache_get,
            cache_set,
            compose_key,
            sha256_json,
            _STATS,
        )
        import time

        takeoff_payload: list[dict[str, Any]] = []
        for t in takeoffs:
            item: dict[str, Any] = {
                "key": t.item_key,
                "type": t.item_type,
                "unit": t.unit,
                "qty": round(float(t.quantity), 3),
            }
            desc = str(t.inputs.get("takeoff_description") or "").strip()
            if desc:
                item["desc"] = desc[:800]
            level = str(t.level_id or "").strip()
            if level:
                item["level"] = level
            level_name = str(t.inputs.get("level_name") or "").strip()
            if level_name:
                item["level_name"] = level_name
            source_file = source_file_from_takeoff(t)
            if source_file:
                item["source_file"] = source_file
            layer = str(t.inputs.get("source_layer") or "").strip()
            if layer:
                item["layer"] = layer
            tags = t.inputs.get("context_tags")
            if isinstance(tags, list) and tags:
                item["tags"] = tags[:8]
            provenance_hint = format_provenance_suffix(t)
            if provenance_hint:
                item["provenance_hint"] = provenance_hint
            takeoff_payload.append(item)

        cache_key = compose_key(
            sha256_json({
                "takeoffs": takeoff_payload,
                "chapter": chapter_code,
                "few_shot": sha256_json(few_shot_block or "")[:16],
                "offset": partida_offset,
            }),
            _MODEL,
            PARTIDA_PROMPT_VERSION,
        )
        cached = cache_get("partida_generate_batch", cache_key)
        if cached is not None:
            logger.info(
                "[cache] HIT partida_generate_batch chapter=%s (%d takeoffs)",
                chapter_code, len(takeoffs),
            )
            return cached
        _STATS.bump("partida_generate_batch", misses=1)

        catalog_block = "\n".join(
            f"  {code}: {name} (disciplina: {disc})"
            for code, (name, disc) in CHAPTER_CATALOG.items()
        )

        start_num = partida_offset + 1
        user_prompt = (
            f"CAPITULO ASIGNADO: {chapter_code} - {chapter_name} (disciplina: {discipline})\n\n"
            f"CATALOGO DE CAPITULOS DISPONIBLES:\n{catalog_block}\n\n"
        )
        if few_shot_block:
            user_prompt += f"{few_shot_block}\n\n"

        user_prompt += (
            f"NUMERACION: los partida_code para este lote empiezan en "
            f"{chapter_code}.{start_num:03d}\n\n"
            f"TAKEOFFS A CONVERTIR EN PARTIDAS ({len(takeoffs)} items):\n"
            + json.dumps(takeoff_payload, ensure_ascii=False, indent=2)
            + "\n\nDevuelve SOLO un JSON object con la propiedad items. "
            "Formato de cada elemento:\n"
            '{"items":[{"chapter_code":"XX","chapter_name":"...","discipline":"...",'
            '"partida_code":"XX.NNN","partida_description":"...","unit":"...",'
            '"quantity":0.0,"source_takeoff_key":"..."}]}'
        )

        t0 = time.monotonic()
        try:
            raw = await self._create_structured_completion(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                chapter_code=chapter_code,
                takeoff_count=len(takeoffs),
            )
        except Exception:
            logger.warning(
                "PartidaGenerator batch failed (chapter=%s, %d takeoffs)",
                chapter_code,
                len(takeoffs),
                exc_info=True,
            )
            return []

        parsed_partidas = _extract_json_list(raw)
        if not parsed_partidas:
            logger.warning(
                "PartidaGenerator: empty JSON from GPT-4o for chapter %s. Raw response was: %s",
                chapter_code, raw
            )
        else:
            if len(parsed_partidas) != len(takeoffs):
                logger.warning(
                    "PartidaGenerator schema-valid response count mismatch "
                    "(chapter=%s expected=%d got=%d); normalizing",
                    chapter_code,
                    len(takeoffs),
                    len(parsed_partidas),
                )
            partidas = _normalize_generated_partidas(
                parsed_partidas,
                takeoffs,
                chapter_code=chapter_code,
                chapter_name=chapter_name,
                discipline=discipline,
                partida_offset=partida_offset,
            )
            _STATS.bump("partida_generate_batch", seconds_saved_estimate=time.monotonic() - t0)
            cache_set("partida_generate_batch", cache_key, partidas)
            return partidas
        return []
