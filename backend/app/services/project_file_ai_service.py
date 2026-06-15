from __future__ import annotations

import json
from typing import Optional

from openai import AsyncOpenAI

from app.config import get_settings
from app.domain.file_discipline import FileDiscipline


class ProjectFileAIService:
    """Sugerencias de disciplina y descripción a partir del nombre y MIME (sin leer binarios CAD)."""

    _SYSTEM = """Eres asistente para clasificar planos y documentos de obra en español.
Debes responder SOLO con un JSON válido con las claves "discipline" y "description".
- discipline: una de: arquitectura, estructura, mecanica, electrica, plomeria
- description: 1 a 3 frases cortas en español describiendo qué podría ser el archivo según su nombre y tipo.
No tienes acceso al contenido binario de DWG/DXF; infiere solo por nombre de archivo y extensión/MIME.
Si no estás seguro, elige la disciplina más probable y dilo brevemente en la descripción."""

    def __init__(self) -> None:
        self._settings = get_settings()
        key = self._settings.openai_api_key
        self._client: Optional[AsyncOpenAI] = (
            AsyncOpenAI(api_key=key) if key and key.strip() else None
        )

    async def suggest(self, original_name: str, mime: Optional[str]) -> tuple[Optional[FileDiscipline], str, bool]:
        """Returns (discipline or None, description, used_openai)."""
        if self._client is None:
            return None, "", False

        client = self._client
        user_msg = f"Nombre del archivo: {original_name}\nMIME: {mime or 'desconocido'}"

        try:
            completion = await client.chat.completions.create(
                model=self._settings.openai_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": self._SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
            )
        except Exception:
            return None, "", False

        raw = completion.choices[0].message.content
        if not raw:
            return None, "", True

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None, "", True

        d_raw = data.get("discipline")
        desc = (data.get("description") or "").strip()
        if not isinstance(d_raw, str):
            return None, desc, True
        disc: Optional[FileDiscipline] = None
        v = d_raw.strip().lower()
        for e in FileDiscipline:
            if e.value == v:
                disc = e
                break
        return disc, desc, True
