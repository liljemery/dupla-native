"""
Post-vision domain validator.

Classifies each extracted element as belongs / not_belongs / unclassified,
checks required attributes, and generates two report files:
  - unclassified_elements.txt  (R1.b)
  - missing_attributes.txt     (R3)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .domain_rules import DomainRules

logger = logging.getLogger("dupla.domain_validator")


# ---------------------------------------------------------------------------
# Classification result types
# ---------------------------------------------------------------------------

@dataclass
class ElementClassification:
    element_type: str
    element_id: str
    source_page: str
    classification: str  # "belongs", "not_belongs", "unclassified"
    reason: str = ""


@dataclass
class MissingAttribute:
    element_type: str
    element_id: str
    source_page: str
    attribute_name: str
    description: str = ""


@dataclass
class ValidationResult:
    discipline_id: str
    project_name: str
    timestamp: str
    classified: list[ElementClassification] = field(default_factory=list)
    missing_attributes: list[MissingAttribute] = field(default_factory=list)

    @property
    def unclassified(self) -> list[ElementClassification]:
        return [c for c in self.classified if c.classification == "unclassified"]

    @property
    def not_belongs(self) -> list[ElementClassification]:
        return [c for c in self.classified if c.classification == "not_belongs"]

    @property
    def belongs(self) -> list[ElementClassification]:
        return [c for c in self.classified if c.classification == "belongs"]


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

def _resolve_element_type(element: dict[str, Any]) -> str:
    """Infer the element_type from a vision-extracted element dict."""
    explicit = element.get("element_type") or element.get("type") or ""
    if explicit:
        return str(explicit).lower().strip()

    material = str(element.get("material") or element.get("material_hint") or "").lower()
    if "block" in material or "masonry" in material:
        return "wall_masonry"
    if material in ("concrete", "drywall", "wood"):
        return f"wall_{material}"

    return "unknown"


def _get_attr_value(element: dict[str, Any], attr_name: str) -> Any:
    """Look up an attribute in an element dict, checking nested structures."""
    if attr_name in element:
        return element[attr_name]

    if attr_name.startswith("reinforcement_"):
        details = element.get("reinforcement_details") or {}
        suffix = attr_name.replace("reinforcement_", "")
        if suffix in details:
            return details[suffix]

    raw = element.get("raw") or element.get("inputs", {}).get("raw") or {}
    if isinstance(raw, dict) and attr_name in raw:
        return raw[attr_name]

    return None


def validate_vision_output(
    vision_results: list[dict[str, Any]],
    rules: DomainRules,
    project_name: str = "",
) -> ValidationResult:
    """Validate all vision-extracted elements against domain rules.

    Walks through each page's elements and:
    1. Classifies each as belongs / not_belongs / unclassified
    2. For 'belongs' elements, checks required attributes
    """
    result = ValidationResult(
        discipline_id=rules.discipline_id,
        project_name=project_name,
        timestamp=datetime.now().isoformat(),
    )

    element_lists = {
        "walls": "wall",
        "doors": "door",
        "windows": "window",
        "wet_areas": "wet_area",
        "kitchens": "kitchen",
        "stairs": "stair",
        "structural_elements": "structural",
        "fixtures": "fixture",
        "floor_finishes": "floor_finish",
        "ceiling_finishes": "ceiling_finish",
        "electrical": "electrical",
        "plumbing": "plumbing",
        "exterior_works": "exterior",
    }

    for page_result in vision_results:
        if not isinstance(page_result, dict) or "error" in page_result:
            continue

        source_page = page_result.get("source_image") or page_result.get("level_name") or "unknown"

        for list_key, default_type in element_lists.items():
            elements = page_result.get(list_key) or []
            if not isinstance(elements, list):
                continue

            for elem in elements:
                if not isinstance(elem, dict):
                    continue

                etype = _resolve_element_type(elem)
                if etype == "unknown" or etype == "structural":
                    etype = elem.get("element_type") or elem.get("type") or default_type
                    etype = str(etype).lower().strip()

                elem_id = elem.get("id") or elem.get("notation") or f"{etype}_{id(elem)}"

                belongs = rules.element_belongs(etype)

                if belongs is None:
                    result.classified.append(ElementClassification(
                        element_type=etype,
                        element_id=str(elem_id),
                        source_page=source_page,
                        classification="unclassified",
                        reason=f"'{etype}' not found in domain_rules.yaml for {rules.discipline_id}",
                    ))
                elif not belongs:
                    rule = rules.vision_elements.get(etype)
                    reason = rule.reason if rule else ""
                    result.classified.append(ElementClassification(
                        element_type=etype,
                        element_id=str(elem_id),
                        source_page=source_page,
                        classification="not_belongs",
                        reason=reason,
                    ))
                else:
                    result.classified.append(ElementClassification(
                        element_type=etype,
                        element_id=str(elem_id),
                        source_page=source_page,
                        classification="belongs",
                    ))

                    for attr_rule in rules.get_required_attributes(etype):
                        value = _get_attr_value(elem, attr_rule.name)
                        if value is None or value == "" or value == "null":
                            result.missing_attributes.append(MissingAttribute(
                                element_type=etype,
                                element_id=str(elem_id),
                                source_page=source_page,
                                attribute_name=attr_rule.name,
                                description=attr_rule.description or "",
                            ))

    logger.info(
        "Domain validation: %d elements (%d belongs, %d not_belongs, %d unclassified), "
        "%d missing attributes",
        len(result.classified),
        len(result.belongs),
        len(result.not_belongs),
        len(result.unclassified),
        len(result.missing_attributes),
    )
    return result


# ---------------------------------------------------------------------------
# Report generation (R1.b + R3)
# ---------------------------------------------------------------------------

def write_unclassified_report(result: ValidationResult, output_path: Path) -> Path | None:
    """Write R1.b unclassified elements report. Returns path or None if empty."""
    unclassified = result.unclassified
    if not unclassified:
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)

    type_counts: dict[str, list[ElementClassification]] = {}
    for item in unclassified:
        type_counts.setdefault(item.element_type, []).append(item)

    lines = [
        "=" * 62,
        f"ELEMENTOS NO CLASIFICADOS - {result.project_name}",
        f"Disciplina activa: {result.discipline_id}",
        f"Corrida: {result.timestamp}",
        "=" * 62,
        "",
    ]

    idx = 1
    for etype, items in sorted(type_counts.items()):
        pages = sorted({i.source_page for i in items})
        lines.append(f"[{idx}] Elemento: {etype}")
        lines.append(f"    Planos: {', '.join(pages)}")
        lines.append(f"    Apariciones: {len(items)}")
        lines.append(f"    IDs: {', '.join(i.element_id for i in items[:5])}")
        if len(items) > 5:
            lines.append(f"         ... y {len(items) - 5} mas")
        lines.append(f"    Accion: Agregar a domain_rules.yaml de la disciplina correspondiente")
        lines.append("")
        idx += 1

    total_appearances = len(unclassified)
    lines.extend([
        "=" * 62,
        f"Total no clasificados: {len(type_counts)} tipos, {total_appearances} apariciones",
        f"Para resolver: editar disciplines/<disciplina>/domain_rules.yaml",
        "=" * 62,
    ])

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Unclassified elements report: %s (%d types)", output_path, len(type_counts))
    return output_path


def write_missing_attributes_report(result: ValidationResult, output_path: Path) -> Path | None:
    """Write R3 missing attributes report. Returns path or None if empty."""
    missing = result.missing_attributes
    if not missing:
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)

    belongs_elements = {(c.element_type, c.element_id, c.source_page) for c in result.belongs}

    by_element: dict[tuple[str, str, str], list[MissingAttribute]] = {}
    for m in missing:
        key = (m.element_type, m.element_id, m.source_page)
        by_element.setdefault(key, []).append(m)

    lines = [
        "=" * 62,
        f"ATRIBUTOS FALTANTES - {result.discipline_id.title()} - {result.project_name}",
        f"Corrida: {result.timestamp}",
        "=" * 62,
        "",
    ]

    total_reviewed = len(belongs_elements)
    elements_with_missing = set()

    for (etype, eid, page), attrs in sorted(by_element.items()):
        elements_with_missing.add((etype, eid, page))
        lines.append(f"{etype.upper()} {eid} ({page})")

        elem_rule = result.discipline_id  # for context
        rule_attrs = set()
        from .domain_rules import load_domain_rules_for_discipline
        rules = load_domain_rules_for_discipline(result.discipline_id)
        if rules:
            for attr_rule in rules.get_required_attributes(etype):
                rule_attrs.add(attr_rule.name)

        missing_names = {a.attribute_name for a in attrs}
        ok_names = rule_attrs - missing_names

        for ok in sorted(ok_names):
            lines.append(f"  [OK]    {ok}")
        for m in attrs:
            desc = f" -- {m.description}" if m.description else ""
            lines.append(f"  [FALTA] {m.attribute_name}{desc}")

        lines.append("")

    complete = total_reviewed - len(elements_with_missing)
    pct = (complete / total_reviewed * 100) if total_reviewed else 0

    attr_counts: dict[str, int] = {}
    for m in missing:
        attr_counts[m.attribute_name] = attr_counts.get(m.attribute_name, 0) + 1

    lines.extend([
        "=" * 62,
        "RESUMEN:",
        f"  Elementos revisados: {total_reviewed}",
        f"  Completos (todos los obligatorios): {complete} ({pct:.0f}%)",
        f"  Con faltantes: {len(elements_with_missing)} ({100 - pct:.0f}%)",
        f"  Total atributos faltantes: {len(missing)}",
        "",
        "  Top faltantes:",
    ])
    for attr_name, count in sorted(attr_counts.items(), key=lambda x: -x[1])[:10]:
        lines.append(f"    {attr_name}: {count} elementos")

    lines.extend(["=" * 62])

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Missing attributes report: %s (%d missing)", output_path, len(missing))
    return output_path
