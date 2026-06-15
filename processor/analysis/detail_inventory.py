"""
Fase 1 — inventario de detalles por disciplina (sin cuantificar).

Aquí solo definimos el contrato de datos, la carga de prompts versionados y un
parser JSON para cuando Vision devuelva la estructura acordada. La llamada a
OpenAI puede engancharse desde el pipeline sin acoplar este módulo a la API.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

DisciplineId = Literal["arquitectonica", "estructural", "sanitaria", "electrica"]

_PROMPTS_DIR = Path(__file__).resolve().parent / "discipline_prompts"

_BASE_USER_TEMPLATE = """Eres un analista de planos de construcción. Tu trabajo NO es cuantificar todavía.
Tu trabajo es INVENTARIAR qué información existe en este plano.

DISCIPLINA: {discipline}

Para cada elemento que identifiques, clasifícalo en:

1. EXPLÍCITO: El plano lo muestra claramente con tipo, dimensiones, especificaciones, cantidad visible.
   Formato: tipo | identificador | especificación | dónde aparece | cómo contarlo

2. IMPLÍCITO: El plano sugiere su existencia pero no da todos los datos.
   Formato: tipo | qué se ve | qué falta | qué se podría asumir | nivel de confianza (alto/medio/bajo)

3. FALTANTE: Elementos que normalmente existen en esta disciplina pero NO aparecen en este plano.
   Formato: tipo | dónde debería estar | impacto si no se tiene

NO inventes cantidades. NO asumas especificaciones que no puedas ver.
Si un muro dice "C1" pero no dice el espesor, repórtalo como: "Muro C1 — espesor NO especificado en este plano".

Instrucción adicional de disciplina:
{discipline_brief}

Cuando termines, devuelve SOLO JSON con la forma:
{{
  "discipline": "{discipline}",
  "explicit_elements": [{{"element_id": "...", "kind": "...", "label": "...", "specs": "...", "location": "...", "count_method": "..."}}],
  "implicit_elements": [{{"element_id": "...", "kind": "...", "seen": "...", "missing_data": "...", "assumption": "...", "confidence": "alto|medio|bajo"}}],
  "missing_elements": [{{"element_id": "...", "kind": "...", "expected_in": "...", "impact": "..."}}],
  "assumptions_needed": [{{"decision": "...", "default": "...", "override_by": "usuario"}}]
}}
"""


@dataclass
class ExplicitElement:
    element_id: str
    kind: str = ""
    label: str = ""
    specs: str = ""
    location: str = ""
    count_method: str = ""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ExplicitElement:
        return ExplicitElement(
            element_id=str(data.get("element_id") or data.get("id") or "").strip(),
            kind=str(data.get("kind") or data.get("type") or "").strip(),
            label=str(data.get("label") or "").strip(),
            specs=str(data.get("specs") or data.get("specification") or "").strip(),
            location=str(data.get("location") or "").strip(),
            count_method=str(data.get("count_method") or "").strip(),
        )


@dataclass
class ImplicitElement:
    element_id: str
    kind: str = ""
    seen: str = ""
    missing_data: str = ""
    assumption: str = ""
    confidence: str = ""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ImplicitElement:
        return ImplicitElement(
            element_id=str(data.get("element_id") or data.get("id") or "").strip(),
            kind=str(data.get("kind") or data.get("type") or "").strip(),
            seen=str(data.get("seen") or data.get("what_is_seen") or "").strip(),
            missing_data=str(data.get("missing_data") or data.get("what_is_missing") or "").strip(),
            assumption=str(data.get("assumption") or "").strip(),
            confidence=str(data.get("confidence") or "").strip().lower(),
        )


@dataclass
class MissingElement:
    element_id: str
    kind: str = ""
    expected_in: str = ""
    impact: str = ""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> MissingElement:
        return MissingElement(
            element_id=str(data.get("element_id") or data.get("id") or "").strip(),
            kind=str(data.get("kind") or data.get("type") or "").strip(),
            expected_in=str(data.get("expected_in") or "").strip(),
            impact=str(data.get("impact") or "").strip(),
        )


@dataclass
class Assumption:
    decision: str = ""
    default: str = ""
    override_by: str = "usuario"

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Assumption:
        return Assumption(
            decision=str(data.get("decision") or "").strip(),
            default=str(data.get("default") or "").strip(),
            override_by=str(data.get("override_by") or "usuario").strip(),
        )


@dataclass
class DetailReport:
    discipline: str
    explicit_elements: list[ExplicitElement] = field(default_factory=list)
    implicit_elements: list[ImplicitElement] = field(default_factory=list)
    missing_elements: list[MissingElement] = field(default_factory=list)
    assumptions_needed: list[Assumption] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "discipline": self.discipline,
            "explicit_elements": [vars(x) for x in self.explicit_elements],
            "implicit_elements": [vars(x) for x in self.implicit_elements],
            "missing_elements": [vars(x) for x in self.missing_elements],
            "assumptions_needed": [vars(x) for x in self.assumptions_needed],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> DetailReport:
        def only_dicts(items: Any) -> list[dict[str, Any]]:
            if not isinstance(items, list):
                return []
            return [x for x in items if isinstance(x, dict)]

        return DetailReport(
            discipline=str(data.get("discipline") or "").strip(),
            explicit_elements=[ExplicitElement.from_dict(x) for x in only_dicts(data.get("explicit_elements"))],
            implicit_elements=[ImplicitElement.from_dict(x) for x in only_dicts(data.get("implicit_elements"))],
            missing_elements=[MissingElement.from_dict(x) for x in only_dicts(data.get("missing_elements"))],
            assumptions_needed=[Assumption.from_dict(x) for x in only_dicts(data.get("assumptions_needed"))],
        )


def load_discipline_prompt(discipline: str, *, prompts_dir: Path | None = None) -> str:
    """Carga el markdown versionado por disciplina (texto libre + bullet de foco)."""
    base = prompts_dir or _PROMPTS_DIR
    path = base / f"{discipline}.md"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def build_detail_inventory_user_content(
    discipline: str,
    *,
    discipline_brief: str | None = None,
    prompts_dir: Path | None = None,
) -> str:
    brief = discipline_brief if discipline_brief is not None else load_discipline_prompt(discipline, prompts_dir=prompts_dir)
    if not brief.strip():
        brief = "(Sin guía adicional: usa buenas prácticas locales RD / FIEBDC.)"
    return _BASE_USER_TEMPLATE.format(discipline=discipline, discipline_brief=brief)


def parse_detail_inventory_json(raw: str) -> DetailReport:
    """Parsea la respuesta Vision (solo JSON)."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Detail inventory JSON must be an object")
    return DetailReport.from_dict(data)


def build_detail_inventory_messages(
    discipline: str,
    *,
    prompts_dir: Path | None = None,
) -> list[dict[str, str]]:
    """Plantilla lista para OpenAI chat: system + user (sin imágenes aquí)."""
    user = build_detail_inventory_user_content(discipline, prompts_dir=prompts_dir)
    return [
        {
            "role": "system",
            "content": (
                "Analista de planos. Solo inventario de información; prohibido inventar cantidades "
                "o precios. Responde SOLO con JSON válido."
            ),
        },
        {"role": "user", "content": user},
    ]
