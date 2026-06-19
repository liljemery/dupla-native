"""
Quality evaluation and report writers for semantic interpretation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from core.quality_models import QualityIssue, QualityReport
from core.semantic_models import SemanticBuilding, SemanticElement


def _evaluate_element(element: SemanticElement, *, discipline: str) -> QualityIssue:
    confidence = float(element.confidence_score or 0.0)
    if not element.level_id:
        return QualityIssue(
            status="BLOCKED",
            code="missing_level",
            message="Elemento sin nivel asignado; no se puede cuantificar con trazabilidad.",
            discipline=discipline,
            element_id=element.element_id,
            confidence_score=confidence,
            evidence_refs=list(element.evidence_refs),
            raw_entity_ids=list(element.raw_entity_ids),
            suggested_action="Definir nivel/capa de origen para este elemento.",
        )
    if not element.space_id:
        # ponytail: cuantificar a nivel de planta sin space_id; solo bloquear sin level_id
        return QualityIssue(
            status="WARNING",
            code="missing_space",
            message="Elemento sin espacio asignado; se cuantifica a nivel de planta.",
            discipline=discipline,
            element_id=element.element_id,
            level_id=element.level_id,
            unit_id=element.unit_id,
            confidence_score=confidence,
            evidence_refs=list(element.evidence_refs),
            raw_entity_ids=list(element.raw_entity_ids),
            suggested_action="Agregar etiquetas espaciales en planos para mayor granularidad.",
        )
    if confidence < 0.75:
        return QualityIssue(
            status="WARNING",
            code="low_confidence_assignment",
            message="Asignación válida pero con confianza baja.",
            discipline=discipline,
            element_id=element.element_id,
            level_id=element.level_id,
            unit_id=element.unit_id,
            space_id=element.space_id,
            confidence_score=confidence,
            evidence_refs=list(element.evidence_refs),
            raw_entity_ids=list(element.raw_entity_ids),
            suggested_action="Revisar nomenclatura de capa/bloque para elevar confianza.",
        )
    return QualityIssue(
        status="OK",
        code="ready_for_quantification",
        message="Elemento trazable y listo para cuantificar.",
        discipline=discipline,
        element_id=element.element_id,
        level_id=element.level_id,
        unit_id=element.unit_id,
        space_id=element.space_id,
        confidence_score=confidence,
        evidence_refs=list(element.evidence_refs),
        raw_entity_ids=list(element.raw_entity_ids),
    )


def evaluate_semantic_quality(building: SemanticBuilding) -> QualityReport:
    issues = [_evaluate_element(element, discipline=building.discipline) for element in building.elements]
    ok_count = sum(1 for issue in issues if issue.status == "OK")
    warning_count = sum(1 for issue in issues if issue.status == "WARNING")
    blocked_count = sum(1 for issue in issues if issue.status == "BLOCKED")
    return QualityReport(
        discipline=building.discipline,
        total_elements=len(issues),
        ok_count=ok_count,
        warning_count=warning_count,
        blocked_count=blocked_count,
        issues=issues,
    )


def _coerce_report_payload(report: QualityReport | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(report, QualityReport):
        return report.to_dict()
    return dict(report)


def write_quality_report_json(report: QualityReport | Mapping[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _coerce_report_payload(report)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_input_gaps_markdown(report: QualityReport | Mapping[str, Any], output_path: str | Path) -> Path:
    payload = _coerce_report_payload(report)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    summary = dict(payload.get("summary", {}))
    issues = list(payload.get("issues", []))
    blocked = [issue for issue in issues if issue.get("status") == "BLOCKED"]
    warnings = [issue for issue in issues if issue.get("status") == "WARNING"]

    lines = [
        "# INPUT GAPS",
        "",
        f"- Disciplina: **{payload.get('discipline', '')}**",
        f"- Total elementos evaluados: **{summary.get('total_elements', 0)}**",
        f"- OK: **{summary.get('ok_count', 0)}**",
        f"- WARNING: **{summary.get('warning_count', 0)}**",
        f"- BLOCKED: **{summary.get('blocked_count', 0)}**",
        "",
        "## Elementos bloqueados",
    ]

    if not blocked:
        lines.append("- Ninguno")
    else:
        for issue in blocked:
            lines.append(
                f"- `{issue.get('element_id')}` ({issue.get('code')}): {issue.get('message')}"
                + (
                    f" | Acción: {issue.get('suggested_action')}"
                    if issue.get("suggested_action")
                    else ""
                )
            )

    lines.extend(["", "## Advertencias"])
    if not warnings:
        lines.append("- Ninguna")
    else:
        for issue in warnings:
            lines.append(f"- `{issue.get('element_id')}` ({issue.get('code')}): {issue.get('message')}")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path
