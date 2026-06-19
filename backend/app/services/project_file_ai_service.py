from __future__ import annotations

import json
import random
from typing import Optional

from openai import AsyncOpenAI

from app.config import get_settings
from app.domain.file_discipline import FileDiscipline, guess_discipline_from_filename


class ProjectFileAIService:
    """Sugerencias de disciplina y descripción a partir del nombre y MIME (sin leer binarios CAD)."""

    _SYSTEM = """Eres un ingeniero presupuestista senior que clasifica planos y documentos de obra en español.
Responde SOLO con un JSON válido con las claves "discipline" y "description".

- "discipline": una de: arquitectura, estructura, mecanica, electrica, plomeria.
  Infiérela por el NOMBRE del archivo y su extensión/MIME (no tienes acceso al binario DWG/DXF).

- "description": un BRIEFING corto (1 a 3 frases) que EMPIECE con
  "Este plano puede contener información sobre ..." y enumere los elementos típicos de la
  disciplina inferida, para orientar la cuantificación. Guíate por la disciplina:
    • estructura: columnas, vigas, losas, zapatas/cimentación, secciones, acero de refuerzo, f'c.
    • arquitectura: distribución de espacios, muros y tabiques, acabados (pisos, cielos, pintura), puertas y ventanas.
    • electrica: tableros, circuitos, canalizaciones, tomacorrientes, interruptores, luminarias.
    • mecanica: climatización/HVAC, ductos, equipos, difusores, rejillas, ventilación.
    • plomeria: agua potable, aguas negras, drenaje pluvial, tuberías, piezas sanitarias, registros, cisterna.

Si no estás seguro de la disciplina, elige la más probable y dilo en la descripción."""

    def __init__(self) -> None:
        self._settings = get_settings()
        chosen = self._pick_key()
        self._client: Optional[AsyncOpenAI] = AsyncOpenAI(api_key=chosen) if chosen else None

    def _pick_key(self) -> Optional[str]:
        """Pick one OpenAI key from DUPLA_OPENAI_KEYS (CSV) or OPENAI_API_KEY.

        A new ProjectFileAIService is created per uploaded file, so choosing a
        random key here spreads files across the configured keys (rotation)."""
        keys: list[str] = []
        csv = (self._settings.dupla_openai_keys or "").strip()
        if csv:
            keys.extend(part.strip() for part in csv.split(",") if part.strip())
        single = (self._settings.openai_api_key or "").strip()
        if single and single not in keys:
            keys.append(single)
        return random.choice(keys) if keys else None

    async def suggest(self, original_name: str, mime: Optional[str]) -> tuple[Optional[FileDiscipline], str, bool]:
        """Returns (discipline or None, description, used_openai).

        Always provides a deterministic filename-based discipline as a fallback
        so auto-categorisation works even when OpenAI is not configured or the
        call fails. The LLM result wins when it returns a valid discipline.
        """
        fallback = guess_discipline_from_filename(original_name)

        if self._client is None:
            return fallback, "", False

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
            return fallback, "", False

        raw = completion.choices[0].message.content
        if not raw:
            return fallback, "", True

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return fallback, "", True

        d_raw = data.get("discipline")
        desc = (data.get("description") or "").strip()
        if not isinstance(d_raw, str):
            return fallback, desc, True
        disc: Optional[FileDiscipline] = None
        v = d_raw.strip().lower()
        for e in FileDiscipline:
            if e.value == v:
                disc = e
                break
        # LLM wins when it returns a valid discipline; otherwise keep filename guess.
        return (disc or fallback), desc, True
