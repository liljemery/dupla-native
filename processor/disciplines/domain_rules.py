"""
Domain rules loader and validator for per-discipline element classification.

Loads ``domain_rules.yaml`` files that declare which vision element types
belong to each discipline, which attributes are required/optional, and
which quantifier item_types are allowed in the budget.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("dupla.domain_rules")


@dataclass
class AttributeRule:
    name: str
    unit: str | None = None
    description: str | None = None
    expected_values: list[str] = field(default_factory=list)


@dataclass
class VisionElementRule:
    element_type: str
    belongs: bool
    description: str = ""
    reason: str = ""
    required_attributes: list[AttributeRule] = field(default_factory=list)
    optional_attributes: list[AttributeRule] = field(default_factory=list)


@dataclass
class DomainRules:
    discipline_id: str
    display_name: str
    version: str
    vision_elements: dict[str, VisionElementRule]
    blacklisted_item_types: set[str]
    budget_item_types: set[str]

    @property
    def whitelisted_element_types(self) -> set[str]:
        return {k for k, v in self.vision_elements.items() if v.belongs}

    @property
    def blacklisted_element_types(self) -> set[str]:
        return {k for k, v in self.vision_elements.items() if not v.belongs}

    def element_belongs(self, element_type: str) -> bool | None:
        """Return True/False if element is in rules, or None if unknown."""
        rule = self.vision_elements.get(element_type)
        if rule is None:
            return None
        return rule.belongs

    def get_required_attributes(self, element_type: str) -> list[AttributeRule]:
        rule = self.vision_elements.get(element_type)
        if rule is None or not rule.belongs:
            return []
        return rule.required_attributes


def _parse_attribute(raw: dict[str, Any]) -> AttributeRule:
    return AttributeRule(
        name=str(raw.get("name", "")),
        unit=raw.get("unit"),
        description=raw.get("description"),
        expected_values=list(raw.get("expected_values", [])),
    )


def _parse_vision_element(element_type: str, raw: Any) -> VisionElementRule:
    if not isinstance(raw, dict):
        return VisionElementRule(element_type=element_type, belongs=bool(raw))

    belongs = bool(raw.get("belongs", True))
    required = [_parse_attribute(a) for a in raw.get("required_attributes", [])]
    optional = [_parse_attribute(a) for a in raw.get("optional_attributes", [])]

    return VisionElementRule(
        element_type=element_type,
        belongs=belongs,
        description=str(raw.get("description", "")),
        reason=str(raw.get("reason", "")),
        required_attributes=required,
        optional_attributes=optional,
    )


def load_domain_rules(path: str | Path) -> DomainRules:
    """Load a ``domain_rules.yaml`` file into a ``DomainRules`` instance."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Domain rules file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid domain rules format in {path}")

    vision_elements: dict[str, VisionElementRule] = {}
    for etype, edata in (raw.get("vision_elements") or {}).items():
        vision_elements[etype] = _parse_vision_element(etype, edata)

    rules = DomainRules(
        discipline_id=str(raw.get("discipline_id", "")),
        display_name=str(raw.get("display_name", "")),
        version=str(raw.get("version", "0.0")),
        vision_elements=vision_elements,
        blacklisted_item_types=set(raw.get("blacklisted_item_types", [])),
        budget_item_types=set(raw.get("budget_item_types", [])),
    )

    logger.info(
        "Loaded domain rules for '%s': %d elements (%d whitelisted, %d blacklisted), "
        "%d budget item types",
        rules.discipline_id,
        len(rules.vision_elements),
        len(rules.whitelisted_element_types),
        len(rules.blacklisted_element_types),
        len(rules.budget_item_types),
    )
    return rules


def load_domain_rules_for_discipline(discipline_id: str) -> DomainRules | None:
    """Load domain rules from the standard path for a given discipline.

    Returns None if the YAML file does not exist (backward-compatible).
    """
    rules_path = (
        Path(__file__).resolve().parent / discipline_id / "domain_rules.yaml"
    )
    if not rules_path.exists():
        logger.debug("No domain_rules.yaml for discipline '%s'", discipline_id)
        return None
    return load_domain_rules(rules_path)
