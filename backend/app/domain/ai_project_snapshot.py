from __future__ import annotations

from app.domain.ai_project_snapshot_data import ProjectSnapshotData
from app.domain.project_kind import ProjectKind
from app.domain.workflow_phase import WorkflowPhase, normalize_workflow_phase
from app.models.project import Project

WORKFLOW_PHASE_ORDER: tuple[WorkflowPhase, ...] = (
    WorkflowPhase.AWAITING_FILES,
    WorkflowPhase.ARCHITECTURE_REVIEW,
    WorkflowPhase.SPECIFICATIONS,
    WorkflowPhase.BUDGETING_PIPELINE,
    WorkflowPhase.MANAGEMENT_APPROVAL,
    WorkflowPhase.BUDGET_APPROVED,
    WorkflowPhase.COMPLETE,
)

_PHASE_SECTION_LABELS: dict[WorkflowPhase, str] = {
    WorkflowPhase.AWAITING_FILES: "Archivos CAD",
    WorkflowPhase.ARCHITECTURE_REVIEW: "Revisión de arquitectura",
    WorkflowPhase.SPECIFICATIONS: "Pliego de condiciones",
    WorkflowPhase.BUDGETING_PIPELINE: "Presupuesto operativo",
    WorkflowPhase.MANAGEMENT_APPROVAL: "Aprobación de gerencia",
    WorkflowPhase.BUDGET_APPROVED: "Presupuesto aprobado por cliente",
    WorkflowPhase.COMPLETE: "Completo",
}

_PHASE_LABELS_ES: dict[str, str] = {
    WorkflowPhase.AWAITING_FILES.value: "Esperando archivos CAD",
    "FILES_INGESTED": "Archivos ingresados",
    WorkflowPhase.ARCHITECTURE_REVIEW.value: "Revisión de arquitectura",
    WorkflowPhase.SPECIFICATIONS.value: "Pliego de condiciones",
    WorkflowPhase.BUDGETING_PIPELINE.value: "Presupuesto (cotización / volumetría / costo)",
    WorkflowPhase.MANAGEMENT_APPROVAL.value: "Aprobación de gerencia",
    WorkflowPhase.BUDGET_APPROVED.value: "Presupuesto aprobado por cliente",
    WorkflowPhase.COMPLETE.value: "Completo",
    WorkflowPhase.CUSTOM_AUTOMATION.value: "Automatización",
}

_KIND_LABELS_ES: dict[str, str] = {
    ProjectKind.CLIENT.value: "Cliente",
    ProjectKind.TENDER.value: "Licitación",
    ProjectKind.DEVELOPMENT.value: "Desarrollo",
}

_STATUS_LABEL_ES = {
    "completo": "completo",
    "en_curso": "en curso",
    "pendiente": "pendiente",
    "no_aplica": "no aplica",
}

_BUDGET_FLAG_LABELS = [
    ("subcontracts_done", "Cotizaciones de subcontratación"),
    ("volumetry_done", "Volumetría"),
    ("cost_analysis_done", "Análisis de costo"),
    ("budget_marked_complete", "Presupuesto interno listo"),
    ("control_review_done", "Revisión de Control"),
]


def phase_status(section: WorkflowPhase, current: WorkflowPhase) -> str:
    """completo | en_curso | pendiente | no_aplica — by index in linear flow."""
    if section not in WORKFLOW_PHASE_ORDER:
        return "no_aplica"
    if current == WorkflowPhase.CUSTOM_AUTOMATION:
        return "completo"
    if current not in WORKFLOW_PHASE_ORDER:
        return "no_aplica"
    si = WORKFLOW_PHASE_ORDER.index(section)
    ci = WORKFLOW_PHASE_ORDER.index(current)
    if si < ci:
        return "completo"
    if si == ci:
        return "en_curso"
    return "pendiente"


