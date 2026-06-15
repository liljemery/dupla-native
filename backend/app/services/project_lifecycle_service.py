from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.types import Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.config import get_settings
from app.domain.file_discipline import FileIngestStatus, parse_discipline
from app.domain.project_kind import ProjectKind
from app.domain.project_updated import touch_project_updated_at
from app.domain.project_uploads import sanitize_project_original_filename, validate_project_file_extension
from app.domain.workflow_automation_tasks import (
    append_automation_card_uuid,
    automation_card_uuids,
    legacy_automation_titles,
)
from app.domain.budget_pipeline_meta import (
    get_budget_pipeline as _budget_pipeline,
    project_has_volumetry_qualifying_job,
    set_budget_pipeline as _set_budget_pipeline,
)
from app.domain.business_pliego import (
    BUSINESS_PLIEGO_KEY,
    apply_approval,
    business_pliego_sections_equal,
    clear_approval_in_block,
    default_empty_sections,
    get_business_pliego_block,
    pliego_sections_incomplete_message,
    sections_dict,
    transition_blockers_for_business_pliego,
)
from app.domain.ga_fo_01_arquitectura import GA_FO_SPEC_KEY, apply_ga_fo_approval, clear_ga_fo_approval
from app.domain.workflow_template_phase import (
    effective_workflow_phase_for_step,
    workflow_phase_from_template_step_index,
)
from app.domain.workflow_phase import LINEAR_NEXT, LINEAR_PREV, WorkflowPhase, upload_counts_for_budget
from app.domain.user_permissions import can_view_budget, has_elevated_access
from app.models.architecture_revision import ArchitectureRevision, ArchitectureRevisionDecision
from app.models.project import Project
from app.models.task_board import TaskCard, TaskList
from app.models.project_technical_finding import ProjectTechnicalFinding
from app.models.project_event import ProjectEvent
from app.models.project_file import ProjectFile
from app.models.project_file_folder import ProjectFileFolder
from app.models.subcontract_quote import SubcontractQuote, SubcontractQuoteLine
from app.models.user import User, UserRole
from app.models.user_notification import UserNotification
from app.models.workflow_template import WorkflowTemplateStep
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.repositories.workflow_template_repository import WorkflowTemplateRepository
from app.schemas.chat import ChatPostRequest
from app.services.chat_service import ChatService
from app.services.pliego_business_service import PliegoBusinessService
from app.services.project_file_ai_service import ProjectFileAIService
from app.services.project_service import ProjectService
from app.services.task_board_service import TaskBoardService


