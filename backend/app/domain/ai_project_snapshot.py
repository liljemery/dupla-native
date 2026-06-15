from __future__ import annotations

from typing import Any

from app.domain.project_kind import ProjectKind
from app.models.project import Project

_PHASE_LABELS_ES: dict[str, str] = {
    "BOOTSTRAPPING": "Arranque (checklist inicial)",
    "AWAITING_FILES": "Esperando archivos",
    "FILES_INGESTED": "Archivos recibidos",
    "ARCHITECTURE_REVIEW": "Revisión de arquitectura",
    "SPECIFICATIONS": "Pliego / especificaciones",
    "BUDGETING_PIPELINE": "Presupuesto (pipeline)",
    "MANAGEMENT_APPROVAL": "Aprobación de gerencia",
    "BUDGET_APPROVED": "Presupuesto aprobado por el cliente",
    "COMPLETE": "Flujo completado",
    "CUSTOM_AUTOMATION": "Paso de flujo",
}

_KIND_LABELS_ES: dict[str, str] = {
    ProjectKind.CLIENT.value: "Cliente",
    ProjectKind.TENDER.value: "Licitación",
    ProjectKind.DEVELOPMENT.value: "Desarrollo",
}


def _bootstrap_lines(criteria: list[Any]) -> tuple[str, list[str]]:
    if not isinstance(criteria, list):
        return "", []
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
    if req_total > 0:
        head = f"Checklist de documentos (obligatorios): {req_done} de {req_total} cumplidos.\n"
    elif lines:
        head = "Checklist de documentos:\n"
    else:
        head = "Checklist de documentos: vacía.\n"
    return head, lines


def _budget_pipeline_es(meta: dict[str, Any]) -> list[str]:
    bp = meta.get("budget_pipeline")
    if not isinstance(bp, dict):
        return []
    labels = [
        ("subcontracts_done", "Cotizaciones de subcontratación"),
        ("volumetry_done", "Volumetría"),
        ("cost_analysis_done", "Análisis de costo"),
        ("budget_marked_complete", "Presupuesto interno marcado como listo"),
        ("control_review_done", "Revisión de Control"),
    ]
    out: list[str] = []
    for key, human in labels:
        if key in bp:
            ok = bool(bp.get(key))
            out.append(f"- {human}: {'sí' if ok else 'no'}")
    vers = bp.get("client_approved_version_label")
    if isinstance(vers, str) and vers.strip():
        out.append(f"- Versión aprobada por el cliente (etiqueta): {vers.strip()}")
    return out


def build_project_snapshot_markdown(
    project: Project,
    *,
    file_count: int,
    member_count: int,
) -> str:
    """Texto en español claro para el modelo (no exponer como respuesta literal al usuario)."""
    phase_key = project.workflow_phase or ""
    phase_human = _PHASE_LABELS_ES.get(phase_key, phase_key.replace("_", " ").lower() or "sin dato")
    kind_human = _KIND_LABELS_ES.get(project.project_kind, project.project_kind)
    step_title = ""
    if project.current_workflow_step is not None:
        step_title = (project.current_workflow_step.title or "").strip()

    lines_out: list[str] = [
        f"- **Nombre del proyecto:** {project.name}",
        f"- **Cliente:** {project.client_name or '—'}",
        f"- **Tipo:** {kind_human}",
        f"- **Etapa del flujo:** {phase_human}",
    ]
    if step_title:
        lines_out.append(f"- **Paso actual en la plantilla:** {step_title}")
    if project.project_code:
        lines_out.append(f"- **Código interno:** {project.project_code}")
    if project.location_text:
        lines_out.append(f"- **Ubicación:** {project.location_text}")
    if project.deadline is not None:
        lines_out.append(f"- **Fecha límite:** {project.deadline.isoformat()}")
    if project.estimated_area_sqm is not None:
        lines_out.append(f"- **Superficie estimada (m²):** {project.estimated_area_sqm}")
    if project.floor_levels_count is not None:
        lines_out.append(f"- **Niveles / pisos:** {project.floor_levels_count}")

    ext_resp = project.responsible_external_name or project.responsible_external_email
    if ext_resp:
        lines_out.append("- **Responsable externo:** indicado en el proyecto")

    lines_out.append(f"- **Archivos subidos al proyecto:** {file_count}")
    lines_out.append(f"- **Personas con acceso al proyecto:** {member_count}")

    crit_intro, crit_lines = _bootstrap_lines(project.project_bootstrap_criteria or [])
    section_bootstrap = crit_intro + ("\n".join(crit_lines) if crit_lines else "")

    specs = project.specifications_document
    if isinstance(specs, dict) and len(specs) > 0:
        spec_note = "Hay datos cargados en el apartado de especificaciones / pliego."
    else:
        spec_note = "El apartado de especificaciones está vacío o sin datos guardados."

    meta = project.workflow_meta if isinstance(project.workflow_meta, dict) else {}
    bp_lines = _budget_pipeline_es(meta)

    parts = [
        "\n".join(lines_out),
        "",
        "### Checklist de arranque",
        section_bootstrap or "(vacío)",
        "",
        "### Especificaciones",
        spec_note,
    ]
    if bp_lines:
        parts.extend(["", "### Avance del presupuesto (hitos)", "\n".join(bp_lines)])

    parts.append("")
    parts.append(
        "Respondé sobre **este proyecto** usando estos datos. Si falta un dato aquí, "
        "decí que no figura y orientá al usuario a revisarlo en la pantalla correspondiente."
    )
    return "\n".join(parts)