def truncate_snapshot(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    marker = "### Qué falta para avanzar al siguiente paso"
    idx = text.find(marker)
    if idx == -1:
        return text[: max_chars - 1] + "…"
    tail = text[idx:]
    ellipsis = "\n…(detalle recortado por límite de contexto)\n\n"
    head_budget = max_chars - len(tail) - len(ellipsis)
    if head_budget < 400:
        combined = text[: max_chars - 1] + "…"
        return combined[:max_chars]
    combined = text[:head_budget] + ellipsis + tail
    if len(combined) > max_chars:
        return combined[: max_chars - 1] + "…"
    return combined


def _current_phase(project: Project) -> WorkflowPhase:
    return normalize_workflow_phase(project.workflow_phase)


def _section_header(phase: WorkflowPhase, current: WorkflowPhase, index: int) -> str:
    label = _PHASE_SECTION_LABELS[phase]
    status = _STATUS_LABEL_ES[phase_status(phase, current)]
    return f"#### {index}. {label} — {status}"


def _files_section(data: ProjectSnapshotData) -> list[str]:
    f = data.files
    lines = [
        f"- Total archivos: {f.total}",
        f"- Carpetas: {f.folder_count}",
    ]
    if f.by_discipline:
        parts = [f"{k}: {v}" for k, v in sorted(f.by_discipline.items())]
        lines.append(f"- Por disciplina: {', '.join(parts)}")
    if f.recent_names:
        lines.append(f"- Recientes: {', '.join(f.recent_names)}")
    if f.total >= 1:
        lines.append("- Requisito para avanzar desde «Esperando archivos»: cumplido.")
    else:
        lines.append("- Requisito para avanzar: falta al menos un archivo.")
    return lines


def _revision_section(data: ProjectSnapshotData) -> list[str]:
    rev = data.revision
    if rev is None:
        return ["- Sin revisiones registradas."]
    return [
        f"- Última revisión: versión {rev.version}",
        f"- Decisión: {rev.decision_es}",
    ]


def _pliego_section(data: ProjectSnapshotData) -> list[str]:
    p = data.pliego
    lines = [
        f"- Modo activo: {p.mode}",
        f"- GA-FO-01: {p.ga_fo_complete} de {p.ga_fo_total} documentos en estado final",
        f"- Pliego aprobado: {'sí' if p.approved else 'no'}",
    ]
    if p.blocker_message:
        lines.append(f"- Bloqueo para presupuesto: {p.blocker_message}")
    return lines


def _budget_section(data: ProjectSnapshotData) -> list[str]:
    bp = data.budget_pipeline
    lines: list[str] = []
    for key, human in _BUDGET_FLAG_LABELS:
        if key in bp:
            lines.append(f"- {human}: {'sí' if bp.get(key) else 'no'}")
    vers = bp.get("client_approved_version_label")
    if isinstance(vers, str) and vers.strip():
        lines.append(f"- Versión aprobada por cliente: {vers.strip()}")
    lines.append(f"- Líneas de cotización de subcontrato: {data.subcontract_line_count}")
    job = data.budget_job
    if job is None:
        lines.append("- Presupuesto maestro (IA): sin jobs registrados.")
    else:
        lines.append(f"- Presupuesto maestro (IA): estado {job.status}")
        if job.discipline:
            lines.append(f"  - Disciplina del último job: {job.discipline}")
        if job.row_count is not None:
            lines.append(f"  - Partidas en resultado: {job.row_count}")
    return lines


def _management_section(data: ProjectSnapshotData) -> list[str]:
    return [
        f"- Revisión de Gerencia (desde fase aprobación): "
        f"{'sí' if data.gerencia_review_since_management else 'no'}",
    ]


def _transversal_section(data: ProjectSnapshotData) -> list[str]:
    c = data.clashes
    lines = [
        f"- Tareas pendientes en tablero (bloquean avance): {data.pending_tasks}",
        f"- Hallazgos técnicos manuales: {data.technical_findings_count}",
        f"- Entrega de planos (SDP): {data.plan_delivery.pending} pendiente(s) de {data.plan_delivery.total}",
        f"- Base de precios: {data.price_database.file_count} archivo(s)",
    ]
    if data.price_database.last_confirmed_at:
        lines.append(f"  - Última confirmación: {data.price_database.last_confirmed_at}")
    if c.latest_job_status:
        smoke = " (modo demo)" if c.smoke_mode else ""
        lines.append(
            f"- Coordinación / hallazgos CAD: job {c.latest_job_status}{smoke}, "
            f"{c.open_clash_count} abierto(s) de {c.total_clash_count}"
        )
    else:
        lines.append("- Coordinación / hallazgos CAD: sin análisis registrado")
    return lines


def _phase_body(phase: WorkflowPhase, data: ProjectSnapshotData) -> list[str]:
    if phase == WorkflowPhase.AWAITING_FILES:
        return _files_section(data)
    if phase == WorkflowPhase.ARCHITECTURE_REVIEW:
        return _revision_section(data)
    if phase == WorkflowPhase.SPECIFICATIONS:
        return _pliego_section(data)
    if phase == WorkflowPhase.BUDGETING_PIPELINE:
        return _budget_section(data)
    if phase == WorkflowPhase.MANAGEMENT_APPROVAL:
        return _management_section(data)
    if phase == WorkflowPhase.BUDGET_APPROVED:
        bp = data.budget_pipeline
        return [
            "- Presupuesto aprobado por el cliente en el flujo.",
            f"- Versión cliente: {(bp.get('client_approved_version_label') or '—')}",
        ]
    if phase == WorkflowPhase.COMPLETE:
        return ["- El flujo lineal del proyecto está en etapa final."]
    return []


def build_project_snapshot_markdown(
    project: Project,
    data: ProjectSnapshotData,
    *,
    max_chars: int = 8000,
) -> str:
    """Spanish markdown for the model (not for literal user copy)."""
    current = _current_phase(project)
    phase_key = project.workflow_phase or ""
    phase_human = _PHASE_LABELS_ES.get(phase_key, phase_key.replace("_", " ").lower() or "sin dato")
    kind_human = _KIND_LABELS_ES.get(project.project_kind, project.project_kind)
    step_title = ""
    if project.current_workflow_step is not None:
        step_title = (project.current_workflow_step.title or "").strip()

    summary_lines: list[str] = [
        "### Resumen del proyecto",
        f"- **Nombre:** {project.name}",
        f"- **Cliente:** {project.client_name or '—'}",
        f"- **Tipo:** {kind_human}",
        f"- **Etapa actual del flujo:** {phase_human}",
    ]
    if step_title:
        summary_lines.append(f"- **Paso en plantilla:** {step_title}")
    if project.project_code:
        summary_lines.append(f"- **Código interno:** {project.project_code}")
    if project.location_text:
        summary_lines.append(f"- **Ubicación:** {project.location_text}")
    if project.deadline is not None:
        summary_lines.append(f"- **Fecha límite:** {project.deadline.isoformat()}")
    if project.estimated_area_sqm is not None:
        summary_lines.append(f"- **Superficie estimada (m²):** {project.estimated_area_sqm}")
    if project.floor_levels_count is not None:
        summary_lines.append(f"- **Niveles / pisos:** {project.floor_levels_count}")
    ext_resp = project.responsible_external_name or project.responsible_external_email
    if ext_resp:
        summary_lines.append(f"- **Responsable externo:** {ext_resp}")
    if data.members:
        names = ", ".join(m.display_name for m in data.members[:8])
        extra = len(data.members) - 8
        if extra > 0:
            names += f" (+{extra} más)"
        summary_lines.append(f"- **Equipo con acceso:** {names}")
    else:
        summary_lines.append(f"- **Personas con acceso:** {len(data.members)}")

    parts: list[str] = ["\n".join(summary_lines), "", "### Estado por fase del flujo"]
    for i, phase in enumerate(WORKFLOW_PHASE_ORDER, start=1):
        parts.append("")
        parts.append(_section_header(phase, current, i))
        parts.extend(_phase_body(phase, data))

    parts.extend(["", "### Áreas transversales del workspace"])
    parts.extend(_transversal_section(data))

    parts.extend(["", "### Qué falta para avanzar al siguiente paso"])
    for hint in data.transition_hints:
        parts.append(f"- {hint}")

    parts.append("")
    parts.append(
        "Usá estos datos para preguntas sobre **este proyecto**. Si falta un detalle, "
        "decilo y orientá al usuario a la pestaña correspondiente."
    )

    text = "\n".join(parts)
    return truncate_snapshot(text, max_chars)
