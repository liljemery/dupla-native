from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.domain.budget_pipeline_meta import get_budget_pipeline
from app.domain.business_pliego import (
    get_business_pliego_block,
    transition_blockers_for_business_pliego,
)
from app.domain.construction_pliego import construction_pliego_is_active
from app.domain.ga_fo_01_arquitectura import (
    GA_FO_SPEC_KEY,
    expected_ga_fo_item_ids,
    ga_fo_block_approved,
)
from app.domain.management_approval_review import project_has_gerencia_review_for_current_phase
from app.domain.workflow_automation_tasks import automation_card_uuids, legacy_automation_titles
from app.domain.workflow_phase import LINEAR_NEXT, WorkflowPhase, normalize_workflow_phase
from app.models.architecture_revision import ArchitectureRevision, ArchitectureRevisionDecision
from app.models.plan_delivery_request import PlanDeliveryRequest
from app.models.project import Project
from app.models.project_budget_job import ProjectBudgetJob
from app.models.project_clash_item import ProjectClashItem
from app.models.project_clash_job import ProjectClashJob
from app.models.project_file import ProjectFile
from app.models.project_file_folder import ProjectFileFolder
from app.models.project_member import ProjectMember
from app.models.project_price_database_file import ProjectPriceDatabaseFile
from app.models.project_technical_finding import ProjectTechnicalFinding
from app.models.subcontract_quote import SubcontractQuote, SubcontractQuoteLine
from app.models.task_board import TaskCard, TaskList
from app.models.user import User

_CLOSED_CLASH_STATUSES = frozenset({"resolved", "false_positive", "closed"})
_PENDING_PLAN_STATUSES = frozenset({"SOLICITADO", "EN_PROCESO", "PENDIENTE"})

_REVISION_DECISION_ES = {
    ArchitectureRevisionDecision.APPROVED.value: "aprobada",
    ArchitectureRevisionDecision.REJECTED.value: "rechazada",
    ArchitectureRevisionDecision.PARTIAL.value: "parcial",
}


@dataclass
class MemberSummary:
    display_name: str
    email: str


@dataclass
class BootstrapSummary:
    required_done: int
    required_total: int
    all_required_ok: bool
    has_criteria: bool
    item_lines: list[str] = field(default_factory=list)


@dataclass
class FilesSummary:
    total: int
    folder_count: int
    by_discipline: dict[str, int] = field(default_factory=dict)
    recent_names: list[str] = field(default_factory=list)


@dataclass
class RevisionSummary:
    version: int
    decision: str
    decision_es: str
    created_at: Optional[datetime]


@dataclass
class PliegoSummary:
    mode: str
    ga_fo_complete: int
    ga_fo_total: int
    approved: bool
    blocker_message: Optional[str]


@dataclass
class BudgetJobSummary:
    status: str
    discipline: Optional[str]
    updated_at: Optional[datetime]
    row_count: Optional[int]
    completed: bool


@dataclass
class PriceDatabaseSummary:
    file_count: int
    last_confirmed_at: Optional[str]


@dataclass
class ClashSummary:
    latest_job_status: Optional[str]
    open_clash_count: int
    total_clash_count: int
    smoke_mode: bool


@dataclass
class PlanDeliverySummary:
    total: int
    pending: int


@dataclass
class ProjectSnapshotData:
    members: list[MemberSummary]
    bootstrap: BootstrapSummary
    files: FilesSummary
    revision: Optional[RevisionSummary]
    pliego: PliegoSummary
    budget_pipeline: dict[str, Any]
    subcontract_line_count: int
    budget_job: Optional[BudgetJobSummary]
    price_database: PriceDatabaseSummary
    clashes: ClashSummary
    plan_delivery: PlanDeliverySummary
    technical_findings_count: int
    pending_tasks: int
    gerencia_review_since_management: bool = False
    transition_hints: list[str] = field(default_factory=list)


def _member_display(first: str, last: str, email: str) -> str:
    name = f"{first} {last}".strip()
    return name or email


