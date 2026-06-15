from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.business_pliego import (
    BUSINESS_PLIEGO_KEY,
    BUSINESS_PLIEGO_SCHEMA_VERSION,
    BUSINESS_PLIEGO_SECTION_KEYS,
    SECTION_ASSUMPTIONS,
    SECTION_DOCS,
    SECTION_EXCLUSIONS,
    SECTION_MATERIALS,
    SECTION_RESTRICTIONS,
    SECTION_RISKS,
    SECTION_SCOPE,
    SECTION_SPECS,
    SECTION_SYSTEMS,
    default_empty_sections,
    get_business_pliego_block,
    sections_dict,
)
from app.models.architecture_revision import ArchitectureRevision
from app.models.project import Project
from app.models.project_file import ProjectFile
from app.models.project_technical_finding import ProjectTechnicalFinding


def _fmt_project_header(p: Project) -> str:
    lines = [
        f"Nombre: {p.name}",
        f"Tipo: {p.project_kind}",
    ]
    if p.project_code:
        lines.append(f"Código: {p.project_code}")
    if p.client_name:
        lines.append(f"Cliente: {p.client_name}")
    if p.location_text:
        lines.append(f"Ubicación: {p.location_text}")
    if p.estimated_area_sqm is not None:
        lines.append(f"Área estimada (m²): {p.estimated_area_sqm}")
    if p.floor_levels_count is not None:
        lines.append(f"Niveles: {p.floor_levels_count}")
    if p.deadline is not None:
        lines.append(f"Plazo / fecha límite: {p.deadline.isoformat()}")
    return "\n".join(lines)


