"""
(d) MOTOR DE DERIVACION de partidas (RulesEngine).

Cada elemento dibujado dispara una familia de partidas con ratios. El quantifier
base mide lo dibujado (wall_net_area, floor_area, ceiling_area, ...). Este motor
*deriva* el trabajo no dibujado pero real: panete, pintura, impermeabilizacion,
contrapiso, etc. Antes ``apply()`` devolvia lo mismo que recibia (504 -> 504, sin
aporte); ahora expande los takeoffs base segun reglas por disciplina.

Las reglas viven en ``disciplines/<disc>/derivation_rules.yaml`` y consumen la
config dura del proyecto (``project_parameters`` -> desperdicios, etc.). El motor:
  - solo deriva tipos que el quantifier base NO produce para ese elemento (anti
    doble-conteo). Estructura ya deriva encofrado/acero/excavacion en el
    quantifier, por eso su archivo de reglas viene vacio.
  - nunca elimina takeoffs; solo agrega.
  - etiqueta cada derivado (assumptions + trace.metadata + inputs.derived_from).
  - se puede apagar con DUPLA_DERIVATION_ENABLED=0.

API estable consumida por core/pipeline.py:
    default_rules_engine(rules_path=None, *, discipline=None, project_parameters=None)
    RulesEngine(...).apply(takeoffs) -> takeoffs (superset)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("dupla.rules_engine")

_DISCIPLINES_DIR = Path(__file__).resolve().parent / "disciplines"


def derivation_enabled() -> bool:
    raw = (os.getenv("DUPLA_DERIVATION_ENABLED") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


@dataclass
class DerivationRule:
    id: str
    from_type: str
    to_type: str
    unit: str
    multiplier: float = 1.0
    waste_key: str | None = None          # llave dentro de project_parameters.desperdicios
    inflate_with_waste: bool = False      # si True, cantidad *= (1+waste)
    when_context_any: list[str] = field(default_factory=list)
    summary: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DerivationRule":
        return cls(
            id=str(data["id"]),
            from_type=str(data["from"]),
            to_type=str(data["to"]),
            unit=str(data.get("unit", "")),
            multiplier=float(data.get("multiplier", 1.0)),
            waste_key=data.get("waste"),
            inflate_with_waste=bool(data.get("inflate_with_waste", False)),
            when_context_any=[str(x).lower() for x in (data.get("when_context_any") or [])],
            summary=str(data.get("summary", "")),
        )


class RulesEngine:
    def __init__(
        self,
        rules: list[DerivationRule] | None = None,
        *,
        discipline: str | None = None,
        project_parameters: dict[str, Any] | None = None,
        structural_schedule: dict[str, Any] | None = None,
        openings_schedule: dict[str, Any] | None = None,
    ) -> None:
        self.rules = rules or []
        self.discipline = discipline
        self.params = project_parameters or {}
        self._waste = dict((self.params.get("desperdicios") or {}))
        self.structural_schedule = structural_schedule or {}
        self.openings_schedule = openings_schedule or {}

    # -- helpers ----------------------------------------------------------------

    @staticmethod
    def _element_root(item_key: str) -> str:
        # "wall123:net_area" -> "wall123"; "wall123#rule" -> "wall123"
        return item_key.split(":", 1)[0].split("#", 1)[0]

    @staticmethod
    def _context_tokens(takeoff: Any) -> set[str]:
        tokens: set[str] = set()
        inputs = getattr(takeoff, "inputs", {}) or {}
        for key in ("context_tags",):
            val = inputs.get(key)
            if isinstance(val, list):
                tokens.update(str(v).lower() for v in val)
        for key in ("material_hint", "location", "interior_exterior_hint", "description"):
            val = inputs.get(key)
            if isinstance(val, str):
                tokens.add(val.lower())
        return tokens

    def _matches_context(self, rule: DerivationRule, takeoff: Any) -> bool:
        if not rule.when_context_any:
            return True
        tokens = self._context_tokens(takeoff)
        blob = " ".join(tokens)
        return any(tok in blob for tok in rule.when_context_any)

    # -- main -------------------------------------------------------------------

    def apply(self, takeoffs: list[Any]) -> list[Any]:
        if not takeoffs:
            return takeoffs
        result = list(takeoffs)
        # 1) Derivacion 1->N (arquitectura, etc.)
        if self.rules and derivation_enabled():
            result = self._apply_derivations(result)
        # 2) Autoridad de cuadros (acero del despiece, conteos de aberturas)
        result = self._apply_schedule_authority(result)
        return result

    def _apply_schedule_authority(self, takeoffs: list[Any]) -> list[Any]:
        result = takeoffs
        try:
            if self.structural_schedule.get("filas"):
                from knowledge.schedule_authority import apply_structural_steel_authority

                cover_m = float(self.params.get("recubrimiento_cm", 4.0)) / 100.0
                result = apply_structural_steel_authority(
                    result, self.structural_schedule, cover_m=cover_m
                )
            if self.openings_schedule.get("filas"):
                from knowledge.schedule_authority import apply_opening_count_authority

                result = apply_opening_count_authority(result, self.openings_schedule)
        except Exception:
            logger.warning("schedule authority skipped (non-fatal)", exc_info=True)
        return result

    def _apply_derivations(self, takeoffs: list[Any]) -> list[Any]:
        # Tipos ya presentes por elemento (anti doble-conteo).
        existing: dict[str, set[str]] = {}
        existing_keys: set[str] = set()
        for t in takeoffs:
            root = self._element_root(t.item_key)
            existing.setdefault(root, set()).add(t.item_type)
            existing_keys.add(t.item_key)

        derived: list[Any] = []
        for t in takeoffs:
            for rule in self.rules:
                if t.item_type != rule.from_type:
                    continue
                root = self._element_root(t.item_key)
                if rule.to_type in existing.get(root, set()):
                    continue  # ya existe medido; no duplicar
                if not self._matches_context(rule, t):
                    continue
                new_takeoff = self._build_derived(t, rule)
                if new_takeoff is None:
                    continue
                if new_takeoff.item_key in existing_keys:
                    continue
                existing_keys.add(new_takeoff.item_key)
                existing.setdefault(root, set()).add(rule.to_type)
                derived.append(new_takeoff)

        if derived:
            logger.info(
                "RulesEngine[%s]: derived +%d takeoffs from %d base",
                self.discipline or "?", len(derived), len(takeoffs),
            )
        return list(takeoffs) + derived

    def _build_derived(self, base: Any, rule: DerivationRule) -> Any | None:
        try:
            base_qty = float(base.quantity or 0.0)
        except (TypeError, ValueError):
            return None
        if base_qty <= 0:
            return None

        waste = float(self._waste.get(rule.waste_key, 0.0)) if rule.waste_key else 0.0
        qty = base_qty * rule.multiplier
        if rule.inflate_with_waste and waste:
            qty *= (1.0 + waste)
        qty = round(qty, 4)

        # Import local para no crear ciclo de import en el arranque del modulo.
        from core.schemas import QuantityTakeoff, QuantityTrace

        formula = f"{base.item_type}({base_qty}) x {rule.multiplier}"
        if rule.inflate_with_waste and waste:
            formula += f" x (1+{waste})"

        inputs = {
            "derived_from": base.item_key,
            "derived_from_type": base.item_type,
            "rule_id": rule.id,
            "multiplier": rule.multiplier,
        }
        if rule.waste_key:
            inputs["desperdicio_key"] = rule.waste_key
            inputs["desperdicio"] = waste
        # propaga tags de contexto utiles para pricing/clasificacion
        base_inputs = getattr(base, "inputs", {}) or {}
        if isinstance(base_inputs.get("context_tags"), list):
            inputs["context_tags"] = base_inputs["context_tags"]
        if base_inputs.get("source_file"):
            inputs["source_file"] = base_inputs["source_file"]
        if base_inputs.get("level_name"):
            inputs["level_name"] = base_inputs["level_name"]

        trace = QuantityTrace(
            source_entity_ids=[self._element_root(base.item_key)],
            steps=[f"Derivado por regla '{rule.id}' desde {base.item_type}."],
            metadata={"rule_id": rule.id, "base_item_key": base.item_key},
        )

        return QuantityTakeoff(
            item_key=f"{base.item_key}#{rule.id}",
            item_type=rule.to_type,
            level_id=getattr(base, "level_id", None),
            unit=rule.unit or base.unit,
            quantity=qty,
            formula=formula,
            inputs=inputs,
            assumptions=[
                (rule.summary or f"Partida derivada ({rule.to_type}) por motor de reglas.")
                + (f" Desperdicio {rule.waste_key}={waste}." if rule.waste_key and waste else "")
            ],
            source_refs=list(getattr(base, "source_refs", []) or []),
            trace=trace,
            confidence=0.7,
            requiere_revision=True,
        )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _load_rules_for_discipline(discipline: str) -> list[DerivationRule]:
    path = _DISCIPLINES_DIR / discipline / "derivation_rules.yaml"
    if not path.exists():
        return []
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.warning("Could not parse %s", path, exc_info=True)
        return []
    rules: list[DerivationRule] = []
    for entry in (data.get("derivations") or []):
        try:
            rules.append(DerivationRule.from_dict(entry))
        except Exception:
            logger.warning("Bad derivation rule in %s: %r", path, entry, exc_info=True)
    return rules


def default_rules_engine(
    rules_path: Any = None,
    *,
    discipline: str | None = None,
    project_parameters: dict[str, Any] | None = None,
    structural_schedule: dict[str, Any] | None = None,
    openings_schedule: dict[str, Any] | None = None,
) -> RulesEngine:
    """Build a RulesEngine.

    Backwards compatible: ``rules_path`` (legacy positional) is accepted and
    ignored when no discipline is given, so existing callers keep working.
    """
    rules: list[DerivationRule] = []
    if discipline:
        rules = _load_rules_for_discipline(discipline)
    return RulesEngine(
        rules,
        discipline=discipline,
        project_parameters=project_parameters,
        structural_schedule=structural_schedule,
        openings_schedule=openings_schedule,
    )
