"""
P0.2 — Deterministic item_type -> APU crosswalk matcher.

Replaces fuzzy keyword/embedding pricing with a curated lookup: a takeoff's
``item_type`` plus a few attributes (section, thickness, discipline) resolve to
exactly one APU code, an explicit EXCLUDE (cost already bundled — avoids the
double/triple billing of separate rebar/formwork takeoffs against all-inclusive
concrete APUs), or UNMATCHED (no price exists in the catalog — a data gap).

Every result is traceable to the rule id that fired.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

logger = logging.getLogger("dupla.pricing.crosswalk")

_DEFAULT_PATH = Path(__file__).resolve().parent / "crosswalk.yaml"

_SPECIAL_TARGETS = {"EXCLUDE", "UNMATCHED"}
_CM_TO_INCH = {10: 4, 15: 6, 20: 8, 30: 12}
_SECTION_TOL = 0.02
_THICKNESS_TOL = 0.03


@dataclass(frozen=True)
class CrosswalkResult:
    target: str | None        # APU code | "EXCLUDE" | "UNMATCHED" | None (no rule)
    rule_id: str | None
    kind: str                 # "apu" | "exclude" | "unmatched" | "none"

    @property
    def priceable(self) -> bool:
        return self.kind == "apu"


def _f(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def _section_of(inputs: Mapping[str, Any]) -> tuple[float, float] | None:
    w = _f(inputs.get("section_width_m"))
    h = _f(inputs.get("section_height_m"))
    if w is None or h is None:
        return None
    return tuple(sorted((round(w, 3), round(h, 3))))  # type: ignore[return-value]


def _parse_section(spec: str) -> tuple[float, float] | None:
    try:
        a, b = str(spec).lower().split("x")
        return tuple(sorted((float(a), float(b))))  # type: ignore[return-value]
    except (ValueError, AttributeError):
        return None


def _section_matches(sec: tuple[float, float] | None, specs: Iterable[str]) -> bool:
    if sec is None:
        return False
    for spec in specs:
        rs = _parse_section(spec)
        if rs and abs(sec[0] - rs[0]) <= _SECTION_TOL and abs(sec[1] - rs[1]) <= _SECTION_TOL:
            return True
    return False


def _inch_of(inputs: Mapping[str, Any]) -> int | None:
    t = _f(inputs.get("thickness_m"))
    if t is None:
        return None
    return _CM_TO_INCH.get(round(t * 100))


def _thickness_value(inputs: Mapping[str, Any]) -> float | None:
    # Wall thickness lives in thickness_m; slab thickness in section_height_m.
    return _f(inputs.get("thickness_m")) if inputs.get("thickness_m") is not None else _f(inputs.get("section_height_m"))


class CrosswalkMatcher:
    def __init__(self, rules: list[dict[str, Any]], *, valid_apu_codes: set[str] | None = None):
        self.rules = rules
        self.valid_apu_codes = valid_apu_codes
        if valid_apu_codes is not None:
            missing = sorted({
                str(r["target"]) for r in rules
                if str(r.get("target")) not in _SPECIAL_TARGETS and str(r.get("target")) not in valid_apu_codes
            })
            if missing:
                logger.warning("Crosswalk references %d APU codes absent from the price file: %s",
                               len(missing), missing[:15])

    @classmethod
    def from_yaml(
        cls,
        path: str | Path | None = None,
        *,
        valid_apu_codes: set[str] | None = None,
    ) -> "CrosswalkMatcher":
        import yaml
        p = Path(path) if path else _DEFAULT_PATH
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cls(list(data.get("rules") or []), valid_apu_codes=valid_apu_codes)

    def _rule_matches(self, rule: dict[str, Any], item_type: str, inputs: Mapping[str, Any]) -> bool:
        if "item_type" in rule and rule["item_type"] != item_type:
            return False
        if "item_type_in" in rule and item_type not in rule["item_type_in"]:
            return False
        if "section_any" in rule and not _section_matches(_section_of(inputs), rule["section_any"]):
            return False
        if "thickness_in" in rule and _inch_of(inputs) != int(rule["thickness_in"]):
            return False
        if "thickness_m" in rule:
            tv = _thickness_value(inputs)
            if tv is None or abs(tv - float(rule["thickness_m"])) > _THICKNESS_TOL:
                return False
        if "discipline" in rule:
            if str(inputs.get("discipline") or "").lower() != str(rule["discipline"]).lower():
                return False
        return True

    def match(self, item_type: str, inputs: Mapping[str, Any] | None = None) -> CrosswalkResult:
        inputs = inputs or {}
        for rule in self.rules:
            if self._rule_matches(rule, item_type, inputs):
                target = str(rule.get("target") or "").strip()
                rule_id = str(rule.get("id") or "")
                if target == "EXCLUDE":
                    return CrosswalkResult("EXCLUDE", rule_id, "exclude")
                if target == "UNMATCHED":
                    return CrosswalkResult("UNMATCHED", rule_id, "unmatched")
                return CrosswalkResult(target, rule_id, "apu")
        return CrosswalkResult(None, None, "none")


def default_matcher(valid_apu_codes: set[str] | None = None) -> CrosswalkMatcher:
    path = os.getenv("DUPLA_CROSSWALK_PATH") or _DEFAULT_PATH
    return CrosswalkMatcher.from_yaml(path, valid_apu_codes=valid_apu_codes)