def _groups_to_spec_text(groups: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for g in groups:
        if not isinstance(g, dict):
            continue
        title = str(g.get("title", "") or "").strip() or "Grupo"
        kind = str(g.get("kind", "") or "").strip()
        head = f"- {title}" + (f" ({kind})" if kind else "")
        lines.append(head)
        for it in g.get("items") or []:
            if not isinstance(it, dict):
                continue
            desc = str(it.get("descripcion", "") or "").strip()
            part = str(it.get("partida", "") or it.get("id", "") or "").strip()
            if desc or part:
                lines.append(f"  · {part}: {desc}")
    return "\n".join(lines) if lines else "Sin partidas en el documento de arquitectura."


def _materiales_text(mats: list[Any]) -> str:
    if not mats:
        return "Sin materiales registrados en arquitectura."
    out: list[str] = []
    for m in mats:
        if isinstance(m, dict):
            label = str(m.get("label", m.get("nombre", "")) or "").strip() or "Material"
            extra = m.get("notas") or m.get("notes")
            if extra:
                out.append(f"- {label}: {extra}")
            else:
                out.append(f"- {label}")
        else:
            out.append(f"- {m!s}")
    return "\n".join(out)


def _documentary_text(criteria: list[dict[str, Any]], files: list[ProjectFile]) -> str:
    lines: list[str] = []
    required = [c for c in criteria if isinstance(c, dict) and c.get("required")]
    done_req = sum(1 for c in required if c.get("done"))
    total_req = len(required)
    pct = int(round(100 * done_req / total_req)) if total_req else 0
    lines.append(f"Checklist (ítems requeridos): {done_req} de {total_req} completados ({pct}%).")
    for item in criteria:
        if not isinstance(item, dict):
            continue
        lab = str(item.get("label", "")).strip() or "Ítem"
        ok = "Listo" if item.get("done") else "Pendiente"
        req = "Sí" if item.get("required") else "No"
        lines.append(f"- [{ok}] {lab} (obligatorio: {req})")
    names_norm = [f.original_name.strip().lower() for f in files]
    dup = Counter(names_norm)
    dups = [n for n, k in dup.items() if k > 1 and n]
    lines.append("")
    lines.append(f"Archivos cargados ({len(files)}):")
    if dups:
        lines.append("Posibles duplicados por nombre: " + ", ".join(dups[:15]))
    if not files:
        lines.append("- Ninguno.")
    else:
        for f in files:
            disc = f.discipline or "—"
            lines.append(f"- {f.original_name} | disciplina: {disc} | ingestión: {f.ingest_status}")
    return "\n".join(lines)


def _findings_restriction_text(findings: list[ProjectTechnicalFinding]) -> str:
    if not findings:
        return "No hay hallazgos técnicos registrados."
    arch = [f for f in findings if "ARQUIT" in f.discipline.upper() or f.discipline.upper() in ("A", "ARQ")]
    use = arch if arch else findings
    lines: list[str] = []
    for f in use:
        lines.append(f"- [{f.severity}] {f.title}: {f.description.strip()[:500]}")
    return "\n".join(lines)


def _findings_risks_text(findings: list[ProjectTechnicalFinding]) -> str:
    if not findings:
        return "Sin riesgos derivados de hallazgos; validar con obra."
    heavy = [f for f in findings if f.severity.upper() in ("ALTA", "ALTO", "HIGH", "CRITICAL", "CRITICO")]
    use = heavy if heavy else findings
    lines: list[str] = []
    for f in use:
        lines.append(f"- ({f.severity}) {f.title}")
    return "\n".join(lines)


class PliegoBusinessService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_project(self, project_id: UUID) -> Project:
        return await self._load_project_internal(project_id)

    async def _load_project_internal(self, project_id: UUID) -> Project:
        q = (
            select(Project)
            .options(
                selectinload(Project.architecture_data),
            )
            .where(Project.id == project_id)
        )
        row = (await self._session.execute(q)).scalar_one_or_none()
        if row is None:
            raise ValueError("project not found")
        return row

    async def _files_for_project(self, project_id: UUID) -> list[ProjectFile]:
        q = select(ProjectFile).where(ProjectFile.project_id == project_id).order_by(ProjectFile.created_at.asc())
        return list((await self._session.execute(q)).scalars().all())

    async def _findings_for_project(self, project_id: UUID) -> list[ProjectTechnicalFinding]:
        q = select(ProjectTechnicalFinding).where(
            ProjectTechnicalFinding.project_id == project_id
        )
        return list((await self._session.execute(q)).scalars().all())

    async def _latest_arch_revision(self, project_id: UUID) -> Optional[ArchitectureRevision]:
        q = (
            select(ArchitectureRevision)
            .where(ArchitectureRevision.project_id == project_id)
            .order_by(ArchitectureRevision.version.desc())
            .limit(1)
        )
        return (await self._session.execute(q)).scalar_one_or_none()

    def build_sections_dict(
        self,
        project: Project,
        files: list[ProjectFile],
        findings: list[ProjectTechnicalFinding],
    ) -> dict[str, str]:
        crit: list[dict[str, Any]] = project.project_bootstrap_criteria or []
        if not isinstance(crit, list):
            crit = []

        arch_doc: dict[str, Any] = {}
        materiales: list[Any] = []
        if project.architecture_data is not None:
            arch_doc = project.architecture_data.document or {}
            materiales = project.architecture_data.materiales or []
        groups = arch_doc.get("groups") if isinstance(arch_doc, dict) else []
        if not isinstance(groups, list):
            groups = []

        scope = _fmt_project_header(project)
        spec_text = _groups_to_spec_text([g for g in groups if isinstance(g, dict)])
        mats = _materiales_text(materiales)
        systems = _groups_to_spec_text([g for g in groups if isinstance(g, dict)])

        crit_done = [c for c in crit if isinstance(c, dict) and c.get("required") and c.get("done")]

        total_req = len([c for c in crit if isinstance(c, dict) and c.get("required")])
        assump = (
            f"Se asume coherencia entre la documentación cargada y el alcance acordado. "
            f"Checklist obligatorio: {len(crit_done)}/{total_req} ítems requeridos marcados listos. "
            f"Validar con visita de obra si aplica."
        )
        excl = (
            "Pendiente de ajuste por negocio: exclusiones de alcance, "
            "suministros por terceros y obras civiles no incluidas, salvo indicación en contrato."
        )

        return {
            SECTION_SCOPE: scope,
            SECTION_SPECS: spec_text,
            SECTION_MATERIALS: mats,
            SECTION_SYSTEMS: systems
            or "Sistemas y fases a definir según documento de arquitectura y partidas anteriores.",
            SECTION_RESTRICTIONS: _findings_restriction_text(findings),
            SECTION_ASSUMPTIONS: assump,
            SECTION_EXCLUSIONS: excl,
            SECTION_DOCS: _documentary_text(
                [c for c in crit if isinstance(c, dict)],
                files,
            ),
            SECTION_RISKS: _findings_risks_text(findings),
        }

    async def build_draft_block(self, project: Project) -> dict[str, Any]:
        files = await self._files_for_project(project.id)
        findings = await self._findings_for_project(project.id)
        sections = self.build_sections_dict(project, files, findings)
        rev = await self._latest_arch_revision(project.id)
        arch_notes = ""
        if rev is not None and rev.notes and str(rev.notes).strip():
            arch_notes = f"\n\nNotas de la última revisión de arquitectura: {str(rev.notes).strip()}"

        s = dict(sections)
        s[SECTION_SCOPE] = (s.get(SECTION_SCOPE) or "") + arch_notes
        for k in BUSINESS_PLIEGO_SECTION_KEYS:
            t = s.get(k, "")
            if len(t.strip()) < 15:
                s[k] = (t.strip() + f"\n\n(Completar sección: {k})").strip()

        return {
            "schema_version": BUSINESS_PLIEGO_SCHEMA_VERSION,
            "sections": s,
            "approved": False,
            "approved_at": None,
            "approved_by_user_uuid": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def merge_draft_into_spec(
        self,
        current_spec: dict[str, Any],
        new_block: dict[str, Any],
    ) -> dict[str, Any]:
        out: dict[str, Any] = dict(current_spec) if current_spec else {}
        out[BUSINESS_PLIEGO_KEY] = new_block
        if not (out.get("summary") and str(out["summary"]).strip()):
            sec = new_block.get("sections") if isinstance(new_block.get("sections"), dict) else {}
            scope_preview = str(sec.get(SECTION_SCOPE) or "")[:200]
            if scope_preview:
                out["summary"] = scope_preview.replace("\n", " ")
        return out
