"""Clasificación GA-FO-01 vía OpenAI (contexto APS + catálogo + fallback PDF/nombre)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from openai import AsyncOpenAI
from pypdf import PdfReader

from app.config import Settings
from app.domain.ga_fo_01_arquitectura import expected_ga_fo_item_ids

logger = logging.getLogger(__name__)

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "domain" / "ga_fo_01_catalog_for_prompt.json"

_SYSTEM = """Eres experto en documentación de obra y pliego GA-FO-01 Arquitectura (República Dominicana).
Debes asignar el archivo subido al documento del catálogo que mejor corresponda.
Responde SOLO con un JSON válido con las claves:
- item_id: string, uno de los ids del catálogo (exactamente igual).
- confidence: número entre 0 y 1.
- reason_short: una frase corta en español justificando la elección.
Si no hay correspondencia razonable, usa item_id null y confidence 0."""

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


async def classify_ga_fo_item(
    settings: Settings,
    *,
    original_name: str,
    mime: Optional[str],
    file_size: int,
    aps_analysis: str,
    pdf_snippet: str,
) -> tuple[Optional[str], float, str]:
    """
    Devuelve (item_id o None, confidence, reason).
    """
    key = (settings.openai_api_key or "").strip()
    if not key:
        return None, 0.0, "sin_openai"
    items = _load_catalog_items()
    if not items:
        return None, 0.0, "sin_catalogo"
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
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
        )
    except Exception as exc:
        logger.warning("OpenAI GA-FO classify: %s", exc)
        return None, 0.0, "openai_error"

    raw = completion.choices[0].message.content
    if not raw:
        return None, 0.0, "empty"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, 0.0, "json_invalid"
    item_raw = data.get("item_id")
    conf_raw = data.get("confidence", 0)
    reason = (data.get("reason_short") or "").strip()
    if item_raw is None or (isinstance(item_raw, str) and not item_raw.strip()):
        return None, 0.0, reason or "sin_item"
    if not isinstance(item_raw, str):
        return None, 0.0, reason
    item_id = item_raw.strip()
    if item_id not in allowed:
        return None, 0.0, reason or "id_invalido"
    try:
        conf = float(conf_raw)
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    if conf < settings.ga_fo_classification_confidence_min:
        return None, conf, reason or "baja_confianza"
    return item_id, conf, reason