class ProjectLifecycleService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self._session = session
        self._workspace_id = workspace_id
        self._projects = ProjectRepository(session)
        self._users = UserRepository(session)
        self._project_svc = ProjectService(session, workspace_id)
        self._workflow_templates = WorkflowTemplateRepository(session)
        self._settings = get_settings()

    @staticmethod
    def _domain_phase_for_project(project: Project) -> WorkflowPhase:
        try:
            return WorkflowPhase(project.workflow_phase)
        except ValueError:
            return WorkflowPhase.BOOTSTRAPPING

    async def _load_project_full(self, project_uuid: UUID) -> Optional[Project]:
        result = await self._session.execute(
            select(Project)
            .options(
                selectinload(Project.architecture_data),
                selectinload(Project.subcontract_quotes).selectinload(SubcontractQuote.lines),
            )
            .where(Project.id == project_uuid)
        )
        return result.scalar_one_or_none()

    async def _sync_subcontracts_flag(self, project: Project) -> None:
        meta = dict(project.workflow_meta or {})
        bp = _budget_pipeline(meta)
        has = False
        for q in project.subcontract_quotes:
            if len(q.lines) > 0:
                has = True
                break
        bp["subcontracts_done"] = has
        _set_budget_pipeline(meta, bp)
        project.workflow_meta = meta

    def _bootstrap_required_ok(self, project: Project) -> bool:
        criteria = project.project_bootstrap_criteria or []
        if not isinstance(criteria, list):
            return False
        for item in criteria:
            if not isinstance(item, dict):
                continue
            if item.get("required") and not item.get("done"):
                return False
        return len(criteria) > 0

    async def _latest_revision(self, project_id: UUID) -> Optional[ArchitectureRevision]:
        q = (
            select(ArchitectureRevision)
            .where(ArchitectureRevision.project_id == project_id)
            .order_by(ArchitectureRevision.version.desc())
            .limit(1)
        )
        return (await self._session.execute(q)).scalar_one_or_none()

    async def _next_revision_version(self, project_id: UUID) -> int:
        q = select(func.coalesce(func.max(ArchitectureRevision.version), 0)).where(
            ArchitectureRevision.project_id == project_id
        )
        v = (await self._session.execute(q)).scalar_one()
        return int(v) + 1

    async def _assert_transition_guards_pair(
        self,
        _user: User,
        project: Project,
        current: WorkflowPhase,
        target: WorkflowPhase,
    ) -> None:
        if current == WorkflowPhase.BOOTSTRAPPING and target == WorkflowPhase.AWAITING_FILES:
            if not self._bootstrap_required_ok(project):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Completa el checklist de documentos requeridos antes de continuar",
                )
        if current == WorkflowPhase.AWAITING_FILES and target == WorkflowPhase.ARCHITECTURE_REVIEW:
            n = await self._projects.count_project_files(project.id)
            if n < 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Sube al menos un archivo de plano antes de continuar",
                )
        if current == WorkflowPhase.ARCHITECTURE_REVIEW and target == WorkflowPhase.SPECIFICATIONS:
            rev = await self._latest_revision(project.id)
            if rev is None or rev.decision != ArchitectureRevisionDecision.APPROVED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Se requiere una revisión de arquitectura aprobada",
                )
        if current == WorkflowPhase.SPECIFICATIONS and target == WorkflowPhase.BUDGETING_PIPELINE:
            await self._session.refresh(project, attribute_names=["specifications_document"])
            spec = project.specifications_document or {}
            if not isinstance(spec, dict):
                spec = {}
            msg = transition_blockers_for_business_pliego(spec)
            if msg is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=msg,
                )
        if current == WorkflowPhase.BUDGETING_PIPELINE and target == WorkflowPhase.MANAGEMENT_APPROVAL:
            await self._sync_subcontracts_flag(project)
            meta = dict(project.workflow_meta or {})
            bp = _budget_pipeline(meta)
            if not (
                bp.get("subcontracts_done")
                and bp.get("volumetry_done")
                and bp.get("cost_analysis_done")
                and bp.get("budget_marked_complete")
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Completa el pipeline de presupuesto antes de enviar a gerencia",
                )
        if current == WorkflowPhase.MANAGEMENT_APPROVAL and target == WorkflowPhase.BUDGET_APPROVED:
            await self._sync_subcontracts_flag(project)
            meta = dict(project.workflow_meta or {})
            bp = _budget_pipeline(meta)
            if not (
                bp.get("subcontracts_done")
                and bp.get("volumetry_done")
                and bp.get("cost_analysis_done")
                and bp.get("budget_marked_complete")
                and (bp.get("client_approved_version_label") or "").strip()
                and bp.get("control_review_done")
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Completa el pipeline de presupuesto, la versión aprobada por el cliente "
                        "y la revisión de Control"
                    ),
                )

    async def _assert_transition_guards(
        self,
        user: User,
        project: Project,
        target: WorkflowPhase,
    ) -> None:
        current = WorkflowPhase(project.workflow_phase)
        await self._assert_transition_guards_pair(user, project, current, target)

    async def _count_pending_tasks_for_project(self, project: Project) -> int:
        done_list_ids = (
            select(TaskList.id)
            .where(
                TaskList.workspace_id == project.workspace_id,
                TaskList.title == "Hecho",
            )
            .scalar_subquery()
        )
        excluded_automation = automation_card_uuids(
            project.workflow_meta if isinstance(project.workflow_meta, dict) else None
        )
        legacy_titles = legacy_automation_titles(
            project.workflow_meta if isinstance(project.workflow_meta, dict) else None
        )
        conditions = [
            TaskCard.project_id == project.id,
            TaskCard.archived.is_(False),
            TaskCard.list_id.not_in(done_list_ids),
        ]
        if excluded_automation:
            conditions.append(TaskCard.id.not_in(excluded_automation))
        if legacy_titles:
            conditions.append(TaskCard.title.not_in(legacy_titles))
        q = select(func.count()).select_from(TaskCard).where(*conditions)
        return int((await self._session.execute(q)).scalar_one())

    def _sync_workflow_phase_denorm(
        self,
        project: Project,
        target_step: WorkflowTemplateStep,
        *,
        step_index: int,
    ) -> None:
        project.workflow_phase = effective_workflow_phase_for_step(step_index)

    async def _apply_template_forward_guards(
        self,
        user: User,
        project: Project,
        from_step_index: int,
        to_step_index: int,
    ) -> None:
        from_eff = workflow_phase_from_template_step_index(from_step_index)
        to_eff = workflow_phase_from_template_step_index(to_step_index)
        await self._assert_transition_guards_pair(
            user,
            project,
            WorkflowPhase(from_eff),
            WorkflowPhase(to_eff),
        )

    async def _run_step_enter_actions(self, actor: User, project: Project, to_step: WorkflowTemplateStep) -> None:
        raw_actions = to_step.on_enter_actions or []
        if not isinstance(raw_actions, list):
            return
        tasks_svc = TaskBoardService(self._session, self._workspace_id)
        chat_svc = ChatService(self._session, self._workspace_id)
        for raw in raw_actions:
            if not isinstance(raw, dict):
                continue
            kind = raw.get("type")
            if kind == "notify_role":
                role_str = str(raw.get("role") or "").strip().upper()
                try:
                    role_enum = UserRole(role_str)
                except ValueError:
                    continue
                mids = await self._users.list_ids_by_module_and_roles(
                    self._settings.architecture_module_id,
                    [role_enum],
                )
                title = str(raw.get("title") or "Actualización de flujo").strip()
                body = str(raw.get("body") or f"Proyecto «{project.name}».").strip()
                now = datetime.now(timezone.utc)
                for uid in mids:
                    self._session.add(
                        UserNotification(
                            user_id=uid,
                            project_id=project.id,
                            kind="WORKFLOW_STEP_ACTION",
                            title=title,
                            body=body,
                            created_at=now,
                        )
                    )
            elif kind == "create_task":
                rrole = str(raw.get("role") or "").strip().upper()
                try:
                    pref = [UserRole(rrole)]
                except ValueError:
                    pref = [UserRole.CONTROL]
                title_t = str(raw.get("title") or "Tarea de flujo").strip()
                desc = str(raw.get("description") or "").strip()
                card = await tasks_svc.create_automation_card_for_phase(
                    actor,
                    project_id=project.id,
                    title=title_t,
                    description=desc or title_t,
                    preferred_roles=pref,
                )
                if card is not None:
                    meta = dict(project.workflow_meta or {})
                    auto = append_automation_card_uuid(
                        dict(meta.get("automation_tasks") or {}),
                        card.id,
                    )
                    meta["automation_tasks"] = auto
                    project.workflow_meta = meta
            elif kind == "project_chat_message":
                body = str(raw.get("body") or "").strip()
                if not body:
                    continue
                conv_wrap = await chat_svc.get_or_create_project_conversation(actor, project.id)
                await chat_svc.post_conversation_message(
                    actor,
                    conv_wrap.uuid,
                    ChatPostRequest(body=body),
                )

    async def transition_phase(
        self,
        user: User,
        project_uuid: UUID,
        target_phase: Optional[WorkflowPhase] = None,
        *,
        target_step_uuid: Optional[UUID] = None,
    ) -> Project:
        project = await self._project_svc.get_project(user, project_uuid)
        if project.current_workflow_step is None:
            await self._session.refresh(project, ["current_workflow_step"])

        steps = await self._workflow_templates.list_steps_ordered(project.workflow_template_id)
        if not steps:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La plantilla de flujo no tiene pasos",
            )
        step_by_id = {s.id: s for s in steps}
        order_index = {s.id: i for i, s in enumerate(steps)}

        cur_step = step_by_id.get(project.current_workflow_step_id)
        if cur_step is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Paso de flujo inválido en el proyecto")
        cur_i = order_index[cur_step.id]

        target_step: Optional[WorkflowTemplateStep] = None
        if target_step_uuid is not None:
            target_step = step_by_id.get(target_step_uuid)
            if target_step is None or target_step.workflow_template_id != project.workflow_template_id:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Paso destino inválido")
        elif target_phase is not None:
            tpv = target_phase.value
            cur_eff = workflow_phase_from_template_step_index(cur_i)
            if tpv == cur_eff:
                await self._session.refresh(project, attribute_names=["current_workflow_step"])
                return project
            fwd = steps[cur_i + 1] if cur_i + 1 < len(steps) else None
            back = steps[cur_i - 1] if cur_i > 0 else None
            candidates: list[WorkflowTemplateStep] = []
            if fwd is not None and workflow_phase_from_template_step_index(cur_i + 1) == tpv:
                candidates.append(fwd)
            if back is not None and workflow_phase_from_template_step_index(cur_i - 1) == tpv:
                candidates.append(back)
            if not candidates:
                fwd_phase = (
                    workflow_phase_from_template_step_index(cur_i + 1)
                    if cur_i + 1 < len(steps)
                    else None
                )
                detail = "Transición inválida para la fase solicitada"
                if fwd_phase and tpv != fwd_phase:
                    detail = (
                        f"El proyecto ya está en «{cur_eff}». "
                        f"Para avanzar, solicita la fase «{fwd_phase}»."
                    )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=detail,
                )
            if len(candidates) > 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Hay más de un paso posible; usa target_step_uuid",
                )
            target_step = candidates[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Indica target_phase o target_step_uuid",
            )

        assert target_step is not None
        tgt_i = order_index[target_step.id]
        is_forward = tgt_i == cur_i + 1
        is_backward = tgt_i == cur_i - 1
        if not is_forward and not is_backward:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Solo se permite avanzar o retroceder un paso en el flujo",
            )

        tgt_effective_phase = effective_workflow_phase_for_step(tgt_i)
        if (
            is_backward
            and project.project_kind == ProjectKind.TENDER.value
            and tgt_effective_phase
            in (WorkflowPhase.BOOTSTRAPPING.value, WorkflowPhase.AWAITING_FILES.value)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Los proyectos de licitación no pueden retroceder por debajo de la fase "
                    "«Revisión de arquitectura»."
                ),
            )

        if is_forward and target_step.requires_approval_role:
            need = target_step.requires_approval_role.strip().upper()
            if user.role.value != need:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Se requiere aprobación del rol {need}",
                )

        if is_forward and target_step.blocked_by_step_id:
            blk = step_by_id.get(target_step.blocked_by_step_id)
            if blk is not None and cur_i < order_index[blk.id]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Este paso está bloqueado por otro paso del flujo",
                )

        if is_forward:
            pending = await self._count_pending_tasks_for_project(project)
            if pending > 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Hay tareas del proyecto pendientes en el tablero (fuera de «Hecho»). "
                        "Complétalas o archívalas antes de avanzar de fase."
                    ),
                )
            await self._apply_template_forward_guards(user, project, cur_i, tgt_i)

        prev_step_id = project.current_workflow_step_id

        project.current_workflow_step_id = target_step.id
        self._sync_workflow_phase_denorm(project, target_step, step_index=tgt_i)

        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="WORKFLOW_TRANSITION",
            payload={
                "from_phase": workflow_phase_from_template_step_index(cur_i),
                "to_phase": workflow_phase_from_template_step_index(tgt_i),
                "from_step_title": cur_step.title,
                "to_step_title": target_step.title,
                "from_step_uuid": str(prev_step_id),
                "to_step_uuid": str(target_step.id),
                "direction": "forward" if is_forward else "backward",
            },
        )

        if is_forward:
            cur_eff = workflow_phase_from_template_step_index(cur_i)
            tgt_eff = workflow_phase_from_template_step_index(tgt_i)
            if cur_eff == WorkflowPhase.ARCHITECTURE_REVIEW.value and tgt_eff == WorkflowPhase.SPECIFICATIONS.value:
                await self._notify_architecture_complete(project)
            if tgt_eff == WorkflowPhase.BUDGET_APPROVED.value:
                await self._notify_budget_approved(project)
            tgt_auto = WorkflowPhase(tgt_eff)
            await self._run_phase_automation(user, project, cur_eff, tgt_auto)
            await self._run_step_enter_actions(user, project, target_step)

        touch_project_updated_at(project)
        await self._session.flush()
        await self._session.refresh(project, attribute_names=["current_workflow_step"])
        return project

    async def _notify_architecture_complete(self, project: Project) -> None:
        mids = await self._users.list_ids_by_module_and_roles(
            self._settings.architecture_module_id,
            [UserRole.GERENCIA, UserRole.CONTROL],
        )
        title = "Fase de arquitectura completada"
        body = f"El proyecto «{project.name}» completó la definición arquitectónica."
        for uid in mids:
            self._session.add(
                UserNotification(
                    user_id=uid,
                    project_id=project.id,
                    kind="ARCHITECTURE_PHASE_COMPLETE",
                    title=title,
                    body=body,
                    created_at=datetime.now(timezone.utc),
                )
            )
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=None,
            event_type="NOTIFICATION_ARCHITECTURE_COMPLETE",
            payload={"recipient_count": len(mids)},
        )

    async def _notify_budget_approved(self, project: Project) -> None:
        mids = await self._users.list_elevated_user_ids_by_module(self._settings.architecture_module_id)
        title = "Presupuesto aprobado por el cliente"
        body = f"El proyecto «{project.name}» tiene una versión de presupuesto aprobada."
        for uid in mids:
            self._session.add(
                UserNotification(
                    user_id=uid,
                    project_id=project.id,
                    kind="BUDGET_APPROVED",
                    title=title,
                    body=body,
                    created_at=datetime.now(timezone.utc),
                )
            )
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=None,
            event_type="NOTIFICATION_BUDGET_APPROVED",
            payload={"recipient_count": len(mids)},
        )

    async def update_project_meta(self, user: User, project_uuid: UUID, patch: dict[str, Any]) -> Project:
        project = await self._project_svc.get_project(user, project_uuid)
        payload: dict[str, Any] = {}
        if "name" in patch and patch["name"] is not None:
            payload["name"] = {"from": project.name, "to": str(patch["name"]).strip()}
            project.name = str(patch["name"]).strip()
        if "client_name" in patch:
            prev = project.client_name
            nxt = str(patch["client_name"]).strip() if patch["client_name"] is not None else ""
            nxt = nxt or None
            payload["client_name"] = {"from": prev, "to": nxt}
            project.client_name = nxt
        if "project_code" in patch:
            pc = str(patch["project_code"]).strip() if patch["project_code"] is not None else ""
            pc = pc or None
            if pc is not None:
                other = await self._projects.get_by_project_code(pc, self._workspace_id)
                if other is not None and other.id != project.id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Ya existe otro proyecto con ese código",
                    )
            payload["project_code"] = {"from": project.project_code, "to": pc}
            project.project_code = pc
        if "location_text" in patch:
            lt = str(patch["location_text"]).strip() if patch["location_text"] is not None else ""
            lt = lt or None
            payload["location_text"] = {"from": project.location_text, "to": lt}
            project.location_text = lt
        if "estimated_area_sqm" in patch:
            v = patch["estimated_area_sqm"]
            if v is None:
                payload["estimated_area_sqm"] = None
                project.estimated_area_sqm = None
            else:
                dec = v if isinstance(v, Decimal) else Decimal(str(v))
                payload["estimated_area_sqm"] = str(dec)
                project.estimated_area_sqm = float(dec)
        if "floor_levels_count" in patch:
            fc = patch["floor_levels_count"]
            payload["floor_levels_count"] = fc
            project.floor_levels_count = fc if fc is not None else None
        if "deadline" in patch:
            dl_raw = patch["deadline"]
            if dl_raw is None:
                project.deadline = None
                payload["deadline"] = None
            elif isinstance(dl_raw, date):
                project.deadline = dl_raw
                payload["deadline"] = dl_raw.isoformat()
            elif isinstance(dl_raw, str):
                project.deadline = date.fromisoformat(dl_raw[:10])
                payload["deadline"] = project.deadline.isoformat()
            else:
                project.deadline = None
                payload["deadline"] = None
        if "responsible_user_uuid" in patch:
            ru = patch["responsible_user_uuid"]
            if ru is None:
                payload["responsible_user_uuid"] = None
                project.responsible_user_id = None
            else:
                uid = ru if isinstance(ru, UUID) else UUID(str(ru))
                if not await self._projects.user_is_project_team_member(project, uid):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="El responsable debe pertenecer al equipo del proyecto",
                    )
                payload["responsible_user_uuid"] = str(uid)
                project.responsible_user_id = uid
        if "responsible_external_name" in patch:
            ren = patch["responsible_external_name"]
            prev = project.responsible_external_name
            if ren is None:
                nxt = None
            else:
                s = str(ren).strip()
                nxt = s or None
            payload["responsible_external_name"] = {"from": prev, "to": nxt}
            project.responsible_external_name = nxt
        if "responsible_external_email" in patch:
            ree = patch["responsible_external_email"]
            prev = project.responsible_external_email
            if ree is None:
                nxt = None
            else:
                s = str(ree).strip()
                nxt = s or None
            payload["responsible_external_email"] = {"from": prev, "to": nxt}
            project.responsible_external_email = nxt
        if payload:
            await self._projects.record_event(
                project_id=project.id,
                actor_user_id=user.id,
                event_type="PROJECT_META_UPDATED",
                payload=payload,
            )
        touch_project_updated_at(project)
        await self._session.flush()
        return project

    async def put_bootstrap_criteria(
        self,
        user: User,
        project_uuid: UUID,
        criteria: list[dict[str, Any]],
    ) -> Project:
        project = await self._project_svc.get_project(user, project_uuid)
        if self._domain_phase_for_project(project) != WorkflowPhase.BOOTSTRAPPING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El checklist solo es editable en fase BOOTSTRAPPING",
            )
        project.project_bootstrap_criteria = criteria
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="BOOTSTRAP_UPDATED",
            payload={"items": len(criteria)},
        )
        touch_project_updated_at(project)
        await self._session.flush()
        return project

    async def put_specifications(
        self,
        user: User,
        project_uuid: UUID,
        document: dict[str, Any],
    ) -> Project:
        project = await self._project_svc.get_project(user, project_uuid)
        wf = self._domain_phase_for_project(project)
        allowed = {
            WorkflowPhase.ARCHITECTURE_REVIEW,
            WorkflowPhase.SPECIFICATIONS,
            WorkflowPhase.BUDGETING_PIPELINE,
            WorkflowPhase.MANAGEMENT_APPROVAL,
            WorkflowPhase.BUDGET_APPROVED,
        }
        if wf not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El pliego de condiciones no es editable en esta fase",
            )
        old_spec: dict[str, Any] = (
            dict(project.specifications_document) if isinstance(project.specifications_document, dict) else {}
        )
        doc: dict[str, Any] = dict(document) if isinstance(document, dict) else {}
        new_block = get_business_pliego_block(doc)
        if new_block:
            old_block = get_business_pliego_block(old_spec)
            osec = sections_dict(old_block) if old_block else default_empty_sections()
            nsec = sections_dict(new_block)
            if not business_pliego_sections_equal(osec, nsec):
                clear_approval_in_block(new_block)
            doc[BUSINESS_PLIEGO_KEY] = new_block
        old_ga = old_spec.get(GA_FO_SPEC_KEY) if isinstance(old_spec, dict) else None
        new_ga = doc.get(GA_FO_SPEC_KEY)
        if isinstance(old_ga, dict) and isinstance(new_ga, dict):
            if json.dumps(old_ga.get("item_states"), sort_keys=True, default=str) != json.dumps(
                new_ga.get("item_states"), sort_keys=True, default=str
            ):
                clear_ga_fo_approval(new_ga)
                doc[GA_FO_SPEC_KEY] = new_ga
        project.specifications_document = doc
        summary = ""
        if isinstance(doc, dict):
            summary = str((doc.get("summary") or "")).strip()
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="SPECIFICATIONS_UPDATED",
            payload={"summary_chars": len(summary)},
        )
        touch_project_updated_at(project)
        await self._session.flush()
        return project

    async def generate_business_pliego(
        self,
        user: User,
        project_uuid: UUID,
        force: bool,
    ) -> Project:
        project = await self._project_svc.get_project(user, project_uuid)
        wf = self._domain_phase_for_project(project)
        if wf not in (WorkflowPhase.ARCHITECTURE_REVIEW, WorkflowPhase.SPECIFICATIONS):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Generar pliego automático solo está disponible en fase de arquitectura o de pliego",
            )
        old_spec: dict[str, Any] = (
            dict(project.specifications_document) if isinstance(project.specifications_document, dict) else {}
        )
        old_block = get_business_pliego_block(old_spec)
        if not force and old_block and old_block.get("generated_at"):
            return project
        pbs = PliegoBusinessService(self._session)
        loaded = await pbs.load_project(project.id)
        block = await pbs.build_draft_block(loaded)
        merged = pbs.merge_draft_into_spec(old_spec, block)
        project.specifications_document = merged
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="PLIEGO_DRAFT_GENERATED",
            payload={},
        )
        touch_project_updated_at(project)
        await self._session.flush()
        return project

    async def approve_business_pliego(
        self,
        user: User,
        project_uuid: UUID,
    ) -> Project:
        if not (has_elevated_access(user) or user.role == UserRole.ARQUITECTURA):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo Gerencia, Líder de equipo o Arquitectura pueden aprobar el pliego de condiciones",
            )
        project = await self._project_svc.get_project(user, project_uuid)
        wf = self._domain_phase_for_project(project)
        if wf not in (WorkflowPhase.ARCHITECTURE_REVIEW, WorkflowPhase.SPECIFICATIONS):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La aprobación del pliego solo aplica en fase de arquitectura o de pliego",
            )
        spec: dict[str, Any] = (
            dict(project.specifications_document) if isinstance(project.specifications_document, dict) else {}
        )
        msg = pliego_sections_incomplete_message(spec)
        if msg is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=msg,
            )
        ga = spec.get(GA_FO_SPEC_KEY)
        has_ga = isinstance(ga, dict) and ga.get("schema_version") == 1
        block = get_business_pliego_block(spec)
        has_block = bool(block)
        if not has_ga and not has_block:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Falta el pliego estructurado; genere el borrador o guarde las secciones.",
            )
        if has_ga:
            apply_ga_fo_approval(ga, user.id)
            spec[GA_FO_SPEC_KEY] = ga
        if has_block:
            apply_approval(block, user.id)
            spec[BUSINESS_PLIEGO_KEY] = block
        project.specifications_document = spec
        flag_modified(project, "specifications_document")
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="PLIEGO_APPROVED",
            payload={},
        )
        touch_project_updated_at(project)
        await self._session.flush()
        return project

    async def patch_workflow_meta(
        self,
        user: User,
        project_uuid: UUID,
        patch: dict[str, Any],
    ) -> Project:
        project = await self._project_svc.get_project(user, project_uuid)
        meta = dict(project.workflow_meta or {})
        if "budget_pipeline" in patch and isinstance(patch["budget_pipeline"], dict):
            if not can_view_budget(user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="El rol Arquitectura no tiene acceso a presupuesto",
                )
            bp_old = _budget_pipeline(meta)
            incoming = patch["budget_pipeline"]
            wants_volumetry = bool(incoming.get("volumetry_done"))
            had_volumetry = bool(bp_old.get("volumetry_done"))
            if wants_volumetry and not had_volumetry and user.role != UserRole.GERENCIA:
                if not await project_has_volumetry_qualifying_job(self._session, project.id):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Ejecuta presupuesto maestro primero y espera a que genere partidas.",
                    )
            wants_true = bool(incoming.get("control_review_done"))
            had_true = bool(bp_old.get("control_review_done"))
            if wants_true and not had_true:
                if user.role != UserRole.CONTROL and not has_elevated_access(user):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Solo Control, Gerencia o Líder de equipo pueden marcar la revisión de Control",
                    )
            bp = dict(bp_old)
            bp.update(incoming)
            _set_budget_pipeline(meta, bp)
        project.workflow_meta = meta
        p = await self._load_project_full(project_uuid)
        if p is not None:
            await self._sync_subcontracts_flag(p)
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="WORKFLOW_META_PATCHED",
            payload={"keys": list(patch.keys())},
        )
        if p is not None:
            touch_project_updated_at(p)
        else:
            touch_project_updated_at(project)
        await self._session.flush()
        return await self._project_svc.get_project(user, project_uuid)

    async def list_events_page(
        self,
        user: User,
        project_uuid: UUID,
        *,
        limit: int,
        offset: int,
        event_type: Optional[str],
        q: Optional[str],
    ) -> tuple[list[ProjectEvent], int]:
        project = await self._project_svc.get_project(user, project_uuid)
        conditions = [ProjectEvent.project_id == project.id]
        if event_type and event_type.strip():
            conditions.append(ProjectEvent.event_type == event_type.strip())
        q_clean = (q or "").strip()
        if q_clean:
            pat = f"%{q_clean}%"
            conditions.append(
                or_(
                    cast(ProjectEvent.payload, Text).ilike(pat),
                    User.email.ilike(pat),
                )
            )
        base = and_(*conditions)
        count_stmt = (
            select(func.count())
            .select_from(ProjectEvent)
            .outerjoin(User, User.id == ProjectEvent.actor_user_id)
            .where(base)
        )
        total = int((await self._session.execute(count_stmt)).scalar_one() or 0)
        stmt = (
            select(ProjectEvent)
            .outerjoin(User, User.id == ProjectEvent.actor_user_id)
            .where(base)
            .order_by(ProjectEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(ProjectEvent.actor))
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        return rows, total

    async def create_architecture_revision(
        self,
        user: User,
        project_uuid: UUID,
        *,
        decision: ArchitectureRevisionDecision,
        notes: Optional[str],
        checklist: dict[str, Any],
    ) -> ArchitectureRevision:
        project = await self._project_svc.get_project(user, project_uuid)
        ver = await self._next_revision_version(project.id)
        role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
        if role_val not in {"GERENCIA", "ARQUITECTURA", "CONTROL", "PRESUPUESTO"}:
            role_val = "GERENCIA"
        rev = ArchitectureRevision(
            id=uuid.uuid4(),
            project_id=project.id,
            version=ver,
            revision_role=role_val,
            decision=decision,
            notes=notes,
            checklist=checklist or {},
            checked_by=user.id,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(rev)
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="ARCHITECTURE_REVISION",
            payload={"version": ver, "decision": decision.value, "revision_role": role_val},
        )
        touch_project_updated_at(project)
        await self._session.flush()
        await self._session.refresh(rev)
        return rev

    async def list_architecture_revisions(self, user: User, project_uuid: UUID) -> list[ArchitectureRevision]:
        project = await self._project_svc.get_project(user, project_uuid)
        q = (
            select(ArchitectureRevision)
            .where(ArchitectureRevision.project_id == project.id)
            .order_by(ArchitectureRevision.version.asc())
        )
        return list((await self._session.execute(q)).scalars().all())

    async def _require_folder_in_project(self, project_id: UUID, folder_uuid: UUID) -> UUID:
        row = await self._session.get(ProjectFileFolder, folder_uuid)
        if row is None or row.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpeta no encontrada")
        return row.id

    async def _folder_is_descendant_of(self, folder_id: UUID, ancestor_id: UUID) -> bool:
        cur = await self._session.get(ProjectFileFolder, folder_id)
        while cur is not None:
            if cur.id == ancestor_id:
                return True
            if cur.parent_id is None:
                return False
            cur = await self._session.get(ProjectFileFolder, cur.parent_id)
        return False

    async def upload_file(
        self,
        user: User,
        project_uuid: UUID,
        upload: UploadFile,
        category: Optional[str],
        *,
        folder_uuid: Optional[UUID] = None,
        wizard: bool = False,
    ) -> ProjectFile:
        project = await self._project_svc.get_project(user, project_uuid)
        wf = self._domain_phase_for_project(project)
        counts_for_budget = upload_counts_for_budget(wf)
        raw = await upload.read()
        max_bytes = self._settings.project_file_max_mb * 1024 * 1024
        if len(raw) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Archivo demasiado grande (máx. {self._settings.project_file_max_mb} MB)",
            )
        fid = uuid.uuid4()
        root = Path(self._settings.upload_root)
        dest_dir = root / str(self._workspace_id) / str(project.id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = sanitize_project_original_filename(upload.filename or "file")
        validate_project_file_extension(safe_name)
        storage_key = str(dest_dir / f"{fid}_{safe_name}")
        Path(storage_key).write_bytes(raw)

        resolved_folder_id: Optional[UUID] = None
        if folder_uuid is not None:
            resolved_folder_id = await self._require_folder_in_project(project.id, folder_uuid)

        pf = ProjectFile(
            id=fid,
            project_id=project.id,
            storage_key=storage_key,
            original_name=upload.filename or "file",
            mime=upload.content_type,
            category=category,
            folder_id=resolved_folder_id,
            counts_for_budget=counts_for_budget,
            created_by=user.id,
            created_at=datetime.now(timezone.utc),
        )
        if wizard:
            ai = ProjectFileAIService()
            disc, desc, _used = await ai.suggest(pf.original_name, pf.mime)
            pf.discipline = disc.value if disc else None
            pf.description = desc if desc else None
            pf.ingest_status = FileIngestStatus.DRAFT.value
        else:
            pf.ingest_status = FileIngestStatus.PUBLISHED.value

        self._session.add(pf)
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="FILE_UPLOADED",
            payload={"file_uuid": str(fid), "name": pf.original_name},
        )
        touch_project_updated_at(project)
        await self._session.flush()
        await self._session.refresh(pf)
        return pf

    async def count_all_project_files(self, user: User, project_uuid: UUID) -> int:
        project = await self._project_svc.get_project(user, project_uuid)
        return await self._projects.count_project_files(project.id)

    async def list_files(
        self,
        user: User,
        project_uuid: UUID,
        folder_uuid: Optional[UUID] = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ProjectFile], int]:
        project = await self._project_svc.get_project(user, project_uuid)
        if folder_uuid is not None:
            await self._require_folder_in_project(project.id, folder_uuid)
        conds = [ProjectFile.project_id == project.id]
        if folder_uuid is None:
            conds.append(ProjectFile.folder_id.is_(None))
        else:
            conds.append(ProjectFile.folder_id == folder_uuid)
        where_clause = and_(*conds)
        count_q = select(func.count()).select_from(ProjectFile).where(where_clause)
        total = int((await self._session.execute(count_q)).scalar_one())
        q = (
            select(ProjectFile)
            .where(where_clause)
            .order_by(ProjectFile.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self._session.execute(q)).scalars().all())
        return rows, total

    async def _folder_path_parts(self, project_id: UUID, folder_id: Optional[UUID]) -> list[str]:
        if folder_id is None:
            return []
        parts: list[str] = []
        cur: Optional[UUID] = folder_id
        for _ in range(128):
            if cur is None:
                break
            row = await self._session.get(ProjectFileFolder, cur)
            if row is None or row.project_id != project_id:
                break
            parts.append(row.name)
            cur = row.parent_id
        parts.reverse()
        return parts

    async def search_project_files(
        self,
        user: User,
        project_uuid: UUID,
        q_raw: Optional[str],
        discipline_raw: Optional[str],
    ) -> list[tuple[ProjectFile, str]]:
        project = await self._project_svc.get_project(user, project_uuid)
        has_q = bool(q_raw and q_raw.strip())
        has_d = bool(discipline_raw and discipline_raw.strip())
        if not has_q and not has_d:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Indica al menos un criterio: q (texto) o discipline",
            )
        stmt = select(ProjectFile).where(ProjectFile.project_id == project.id)
        if has_d:
            d = parse_discipline(discipline_raw.strip())
            if d is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="discipline no válida",
                )
            stmt = stmt.where(ProjectFile.discipline == d.value)
        if has_q:
            term = f"%{q_raw.strip()}%"
            stmt = stmt.where(
                or_(
                    ProjectFile.original_name.ilike(term),
                    ProjectFile.description.ilike(term),
                )
            )
        stmt = stmt.order_by(ProjectFile.created_at.desc())
        rows = list((await self._session.execute(stmt)).scalars().all())
        out: list[tuple[ProjectFile, str]] = []
        for pf in rows:
            parts = await self._folder_path_parts(project.id, pf.folder_id)
            path_display = "Raíz" if not parts else "Raíz / " + " / ".join(parts)
            out.append((pf, path_display))
        return out

    async def list_file_folders(
        self,
        user: User,
        project_uuid: UUID,
        parent_uuid: Optional[UUID],
    ) -> list[ProjectFileFolder]:
        project = await self._project_svc.get_project(user, project_uuid)
        q = select(ProjectFileFolder).where(ProjectFileFolder.project_id == project.id)
        if parent_uuid is None:
            q = q.where(ProjectFileFolder.parent_id.is_(None))
        else:
            await self._require_folder_in_project(project.id, parent_uuid)
            q = q.where(ProjectFileFolder.parent_id == parent_uuid)
        q = q.order_by(ProjectFileFolder.name.asc())
        return list((await self._session.execute(q)).scalars().all())

    async def create_file_folder(
        self,
        user: User,
        project_uuid: UUID,
        name: str,
        parent_uuid: Optional[UUID],
    ) -> ProjectFileFolder:
        project = await self._project_svc.get_project(user, project_uuid)
        parent_id: Optional[UUID] = None
        if parent_uuid is not None:
            parent_id = await self._require_folder_in_project(project.id, parent_uuid)
        row = ProjectFileFolder(
            id=uuid.uuid4(),
            project_id=project.id,
            parent_id=parent_id,
            name=name.strip(),
            created_by=user.id,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(row)
        touch_project_updated_at(project)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def patch_file_folder(
        self,
        user: User,
        project_uuid: UUID,
        folder_uuid: UUID,
        patch: dict[str, Any],
    ) -> ProjectFileFolder:
        project = await self._project_svc.get_project(user, project_uuid)
        row = await self._session.get(ProjectFileFolder, folder_uuid)
        if row is None or row.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpeta no encontrada")

        if "parent_uuid" in patch:
            raw_parent = patch["parent_uuid"]
            if raw_parent is None:
                row.parent_id = None
            else:
                if raw_parent == folder_uuid:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="La carpeta no puede ser padre de sí misma",
                    )
                new_parent = await self._require_folder_in_project(project.id, raw_parent)
                if await self._folder_is_descendant_of(new_parent, folder_uuid):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No se puede mover una carpeta dentro de su propia jerarquía",
                    )
                row.parent_id = new_parent

        if "name" in patch and patch["name"] is not None:
            row.name = str(patch["name"]).strip()

        touch_project_updated_at(project)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def delete_file_folder(self, user: User, project_uuid: UUID, folder_uuid: UUID) -> None:
        project = await self._project_svc.get_project(user, project_uuid)
        row = await self._session.get(ProjectFileFolder, folder_uuid)
        if row is None or row.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpeta no encontrada")
        sub = await self._session.execute(
            select(func.count()).select_from(ProjectFileFolder).where(ProjectFileFolder.parent_id == row.id)
        )
        if sub.scalar_one() > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La carpeta contiene subcarpetas",
            )
        fc = await self._session.execute(
            select(func.count()).select_from(ProjectFile).where(ProjectFile.folder_id == row.id)
        )
        if fc.scalar_one() > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La carpeta contiene archivos",
            )
        await self._session.delete(row)
        touch_project_updated_at(project)

    async def patch_project_file(
        self,
        user: User,
        project_uuid: UUID,
        file_uuid: UUID,
        patch: dict[str, Any],
    ) -> ProjectFile:
        project = await self._project_svc.get_project(user, project_uuid)
        pf = await self._session.get(ProjectFile, file_uuid)
        if pf is None or pf.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")

        changes: dict[str, Any] = {}

        if "original_name" in patch and patch["original_name"] is not None:
            new_name = sanitize_project_original_filename(str(patch["original_name"]))
            validate_project_file_extension(new_name)
            if new_name != pf.original_name:
                changes["original_name"] = {"from": pf.original_name, "to": new_name}
                pf.original_name = new_name

        if "description" in patch:
            new_desc = patch["description"]
            old_desc = pf.description
            if (old_desc or "") != (new_desc if new_desc is not None else ""):
                changes["description"] = {"from": old_desc, "to": new_desc}
            pf.description = new_desc

        if "discipline" in patch:
            raw = patch["discipline"]
            if raw is None or (isinstance(raw, str) and raw.strip() == ""):
                new_val = None
            elif isinstance(raw, str):
                d = parse_discipline(raw)
                if d is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="discipline no válida",
                    )
                new_val = d.value
            else:
                new_val = pf.discipline
            if new_val != pf.discipline:
                changes["discipline"] = {"from": pf.discipline, "to": new_val}
            pf.discipline = new_val

        if "folder_uuid" in patch:
            fu = patch["folder_uuid"]
            old_folder = pf.folder_id
            if fu is None:
                new_folder_id = None
            else:
                new_folder_id = await self._require_folder_in_project(project.id, fu)
            if old_folder != new_folder_id:
                changes["folder_uuid"] = {"from": str(old_folder) if old_folder else None, "to": str(new_folder_id) if new_folder_id else None}
            pf.folder_id = new_folder_id

        if "ingest_status" in patch and patch["ingest_status"] is not None:
            s = str(patch["ingest_status"]).strip().upper()
            if s not in (FileIngestStatus.DRAFT.value, FileIngestStatus.PUBLISHED.value):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="ingest_status debe ser DRAFT o PUBLISHED",
                )
            if s != pf.ingest_status:
                changes["ingest_status"] = {"from": pf.ingest_status, "to": s}
            pf.ingest_status = s

        if changes:
            await self._projects.record_event(
                project_id=project.id,
                actor_user_id=user.id,
                event_type="FILE_UPDATED",
                payload={
                    "file_uuid": str(file_uuid),
                    "name": pf.original_name,
                    "changes": changes,
                },
            )

        touch_project_updated_at(project)
        await self._session.flush()
        await self._session.refresh(pf)
        return pf

    async def delete_project_file(self, user: User, project_uuid: UUID, file_uuid: UUID) -> None:
        project = await self._project_svc.get_project(user, project_uuid)
        pf = await self._session.get(ProjectFile, file_uuid)
        if pf is None or pf.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")
        display_name = pf.original_name
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="FILE_DELETED",
            payload={"file_uuid": str(file_uuid), "name": display_name},
        )
        path = Path(pf.storage_key)
        await self._session.delete(pf)
        if path.is_file():
            path.unlink()
        touch_project_updated_at(project)

    async def get_file_path(self, user: User, project_uuid: UUID, file_uuid: UUID) -> tuple[ProjectFile, Path]:
        project = await self._project_svc.get_project(user, project_uuid)
        pf = await self._session.get(ProjectFile, file_uuid)
        if pf is None or pf.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")
        return pf, Path(pf.storage_key)

    async def list_subcontract_quotes(self, user: User, project_uuid: UUID) -> list[SubcontractQuote]:
        project = await self._project_svc.get_project(user, project_uuid)
        q = (
            select(SubcontractQuote)
            .options(selectinload(SubcontractQuote.lines))
            .where(SubcontractQuote.project_id == project.id)
            .order_by(SubcontractQuote.created_at.desc())
        )
        return list((await self._session.execute(q)).scalars().all())

    async def create_subcontract_quote(
        self,
        user: User,
        project_uuid: UUID,
        title: Optional[str],
    ) -> SubcontractQuote:
        project = await self._project_svc.get_project(user, project_uuid)
        q = SubcontractQuote(
            id=uuid.uuid4(),
            project_id=project.id,
            title=title,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(q)
        await self._session.flush()
        await self._session.refresh(q, ["lines"])
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="SUBCONTRACT_QUOTE_CREATED",
            payload={"quote_uuid": str(q.id), "title": q.title},
        )
        p2 = await self._load_project_full(project_uuid)
        if p2 is not None:
            await self._sync_subcontracts_flag(p2)
            touch_project_updated_at(p2)
        else:
            touch_project_updated_at(project)
        return q

    async def add_subcontract_line(
        self,
        user: User,
        project_uuid: UUID,
        quote_uuid: UUID,
        *,
        item_label: str,
        provider: Optional[str],
        price: Decimal,
        currency: str,
        external_ref: Optional[str],
    ) -> SubcontractQuoteLine:
        project = await self._project_svc.get_project(user, project_uuid)
        quote = await self._session.get(SubcontractQuote, quote_uuid)
        if quote is None or quote.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cotización no encontrada")
        line = SubcontractQuoteLine(
            id=uuid.uuid4(),
            quote_id=quote.id,
            item_label=item_label.strip(),
            provider=provider,
            price=price,
            currency=currency or "MXN",
            external_ref=external_ref,
        )
        self._session.add(line)
        await self._session.flush()
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="SUBCONTRACT_LINE_ADDED",
            payload={
                "quote_uuid": str(quote.id),
                "line_uuid": str(line.id),
                "item_label": line.item_label,
                "price": str(line.price),
                "currency": line.currency,
            },
        )
        p2 = await self._load_project_full(project_uuid)
        if p2 is not None:
            await self._sync_subcontracts_flag(p2)
            touch_project_updated_at(p2)
        else:
            touch_project_updated_at(project)
        return line

    async def get_subcontract_quote_with_lines(
        self,
        user: User,
        project_uuid: UUID,
        quote_uuid: UUID,
    ) -> SubcontractQuote:
        project = await self._project_svc.get_project(user, project_uuid)
        q = await self._session.execute(
            select(SubcontractQuote)
            .options(selectinload(SubcontractQuote.lines))
            .where(
                SubcontractQuote.id == quote_uuid,
                SubcontractQuote.project_id == project.id,
            )
        )
        row = q.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cotización no encontrada")
        return row

    async def delete_subcontract_quote(self, user: User, project_uuid: UUID, quote_uuid: UUID) -> None:
        project = await self._project_svc.get_project(user, project_uuid)
        quote = await self._session.get(SubcontractQuote, quote_uuid)
        if quote is None or quote.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cotización no encontrada")
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="SUBCONTRACT_QUOTE_DELETED",
            payload={"quote_uuid": str(quote.id), "title": quote.title},
        )
        await self._session.delete(quote)
        await self._session.flush()
        p2 = await self._load_project_full(project_uuid)
        if p2 is not None:
            await self._sync_subcontracts_flag(p2)
            touch_project_updated_at(p2)
        else:
            touch_project_updated_at(project)

    async def list_my_notifications(self, user: User, *, unread_only: bool) -> list[UserNotification]:
        q = select(UserNotification).where(UserNotification.user_id == user.id)
        if unread_only:
            q = q.where(UserNotification.read_at.is_(None))
        q = q.order_by(UserNotification.created_at.desc()).limit(100)
        return list((await self._session.execute(q)).scalars().all())

    async def mark_notification_read(self, user: User, notification_uuid: UUID) -> None:
        n = await self._session.get(UserNotification, notification_uuid)
        if n is None or n.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificación no encontrada")
        n.read_at = datetime.now(timezone.utc)
        await self._session.flush()

    async def _run_phase_automation(
        self,
        actor: User,
        project: Project,
        prev_phase_str: str,
        target_phase: WorkflowPhase,
    ) -> None:
        meta = dict(project.workflow_meta or {})
        auto = dict(meta.get("automation_tasks") or {})
        tasks = TaskBoardService(self._session, self._workspace_id)
        changed = False

        if (
            prev_phase_str == WorkflowPhase.AWAITING_FILES.value
            and target_phase == WorkflowPhase.ARCHITECTURE_REVIEW
            and not auto.get("enter_architecture_review")
        ):
            card = await tasks.create_automation_card_for_phase(
                actor,
                project_id=project.id,
                title="Revisión técnica documental (entrada a revisión de arquitectura)",
                description=(
                    "Revise checklist, archivos e informe documental antes de registrar la revisión formal."
                ),
                preferred_roles=[UserRole.ARQUITECTURA, UserRole.CONTROL],
            )
            auto["enter_architecture_review"] = True
            if card is not None:
                auto = append_automation_card_uuid(auto, card.id)
            changed = True

        if (
            prev_phase_str == WorkflowPhase.BUDGETING_PIPELINE.value
            and target_phase == WorkflowPhase.MANAGEMENT_APPROVAL
            and not auto.get("enter_management_approval")
        ):
            card = await tasks.create_automation_card_for_phase(
                actor,
                project_id=project.id,
                title="Revisión de Control — presupuesto",
                description="Validar cantidades, costos y supuestos antes de la aprobación de Gerencia.",
                preferred_roles=[UserRole.CONTROL],
            )
            auto["enter_management_approval"] = True
            if card is not None:
                auto = append_automation_card_uuid(auto, card.id)
            changed = True

        if changed:
            meta["automation_tasks"] = auto
            project.workflow_meta = meta

    async def maybe_automation_after_documentary_export(self, user: User, project_uuid: UUID) -> None:
        project = await self._project_svc.get_project(user, project_uuid)
        meta = dict(project.workflow_meta or {})
        auto = dict(meta.get("automation_tasks") or {})
        if auto.get("after_documentary_export"):
            return
        tasks = TaskBoardService(self._session, self._workspace_id)
        card = await tasks.create_automation_card_for_phase(
            user,
            project_id=project.id,
            title="Revisión informe documental generado",
            description="Se generó el PDF de informe documental; validar coherencia con el checklist.",
            preferred_roles=[UserRole.CONTROL, UserRole.ARQUITECTURA],
        )
        auto["after_documentary_export"] = True
        if card is not None:
            auto = append_automation_card_uuid(auto, card.id)
        meta["automation_tasks"] = auto
        project.workflow_meta = meta
        touch_project_updated_at(project)
        await self._session.flush()

    async def list_technical_findings(self, user: User, project_uuid: UUID) -> list[ProjectTechnicalFinding]:
        project = await self._project_svc.get_project(user, project_uuid)
        q = (
            select(ProjectTechnicalFinding)
            .where(ProjectTechnicalFinding.project_id == project.id)
            .order_by(ProjectTechnicalFinding.created_at.desc())
        )
        return list((await self._session.execute(q)).scalars().all())

    async def create_technical_finding(
        self,
        user: User,
        project_uuid: UUID,
        *,
        discipline: str,
        severity: str,
        title: str,
        description: str,
        evidence_ref: Optional[str],
    ) -> ProjectTechnicalFinding:
        project = await self._project_svc.get_project(user, project_uuid)
        row = ProjectTechnicalFinding(
            id=uuid.uuid4(),
            project_id=project.id,
            discipline=discipline.strip(),
            severity=severity.strip(),
            title=title.strip(),
            description=description.strip(),
            evidence_ref=(evidence_ref.strip() if evidence_ref else None),
            created_at=datetime.now(timezone.utc),
            created_by=user.id,
        )
        self._session.add(row)
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="TECHNICAL_FINDING_CREATED",
            payload={"finding_uuid": str(row.id), "title": row.title},
        )
        touch_project_updated_at(project)
        await self._session.flush()
        await self._session.refresh(row)
        return row

