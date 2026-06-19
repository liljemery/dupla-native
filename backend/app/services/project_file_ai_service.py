from __future__ import annotations

import json
import random
from typing import Optional

from openai import AsyncOpenAI

from app.config import get_settings


class ProjectFileAIService:
    """Sugerencias de descripción a partir del nombre y MIME (sin leer binarios CAD)."""

    _SYSTEM = """Eres un ingeniero presupuestista senior que clasifica planos y documentos de obra en español.
Responde SOLO con un JSON válido con la clave "description".

- "description": un BRIEFING corto (1 a 3 frases) que EMPIECE con
  "Este plano puede contener información sobre ..." y enumere los elementos típicos
  que suelen aparecer en planos de obra según el nombre del archivo y su extensión/MIME.
  No inventes una disciplina concreta si el nombre no lo indica claramente."""

    def __init__(self) -> None:
        self._settings = get_settings()
        chosen = self._pick_key()
        self._client: Optional[AsyncOpenAI] = AsyncOpenAI(api_key=chosen) if chosen else None

    def _pick_key(self) -> Optional[str]:
        keys: list[str] = []
        csv = (self._settings.dupla_openai_keys or "").strip()
        if csv:
            keys.extend(part.strip() for part in csv.split(",") if part.strip())
        single = (self._settings.openai_api_key or "").strip()
        if single and single not in keys:
            keys.append(single)
        return random.choice(keys) if keys else None

    async def suggest(self, original_name: str, mime: Optional[str]) -> tuple[None, str, bool]:
        """Returns (discipline always None in DRAFT, description, used_openai)."""
        if self._client is None:
            return None, "", False

        user_msg = f"Nombre del archivo: {original_name}\nMIME: {mime or 'desconocido'}"

        try:
            completion = await self._client.chat.completions.create(
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

        desc = (data.get("description") or "").strip()
        return None, desc, True
