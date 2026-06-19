"""Clasificación GA-FO-01 vía OpenAI (contexto APS + catálogo + fallback PDF/nombre)."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Optional

from openai import AsyncOpenAI
from pypdf import PdfReader

from app.config import Settings
from app.domain.ga_fo_01_arquitectura import expected_ga_fo_item_ids

logger = logging.getLogger(__name__)

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "domain" / "ga_fo_01_catalog_for_prompt.json"

GaFoMatch = tuple[str, float, str]  # item_id, confidence, reason

_SYSTEM_MULTI = """Eres experto en documentación de obra y pliego GA-FO-01 Arquitectura (República Dominicana).
Debes identificar TODOS los documentos del catálogo que correspondan al archivo subido (puede haber varios en distintas secciones).
Responde SOLO con un JSON válido:
- matches: array de objetos { "item_id": string (id exacto del catálogo), "confidence": 0-1, "reason_short": string }.
Incluye cada ítem con correspondencia razonable (confidence >= 0.55). Si no hay ninguno, devuelve matches: []."""

_DISCIPLINE_GA_FO_SECTION: dict[str, str] = {
    "arquitectura": "3 — Planos y documentación arquitectónica",
    "estructura": "4.1 — Estructural",
    "electrica": "4.2 — Instalaciones eléctricas",
    "plomeria": "4.3 — Instalaciones sanitarias e hidráulicas",
    "mecanica": "4.4 — Climatización y extracción",
}

_FILENAME_SECTION_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("licencia", "permiso", "permisolog", "no objecion", "no objeción", "registro de impacto"), "2 — Permisologías"),
    (("contrato", "acuerdo", "fianza"), "5 — Contratos"),
    (("poliza", "póliza", "seguro"), "7 — Pólizas"),
)


def _fold_text(value: str) -> str:
    text = (value or "").strip().lower()
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _name_tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _fold_text(name)) if len(t) >= 3]


def _load_catalog_items() -> list[dict[str, str]]:
    if not _CATALOG_PATH.is_file():
        return []
    raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        iid = row.get("id")
        if not isinstance(iid, str):
            continue
        nombre = row.get("nombre") if isinstance(row.get("nombre"), str) else ""
        sec = row.get("seccion") if isinstance(row.get("seccion"), str) else ""
        out.append({"id": iid, "nombre": nombre[:400], "seccion": sec[:200]})
    return out


def _is_drawings_document_item(nombre: str, discipline: str) -> bool:
    if discipline == "arquitectura":
        return any(
            k in nombre
            for k in (
                "plano",
                "planta",
                "alzado",
                "fachada",
                "corte",
                "detalle",
                "conjunto",
                "memoria",
                "localiz",
                "paisaj",
                "dossier",
                "listado",
            )
        )
    return any(k in nombre for k in ("plano", "planta", "memoria", "detalle", "especific", "cálculo", "calculo"))


def rule_based_ga_fo_matches(
    *,
    original_name: str,
    discipline: str | None = None,
    mime: str | None = None,
) -> list[GaFoMatch]:
    """Deterministic GA-FO matches from filename, MIME and discipline."""
    allowed = expected_ga_fo_item_ids()
    items = _load_catalog_items()
    if not items:
        return []

    name = _fold_text(original_name)
    ext = Path(original_name).suffix.lower()
    is_doc = ext in (".dwg", ".dxf", ".pdf") or (mime or "").lower().endswith("pdf")
    matched: dict[str, GaFoMatch] = {}

    def add(iid: str, conf: float, reason: str) -> None:
        if iid not in allowed:
            return
        prev = matched.get(iid)
        if prev is None or conf > prev[1]:
            matched[iid] = (iid, conf, reason)

    tokens = _name_tokens(original_name)
    for item in items:
        iid = item["id"]
        nombre = _fold_text(item["nombre"])
        for token in tokens:
            if len(token) >= 4 and token in nombre:
                add(iid, 0.62, f"nombre:{token}")

    for keywords, section_prefix in _FILENAME_SECTION_HINTS:
        if any(kw in name for kw in keywords):
            for item in items:
                if item["seccion"].startswith(section_prefix):
                    add(item["id"], 0.58, f"seccion:{section_prefix[:20]}")

    disc = _fold_text(discipline or "")
    section_prefix = _DISCIPLINE_GA_FO_SECTION.get(disc)
    if section_prefix and is_doc:
        for item in items:
            if not item["seccion"].startswith(section_prefix):
                continue
            if _is_drawings_document_item(_fold_text(item["nombre"]), disc):
                add(item["id"], 0.55, f"disciplina:{disc}")

    if "plan" in name or "plano" in name or "planta" in name:
        for item in items:
            if item["seccion"].startswith("3 — Planos"):
                nombre = _fold_text(item["nombre"])
                if any(k in nombre for k in ("plano", "planta")):
                    add(item["id"], 0.6, "nombre:planos")

    return list(matched.values())


def _merge_ga_fo_match_lists(*groups: list[GaFoMatch], min_confidence: float) -> list[GaFoMatch]:
    merged: dict[str, GaFoMatch] = {}
    for group in groups:
        for item_id, conf, reason in group:
            if conf < min_confidence:
                continue
            prev = merged.get(item_id)
            if prev is None or conf > prev[1]:
                merged[item_id] = (item_id, conf, reason)
    return list(merged.values())


def extract_pdf_text_snippet(file_path: Path, max_chars: int = 8000) -> str:
    if file_path.suffix.lower() != ".pdf" or not file_path.is_file():
        return ""
    try:
        reader = PdfReader(str(file_path))
        parts: list[str] = []
        total = 0
        for page in reader.pages[:8]:
            t = page.extract_text() or ""
            t = t.strip()
            if not t:
                continue
            parts.append(t)
            total += len(t)
            if total >= max_chars:
                break
        out = "\n\n".join(parts)
        return out[:max_chars]
    except Exception as exc:
        logger.debug("PDF snippet skip: %s", exc)
        return ""


async def _openai_ga_fo_matches(
    settings: Settings,
    *,
    original_name: str,
    mime: Optional[str],
    file_size: int,
    aps_analysis: str,
    pdf_snippet: str,
) -> list[GaFoMatch]:
    key = (settings.openai_api_key or "").strip()
    if not key:
        return []
    items = _load_catalog_items()
    if not items:
        return []
    allowed = expected_ga_fo_item_ids()
    client = AsyncOpenAI(api_key=key)
    cap = settings.ga_fo_aps_context_max_chars
    user_blocks: dict[str, Any] = {
        "archivo": {"nombre": original_name, "mime": mime or "", "tamaño_bytes": file_size},
        "aps_analysis": aps_analysis[:cap] if len(aps_analysis) > cap else aps_analysis,
        "texto_pdf_local": pdf_snippet[:8000] if pdf_snippet else "",
        "catalogo_ga_fo": items,
    }
    user_msg = json.dumps(user_blocks, ensure_ascii=False)
    try:
        completion = await client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_MULTI},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
        )
    except Exception as exc:
        logger.warning("OpenAI GA-FO classify: %s", exc)
        return []

    raw = completion.choices[0].message.content
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    out: list[GaFoMatch] = []
    matches = data.get("matches")
    if not isinstance(matches, list):
        # ponytail: backward compat if model returns single item_id
        single = data.get("item_id")
        if isinstance(single, str) and single.strip():
            matches = [{"item_id": single.strip(), "confidence": data.get("confidence", 0), "reason_short": data.get("reason_short", "")}]
        else:
            return []

    for row in matches:
        if not isinstance(row, dict):
            continue
        item_raw = row.get("item_id")
        if not isinstance(item_raw, str) or not item_raw.strip():
            continue
        item_id = item_raw.strip()
        if item_id not in allowed:
            continue
        try:
            conf = float(row.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        reason = str(row.get("reason_short") or "").strip() or "openai"
        out.append((item_id, conf, reason))
    return out


async def classify_ga_fo_matches(
    settings: Settings,
    *,
    original_name: str,
    mime: Optional[str],
    file_size: int,
    aps_analysis: str,
    pdf_snippet: str,
    discipline: str | None = None,
) -> list[GaFoMatch]:
    """All GA-FO catalog items that match this file (rules + OpenAI)."""
    rules = rule_based_ga_fo_matches(original_name=original_name, discipline=discipline, mime=mime)
    ai = await _openai_ga_fo_matches(
        settings,
        original_name=original_name,
        mime=mime,
        file_size=file_size,
        aps_analysis=aps_analysis,
        pdf_snippet=pdf_snippet,
    )
    return _merge_ga_fo_match_lists(
        rules,
        ai,
        min_confidence=settings.ga_fo_classification_confidence_min,
    )


async def classify_ga_fo_item(
    settings: Settings,
    *,
    original_name: str,
    mime: Optional[str],
    file_size: int,
    aps_analysis: str,
    pdf_snippet: str,
    discipline: str | None = None,
) -> tuple[Optional[str], float, str]:
    """Devuelve el mejor match (compat legacy)."""
    matches = await classify_ga_fo_matches(
        settings,
        original_name=original_name,
        mime=mime,
        file_size=file_size,
        aps_analysis=aps_analysis,
        pdf_snippet=pdf_snippet,
        discipline=discipline,
    )
    if not matches:
        return None, 0.0, "sin_item"
    item_id, conf, reason = max(matches, key=lambda row: row[1])
    return item_id, conf, reason


if __name__ == "__main__":
    sample = rule_based_ga_fo_matches(
        original_name="LAS NASAS Plans ARQ Nov 21.dwg",
        discipline="arquitectura",
    )
    assert sample, "expected rule matches for ARQ plan"
    print(f"ga_fo rule self-check ok ({len(sample)} matches)")