def _bootstrap_summary(criteria: list[Any]) -> BootstrapSummary:
    if not isinstance(criteria, list):
        return BootstrapSummary(0, 0, False, False)
    req_done = 0
    req_total = 0
    lines: list[str] = []
    for item in criteria:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "Ítem").strip()
        done = bool(item.get("done"))
        req = bool(item.get("required"))
        if req:
            req_total += 1
            if done:
                req_done += 1
        estado = "cumplido" if done else "pendiente"
        suf = ", obligatorio" if req else ""
        lines.append(f"- {label}{suf}: {estado}")
    all_ok = req_total > 0 and req_done == req_total
    return BootstrapSummary(
        required_done=req_done,
        required_total=req_total,
        all_required_ok=all_ok,
        has_criteria=len(lines) > 0,
        item_lines=lines[:12],
    )


def _pliego_summary(spec: dict[str, Any] | None) -> PliegoSummary:
    if not isinstance(spec, dict):
        spec = {}
    expected = expected_ga_fo_item_ids()
    ga = spec.get(GA_FO_SPEC_KEY)
    ga_complete = 0
    if isinstance(ga, dict):
        states = ga.get("item_states")
        st_dict = states if isinstance(states, dict) else {}
        for item_id in expected:
            row = st_dict.get(item_id)
            if isinstance(row, dict) and row.get("estado") in ("COMPLETO", "NO_APLICA"):
                ga_complete += 1

    if construction_pliego_is_active(spec):
        mode = "pliego de obra (partidas)"
    elif isinstance(ga, dict) and ga.get("schema_version") == 1:
        mode = "GA-FO-01 (checklist documental)"
    elif get_business_pliego_block(spec):
        mode = "pliego estructurado (secciones)"
    elif str(spec.get("summary") or "").strip():
        mode = "resumen libre"
    else:
        mode = "sin datos"

    approved = ga_fo_block_approved(spec) or bool(get_business_pliego_block(spec).get("approved"))
    blocker = transition_blockers_for_business_pliego(spec)
    return PliegoSummary(
        mode=mode,
        ga_fo_complete=ga_complete,
        ga_fo_total=len(expected),
        approved=approved,
        blocker_message=blocker,
    )


def _budget_job_summary(job: Optional[ProjectBudgetJob]) -> Optional[BudgetJobSummary]:
    if job is None:
        return None
    row_count: Optional[int] = None
    if job.status == "completed" and isinstance(job.result, dict):
        rows = job.result.get("rows")
        if isinstance(rows, list):
            row_count = len(rows)
    return BudgetJobSummary(
        status=job.status,
        discipline=job.discipline,
        updated_at=job.updated_at,
        row_count=row_count,
        completed=job.status == "completed",
    )


def compute_phase_transition_hints(project: Project, data: ProjectSnapshotData) -> list[str]:
    """Spanish hints for advancing to the next linear workflow phase."""
    try:
        current = WorkflowPhase(project.workflow_phase)
    except ValueError:
        return []

    if current == WorkflowPhase.COMPLETE:
        return ["El flujo del proyecto está completado."]

    hints: list[str] = []

    if data.pending_tasks > 0:
        hints.append(
            f"Hay {data.pending_tasks} tarea(s) pendiente(s) en el tablero del proyecto "
            "(fuera de «Completado»). Complétalas o archívalas antes de avanzar de fase."
        )

    target = LINEAR_NEXT.get(current)
    if target is None:
        if current == WorkflowPhase.CUSTOM_AUTOMATION:
            hints.append("Estás en un paso de automatización del flujo; seguí las indicaciones del paso actual.")
        return hints

    if current == WorkflowPhase.AWAITING_FILES and target == WorkflowPhase.ARCHITECTURE_REVIEW:
        if data.files.total < 1:
            hints.append("Subí al menos un archivo de plano (DWG, DXF o PDF) en la pestaña Archivos.")
    elif current == WorkflowPhase.ARCHITECTURE_REVIEW and target == WorkflowPhase.SPECIFICATIONS:
        rev = data.revision
        if rev is None:
            hints.append("Registrá y aprobá una revisión de arquitectura en la pestaña Revisiones.")
        elif rev.decision != ArchitectureRevisionDecision.APPROVED.value:
            hints.append(
                f"La última revisión de arquitectura (v{rev.version}) no está aprobada "
                f"(estado: {rev.decision_es})."
            )
    elif current == WorkflowPhase.SPECIFICATIONS and target == WorkflowPhase.BUDGETING_PIPELINE:
        if data.pliego.blocker_message:
            hints.append(data.pliego.blocker_message)
    elif current == WorkflowPhase.BUDGETING_PIPELINE and target == WorkflowPhase.MANAGEMENT_APPROVAL:
        bp = data.budget_pipeline
        if not bp.get("control_review_done"):
            hints.append("Marca la revisión de Control en Presupuesto — Checklist antes de enviar a gerencia.")
        else:
            pending_labels: list[str] = []
            if not bp.get("subcontracts_done"):
                pending_labels.append("cotizaciones de subcontratación")
            if not bp.get("volumetry_done"):
                pending_labels.append("volumetría")
            if not bp.get("cost_analysis_done"):
                pending_labels.append("análisis de costo")
            if not bp.get("budget_marked_complete"):
                pending_labels.append("presupuesto interno marcado como listo")
            if pending_labels:
                hints.append(
                    "Completa el pipeline de presupuesto en la pestaña Presupuesto: "
                    + ", ".join(pending_labels)
                    + "."
                )
    elif current == WorkflowPhase.MANAGEMENT_APPROVAL and target == WorkflowPhase.BUDGET_APPROVED:
        if not data.gerencia_review_since_management:
            hints.append(
                "Registra una revisión con rol Gerencia en la pestaña Revisiones "
                "(después de entrar en aprobación de gerencia)."
            )

    if not hints:
        hints.append("No hay bloqueos conocidos para avanzar al siguiente paso del flujo.")
    return hints


