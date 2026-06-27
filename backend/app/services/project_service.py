from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.project_kind import ProjectKind
from app.domain.workflow_template_phase import effective_workflow_phase_for_step
from app.domain.project_updated import touch_project_updated_at
from app.services.permission_service import PermissionService
from app.models.project import Project
from app.models.user import User, UserRole
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.repositories.workflow_template_repository import WorkflowTemplateRepository
from app.schemas.architecture import ArchitectureDocumentPayload

settings = get_settings()


class ProjectService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self._session = session
        self._workspace_id = workspace_id
        self._projects = ProjectRepository(session)
        self._users = UserRepository(session)
        self._workflow_templates = WorkflowTemplateRepository(session)
        self._perm_svc = PermissionService(session)

    async def ensure_architecture_access(self, user: User) -> None:
        ok = await self._users.has_module(user.id, settings.architecture_module_id)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to the Architecture module",
            )

    async def list_projects(self, user: User, *, include_archived: bool = False) -> list[Project]:
        await self.ensure_architecture_access(user)
        if include_archived and not await self._perm_svc.has(user, "projects.view_archived"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo Gerencia puede listar proyectos archivados",
            )
        is_master = await self._perm_svc.has(user, "projects.view_all")
        return await self._projects.list_for_user(
            user.id,
            is_master=is_master,
            workspace_id=self._workspace_id,
            include_archived=include_archived,
        )

    async def list_projects_for_template(
        self, user: User, template_uuid: UUID, *, include_archived: bool = False
    ) -> list[Project]:
        await self.ensure_architecture_access(user)
        if include_archived and not await self._perm_svc.has(user, "projects.view_archived"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo Gerencia puede listar proyectos archivados",
            )
        tpl = await self._workflow_templates.get_template_by_uuid(template_uuid, self._workspace_id)
        if tpl is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plantilla no encontrada")
        is_master = await self._perm_svc.has(user, "projects.view_all")
        return await self._projects.list_for_template(
            tpl.id,
            is_master=is_master,
            user_uuid=user.id,
            workspace_id=self._workspace_id,
            include_archived=include_archived,
        )

    async def create_project(
        self,
        user: User,
        *,
        name: str,
        client_name: Optional[str],
        project_kind: ProjectKind,
        member_user_uuids: Optional[list[UUID]],
        files: list[UploadFile],
        project_code: Optional[str] = None,
        location_text: Optional[str] = None,
        estimated_area_sqm: Optional[Decimal] = None,
        floor_levels_count: Optional[int] = None,
        deadline: Optional[date] = None,
        responsible_user_uuid: Optional[UUID] = None,
        responsible_external_name: Optional[str] = None,
        responsible_external_email: Optional[str] = None,
        workflow_template_uuid: Optional[UUID] = None,
    ) -> Project:
        await self.ensure_architecture_access(user)
        if not await self._perm_svc.has(user, "projects.create"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo Gerencia o Líder de equipo puede crear proyectos",
            )
        name_clean = name.strip()
        if not name_clean:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre del proyecto es obligatorio",
            )
        non_empty_files = [f for f in files if getattr(f, "filename", None)]
        if project_kind == ProjectKind.TENDER and len(non_empty_files) < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Los proyectos de licitación requieren al menos un archivo al crear el proyecto",
            )
        if workflow_template_uuid is not None:
            tpl = await self._workflow_templates.get_template_by_uuid(workflow_template_uuid, self._workspace_id)
            if tpl is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La plantilla de flujo no existe",
                )
        else:
            tpl = await self._workflow_templates.get_default_active_template(self._workspace_id)
            if tpl is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No hay plantillas de flujo activas; creá una en Flujos.",
                )
        if tpl.archived_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La plantilla de flujo está archivada",
            )
        ordered_steps = await self._workflow_templates.list_steps_ordered(tpl.id)
        if not ordered_steps:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La plantilla de flujo no tiene ningún paso",
            )
        initial_step = ordered_steps[0]
        wf = effective_workflow_phase_for_step(0)
        cn = client_name.strip() if client_name else None
        cn = cn or None
        pc = project_code.strip() if project_code else None
        pc = pc or None
        if pc is not None:
            existing = await self._projects.get_by_project_code(pc, self._workspace_id)
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ya existe un proyecto con ese código",
                )
        allowed_ids: set[UUID] = {user.id}
        if member_user_uuids is not None:
            allowed_ids |= set(member_user_uuids)
        if responsible_user_uuid is not None and responsible_user_uuid not in allowed_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El responsable debe ser el creador o un miembro seleccionado para el proyecto",
            )
        area_float: Optional[float] = None
        if estimated_area_sqm is not None:
            area_float = float(estimated_area_sqm)
        loc = location_text.strip() if location_text else None
        loc = loc or None
        ext_name = responsible_external_name.strip() if responsible_external_name else None
        ext_name = ext_name or None
        ext_email = responsible_external_email.strip() if responsible_external_email else None
        ext_email = ext_email or None
        project = await self._projects.create_with_architecture(
            name=name_clean,
            client_name=cn,
            created_by=user.id,
            workspace_id=self._workspace_id,
            project_kind=project_kind.value,
            workflow_phase=wf,
            workflow_template_id=tpl.id,
            current_workflow_step_id=initial_step.id,
            project_code=pc,
            location_text=loc,
            estimated_area_sqm=area_float,
            floor_levels_count=floor_levels_count,
            deadline=deadline,
            responsible_user_id=responsible_user_uuid,
            responsible_external_name=ext_name,
            responsible_external_email=ext_email,
        )
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="PROJECT_CREATED",
            payload={
                "name": project.name,
                "client_name": project.client_name,
                "project_kind": project_kind.value,
            },
        )
        if member_user_uuids is not None:
            await self.set_project_members(user, project.id, member_user_uuids)
        return project

    async def get_project(self, user: User, project_uuid: UUID) -> Project:
        await self.ensure_architecture_access(user)
        project = await self._projects.get_by_uuid(project_uuid)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        if project.archived_at is not None and not await self._perm_svc.has(user, "projects.view_archived"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        if not await self._projects.user_has_access_to_project(
            user, project, self._workspace_id, view_all=await self._perm_svc.has(user, "projects.view_all")
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project

    async def delete_project(self, user: User, project_uuid: UUID) -> None:
        if not await self._perm_svc.has(user, "projects.delete"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo Gerencia puede eliminar proyectos archivados",
            )
        project = await self.get_project(user, project_uuid)
        if project.archived_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Solo se pueden eliminar proyectos archivados",
            )
        await self._projects.delete_project(project.id)

    async def list_project_members(self, user: User, project_uuid: UUID) -> list[tuple[UUID, str, str, str]]:
        project = await self.get_project(user, project_uuid)
        return await self._projects.list_project_member_profiles(project.id)

    async def set_project_members(self, master: User, project_uuid: UUID, member_user_uuids: list[UUID]) -> None:
        if not await self._perm_svc.has(master, "projects.view_all"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo Gerencia o Líder de equipo puede configurar quién ve el proyecto",
            )
        project = await self.get_project(master, project_uuid)
        ids = set(member_user_uuids)
        if project.created_by is not None:
            ids.add(project.created_by)
        for uid in ids:
            u = await self._users.get_by_uuid(uid)
            if u is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Usuario no encontrado (uuid: {uid}). Actualiza el listado de usuarios en administración.",
                )
            if not await self._users.has_module(uid, settings.architecture_module_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Todos los miembros deben tener acceso al módulo Arquitectura",
                )
        await self._projects.replace_project_members(project.id, ids)
        pairs = await self._projects.list_project_member_profiles(project.id)
        member_payload: list[dict[str, Any]] = [
            {"user_uuid": str(u), "email": e, "first_name": fn, "last_name": ln}
            for u, e, fn, ln in sorted(pairs, key=lambda x: x[1].lower())
        ]
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=master.id,
            event_type="PROJECT_MEMBERS_UPDATED",
            payload={"member_count": len(member_payload), "members": member_payload},
        )
        touch_project_updated_at(project)

    async def get_architecture(self, user: User, project_uuid: UUID) -> Tuple[dict, Optional[datetime]]:
        project = await self.get_project(user, project_uuid)
        if project.architecture_data is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Architecture data missing")
        doc = project.architecture_data.document or {}
        if "groups" not in doc:
            doc = {"groups": doc.get("groups", [])}
        materiales = project.architecture_data.materiales or []
        payload = {"groups": doc.get("groups", []), "materiales": materiales}
        return payload, project.architecture_data.updated_at

    async def put_architecture(
        self,
        user: User,
        project_uuid: UUID,
        payload: ArchitectureDocumentPayload,
    ) -> None:
        project = await self.get_project(user, project_uuid)
        groups = [g.model_dump(mode="json") for g in payload.groups]
        materiales = [m.model_dump(mode="json") for m in payload.materiales]
        document = {"groups": groups}
        row = await self._projects.save_architecture(
            project_uuid,
            document=document,
            materiales=materiales,
            user_uuid=user.id,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Architecture data missing")
        await self._projects.record_event(
            project_id=project.id,
            actor_user_id=user.id,
            event_type="ARCHITECTURE_SAVED",
            payload={"groups_count": len(groups), "materiales_count": len(materiales)},
        )
