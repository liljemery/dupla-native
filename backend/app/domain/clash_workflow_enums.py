"""Domain enums for the live clash coordination workflow."""

from __future__ import annotations

from enum import Enum


class ClashStatus(str, Enum):
    DETECTED = "detected"
    NEEDS_REVIEW = "needs_review"
    CORRECTION_REQUIRED = "correction_required"
    CORRECTION_UPLOADED = "correction_uploaded"
    PENDING_REANALYSIS = "pending_reanalysis"
    RESOLVED = "resolved"
    STILL_PRESENT = "still_present"
    FALSE_POSITIVE = "false_positive"
    CLOSED = "closed"


class ReviewerDecision(str, Enum):
    CORRECT_DWG_A = "correct_dwg_a"
    CORRECT_DWG_B = "correct_dwg_b"
    CORRECT_BOTH = "correct_both"
    FALSE_POSITIVE = "false_positive"
    DESIGN_DECISION_NEEDED = "design_decision_needed"
    EXTERNAL_DISCIPLINE_REQUIRED = "external_discipline_required"
    KEEP_PENDING = "keep_pending"


class CorrectionTarget(str, Enum):
    DWG_A = "dwg_a"
    DWG_B = "dwg_b"
    BOTH = "both"


class CorrectionResult(str, Enum):
    RESOLVED = "resolved"
    STILL_PRESENT = "still_present"


class Priority(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReportConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EventType(str, Enum):
    INGESTED = "ingested"
    STATUS_CHANGE = "status_change"
    DECISION = "decision"
    ASSIGNMENT = "assignment"
    COMMENT = "comment"
    CORRECTION_UPLOAD = "correction_upload"
    REANALYSIS = "reanalysis"


STATUS_TRANSITIONS: dict[ClashStatus, frozenset[ClashStatus]] = {
    ClashStatus.DETECTED: frozenset({ClashStatus.NEEDS_REVIEW, ClashStatus.FALSE_POSITIVE}),
    ClashStatus.NEEDS_REVIEW: frozenset(
        {ClashStatus.CORRECTION_REQUIRED, ClashStatus.FALSE_POSITIVE, ClashStatus.DETECTED}
    ),
    ClashStatus.CORRECTION_REQUIRED: frozenset(
        {ClashStatus.CORRECTION_UPLOADED, ClashStatus.NEEDS_REVIEW}
    ),
    ClashStatus.CORRECTION_UPLOADED: frozenset(
        {ClashStatus.PENDING_REANALYSIS, ClashStatus.CORRECTION_REQUIRED}
    ),
    ClashStatus.PENDING_REANALYSIS: frozenset({ClashStatus.RESOLVED, ClashStatus.STILL_PRESENT}),
    ClashStatus.STILL_PRESENT: frozenset({ClashStatus.CORRECTION_REQUIRED, ClashStatus.NEEDS_REVIEW}),
    ClashStatus.RESOLVED: frozenset({ClashStatus.CLOSED, ClashStatus.STILL_PRESENT}),
    ClashStatus.FALSE_POSITIVE: frozenset({ClashStatus.CLOSED, ClashStatus.NEEDS_REVIEW}),
    ClashStatus.CLOSED: frozenset({ClashStatus.NEEDS_REVIEW}),
}

PENDING_DECISION_STATUSES: frozenset[ClashStatus] = frozenset(
    {ClashStatus.DETECTED, ClashStatus.NEEDS_REVIEW}
)

DECISION_TARGET_STATUS: dict[ReviewerDecision, ClashStatus] = {
    ReviewerDecision.CORRECT_DWG_A: ClashStatus.CORRECTION_REQUIRED,
    ReviewerDecision.CORRECT_DWG_B: ClashStatus.CORRECTION_REQUIRED,
    ReviewerDecision.CORRECT_BOTH: ClashStatus.CORRECTION_REQUIRED,
    ReviewerDecision.FALSE_POSITIVE: ClashStatus.FALSE_POSITIVE,
    ReviewerDecision.DESIGN_DECISION_NEEDED: ClashStatus.NEEDS_REVIEW,
    ReviewerDecision.EXTERNAL_DISCIPLINE_REQUIRED: ClashStatus.NEEDS_REVIEW,
    ReviewerDecision.KEEP_PENDING: ClashStatus.NEEDS_REVIEW,
}

STATUS_LABELS_ES: dict[ClashStatus, str] = {
    ClashStatus.DETECTED: "Detectado",
    ClashStatus.NEEDS_REVIEW: "Requiere revisión",
    ClashStatus.CORRECTION_REQUIRED: "Corrección requerida",
    ClashStatus.CORRECTION_UPLOADED: "Corrección cargada",
    ClashStatus.PENDING_REANALYSIS: "Pendiente de reanálisis",
    ClashStatus.RESOLVED: "Resuelto",
    ClashStatus.STILL_PRESENT: "Persiste tras reanálisis",
    ClashStatus.FALSE_POSITIVE: "Falso positivo",
    ClashStatus.CLOSED: "Cerrado",
}

DECISION_TO_CORRECTION_TARGET: dict[ReviewerDecision, CorrectionTarget] = {
    ReviewerDecision.CORRECT_DWG_A: CorrectionTarget.DWG_A,
    ReviewerDecision.CORRECT_DWG_B: CorrectionTarget.DWG_B,
    ReviewerDecision.CORRECT_BOTH: CorrectionTarget.BOTH,
}

CORRECTION_TARGET_LABELS_ES: dict[CorrectionTarget, str] = {
    CorrectionTarget.DWG_A: "DWG A",
    CorrectionTarget.DWG_B: "DWG B",
    CorrectionTarget.BOTH: "Ambos DWG",
}

CORRECTION_RESULT_LABELS_ES: dict[CorrectionResult, str] = {
    CorrectionResult.RESOLVED: "Resuelto",
    CorrectionResult.STILL_PRESENT: "Persiste tras reanálisis",
}

DECISION_LABELS_ES: dict[ReviewerDecision, str] = {
    ReviewerDecision.CORRECT_DWG_A: "Corregir DWG A",
    ReviewerDecision.CORRECT_DWG_B: "Corregir DWG B",
    ReviewerDecision.CORRECT_BOTH: "Corregir ambos",
    ReviewerDecision.FALSE_POSITIVE: "Falso positivo",
    ReviewerDecision.DESIGN_DECISION_NEEDED: "Decisión de diseño requerida",
    ReviewerDecision.EXTERNAL_DISCIPLINE_REQUIRED: "Disciplina externa requerida",
    ReviewerDecision.KEEP_PENDING: "Mantener pendiente",
}


def can_transition(current: ClashStatus, target: ClashStatus) -> bool:
    if current == target:
        return True
    return target in STATUS_TRANSITIONS.get(current, frozenset())


def status_label(status: ClashStatus, lang: str = "es") -> str:
    if lang == "es":
        return STATUS_LABELS_ES.get(status, status.value)
    return status.value


def decision_label(decision: ReviewerDecision, lang: str = "es") -> str:
    if lang == "es":
        return DECISION_LABELS_ES.get(decision, decision.value)
    return decision.value