async def _count_pending_tasks(session: AsyncSession, project: Project) -> int:
    done_title = func.lower(TaskList.title)
    done_list_ids = (
        select(TaskList.id)
        .where(
            TaskList.workspace_id == project.workspace_id,
            or_(done_title.like("%completado%"), done_title.like("%hecho%")),
        )
        .scalar_subquery()
    )
    excluded = automation_card_uuids(
        project.workflow_meta if isinstance(project.workflow_meta, dict) else None
    )
    legacy = legacy_automation_titles(
        project.workflow_meta if isinstance(project.workflow_meta, dict) else None
    )
    conditions = [
        TaskCard.project_id == project.id,
        TaskCard.archived.is_(False),
        TaskCard.list_id.not_in(done_list_ids),
    ]
    if excluded:
        conditions.append(TaskCard.id.not_in(excluded))
    if legacy:
        conditions.append(TaskCard.title.not_in(legacy))
    q = select(func.count()).select_from(TaskCard).where(*conditions)
    return int((await session.execute(q)).scalar_one() or 0)


async def load_project_snapshot_data(session: AsyncSession, project: Project) -> ProjectSnapshotData:
    project_id = project.id
    meta = project.workflow_meta if isinstance(project.workflow_meta, dict) else {}
    bp = get_budget_pipeline(meta)

    member_rows = (
        await session.execute(
            select(User.first_name, User.last_name, User.email)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project_id)
            .order_by(User.email)
            .limit(8)
        )
    ).all()
    members = [
        MemberSummary(
            display_name=_member_display(r[0], r[1], r[2]),
            email=r[2],
        )
        for r in member_rows
    ]

    bootstrap = _bootstrap_summary(project.project_bootstrap_criteria or [])

    file_total = int(
        (await session.execute(
            select(func.count()).select_from(ProjectFile).where(ProjectFile.project_id == project_id)
        )).scalar_one()
        or 0
    )
    folder_count = int(
        (await session.execute(
            select(func.count()).select_from(ProjectFileFolder).where(ProjectFileFolder.project_id == project_id)
        )).scalar_one()
        or 0
    )
    discipline_rows = (
        await session.execute(
            select(ProjectFile.discipline, func.count())
            .where(ProjectFile.project_id == project_id)
            .group_by(ProjectFile.discipline)
        )
    ).all()
    by_discipline: dict[str, int] = {}
    for disc, cnt in discipline_rows:
        key = (disc or "sin_clasificar").strip() or "sin_clasificar"
        by_discipline[key] = int(cnt)
    recent_files = (
        await session.execute(
            select(ProjectFile.original_name)
            .where(ProjectFile.project_id == project_id)
            .order_by(ProjectFile.created_at.desc())
            .limit(5)
        )
    ).scalars().all()
    files = FilesSummary(
        total=file_total,
        folder_count=folder_count,
        by_discipline=by_discipline,
        recent_names=list(recent_files),
    )

    rev_row = (
        await session.execute(
            select(ArchitectureRevision)
            .where(ArchitectureRevision.project_id == project_id)
            .order_by(ArchitectureRevision.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    revision: Optional[RevisionSummary] = None
    if rev_row is not None:
        dec = rev_row.decision.value if hasattr(rev_row.decision, "value") else str(rev_row.decision)
        revision = RevisionSummary(
            version=rev_row.version,
            decision=dec,
            decision_es=_REVISION_DECISION_ES.get(dec, dec.lower()),
            created_at=rev_row.created_at,
        )

    spec = project.specifications_document if isinstance(project.specifications_document, dict) else {}
    pliego = _pliego_summary(spec)

    subcontract_lines = int(
        (
            await session.execute(
                select(func.count(SubcontractQuoteLine.id))
                .select_from(SubcontractQuoteLine)
                .join(SubcontractQuote, SubcontractQuoteLine.quote_id == SubcontractQuote.id)
                .where(SubcontractQuote.project_id == project_id)
            )
        ).scalar_one()
        or 0
    )
    if subcontract_lines > 0 and not bp.get("subcontracts_done"):
        bp = dict(bp)
        bp["subcontracts_done"] = True

    latest_job = (
        await session.execute(
            select(ProjectBudgetJob)
            .where(ProjectBudgetJob.project_id == project_id)
            .order_by(ProjectBudgetJob.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    price_db_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(ProjectPriceDatabaseFile)
                .where(ProjectPriceDatabaseFile.project_id == project_id)
            )
        ).scalar_one()
        or 0
    )
    price_meta = meta.get("price_database")
    last_confirmed: Optional[str] = None
    if isinstance(price_meta, dict):
        raw = price_meta.get("last_confirmed_at")
        if isinstance(raw, str) and raw.strip():
            last_confirmed = raw.strip()

    latest_clash_job = (
        await session.execute(
            select(ProjectClashJob)
            .where(ProjectClashJob.project_id == project_id)
            .order_by(ProjectClashJob.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    open_clashes = 0
    total_clashes = 0
    if latest_clash_job is not None:
        clash_counts = (
            await session.execute(
                select(ProjectClashItem.status, func.count())
                .where(ProjectClashItem.job_id == latest_clash_job.id)
                .group_by(ProjectClashItem.status)
            )
        ).all()
        for status, cnt in clash_counts:
            total_clashes += int(cnt)
            if status not in _CLOSED_CLASH_STATUSES:
                open_clashes += int(cnt)

    plan_rows = (
        await session.execute(
            select(PlanDeliveryRequest.status).where(PlanDeliveryRequest.project_id == project_id)
        )
    ).scalars().all()
    plan_pending = sum(1 for s in plan_rows if s in _PENDING_PLAN_STATUSES)

    findings_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(ProjectTechnicalFinding)
                .where(ProjectTechnicalFinding.project_id == project_id)
            )
        ).scalar_one()
        or 0
    )

    pending_tasks = await _count_pending_tasks(session, project)
    settings = get_settings()
    meta = project.workflow_meta if isinstance(project.workflow_meta, dict) else {}
    gerencia_review_ok = await project_has_gerencia_review_for_current_phase(
        session,
        project_id,
        meta,
        project.workflow_phase,
    )

    data = ProjectSnapshotData(
        members=members,
        bootstrap=bootstrap,
        files=files,
        revision=revision,
        pliego=pliego,
        budget_pipeline=bp,
        subcontract_line_count=subcontract_lines,
        budget_job=_budget_job_summary(latest_job),
        price_database=PriceDatabaseSummary(file_count=price_db_count, last_confirmed_at=last_confirmed),
        clashes=ClashSummary(
            latest_job_status=latest_clash_job.status if latest_clash_job else None,
            open_clash_count=open_clashes,
            total_clash_count=total_clashes,
            smoke_mode=settings.coordination_smoke_mode,
        ),
        plan_delivery=PlanDeliverySummary(total=len(plan_rows), pending=plan_pending),
        technical_findings_count=findings_count,
        pending_tasks=pending_tasks,
        gerencia_review_since_management=gerencia_review_ok,
    )
    data.transition_hints = compute_phase_transition_hints(project, data)
    return data
