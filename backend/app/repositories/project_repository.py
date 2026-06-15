import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.bootstrap_defaults import default_bootstrap_criteria
from app.domain.project_default_areas import default_area_names_for_project_kind
from app.domain.project_updated import touch_project_updated_at
from app.domain.user_permissions import has_elevated_access
from app.models.project import Project, ProjectArchitectureData
from app.models.project_event import ProjectEvent
from app.models.project_file import ProjectFile
from app.models.project_file_folder import ProjectFileFolder
from app.models.project_member import ProjectMember
from app.models.user import User, UserRole


def _default_workflow_meta() -> dict[str, Any]:
    return {
        "budget_pipeline": {
            "subcontracts_done": False,
            "volumetry_done": False,
            "cost_analysis_done": False,
            "budget_marked_complete": False,
            "control_review_done": False,
            "client_approved_version_label": None,
            "volumetry": {},
            "cost_analysis": {},
            "budget_versions": [],
        },
        "automation_tasks": {},
    }


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(
        self,
        user_uuid: UUID,
        *,
        is_master: bool,
        workspace_id: UUID,
    ) -> list[Project]:
        stmt = (
            select(Project)
            .options(selectinload(Project.current_workflow_step))
            .where(Project.workspace_id == workspace_id)
            .order_by(Project.updated_at.desc())
        )
        if not is_master:
            member_projects = select(ProjectMember.project_id).where(ProjectMember.user_id == user_uuid)
            stmt = stmt.where(or_(Project.created_by == user_uuid, Project.id.in_(member_projects)))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def is_project_member(self, project_id: UUID, user_id: UUID) -> bool:
        q = select(ProjectMember.id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        return (await self._session.execute(q)).scalar_one_or_none() is not None

    async def user_has_access_to_project(self, user: User, project: Project, workspace_id: UUID) -> bool:
        if project.workspace_id != workspace_id:
            return False
        if has_elevated_access(user):
            return True
        if project.created_by is not None and project.created_by == user.id:
            return True
        return await self.is_project_member(project.id, user.id)

    async def add_project_member(self, project_id: UUID, user_id: UUID) -> None:
        if await self.is_project_member(project_id, user_id):
            return
        self._session.add(
            ProjectMember(id=uuid.uuid4(), project_id=project_id, user_id=user_id),
        )
        await self._session.flush()

    async def replace_project_members(self, project_id: UUID, user_ids: set[UUID]) -> None:
        await self._session.execute(delete(ProjectMember).where(ProjectMember.project_id == project_id))
        for uid in user_ids:
            self._session.add(ProjectMember(id=uuid.uuid4(), project_id=project_id, user_id=uid))
        await self._session.flush()

    async def list_project_member_profiles(self, project_id: UUID) -> list[tuple[UUID, str, str, str]]:
        q = (
            select(User.id, User.email, User.first_name, User.last_name)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project_id)
            .order_by(User.email)
        )
        rows = (await self._session.execute(q)).all()
        return [(r[0], r[1], r[2], r[3]) for r in rows]

    async def list_team_profiles_for_project(self, project_uuid: UUID) -> list[tuple[UUID, str, str, str]]:
        project = await self.get_by_uuid(project_uuid)
        if project is None:
            return []
        by_id: dict[UUID, tuple[str, str, str]] = {}
        if project.created_by is not None:
            q_creator = select(User).where(User.id == project.created_by)
            creator = (await self._session.execute(q_creator)).scalar_one_or_none()
            if creator is not None:
                by_id[creator.id] = (creator.email, creator.first_name, creator.last_name)
        q = (
            select(User.id, User.email, User.first_name, User.last_name)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project.id)
        )
        for row in (await self._session.execute(q)).all():
            by_id[row[0]] = (row[1], row[2], row[3])
        return sorted([(uid, t[0], t[1], t[2]) for uid, t in by_id.items()], key=lambda x: x[1].lower())

    async def user_is_project_team_member(self, project: Project, user_id: UUID) -> bool:
        if project.created_by is not None and project.created_by == user_id:
            return True
        return await self.is_project_member(project.id, user_id)

    async def get_by_uuid(self, project_uuid: UUID) -> Optional[Project]:
        result = await self._session.execute(
            select(Project)
            .options(
                selectinload(Project.architecture_data),
                selectinload(Project.current_workflow_step),
            )
            .where(Project.id == project_uuid)
        )
        return result.scalar_one_or_none()

    async def list_for_template(
        self,
        template_id: UUID,
        *,
        is_master: bool,
        user_uuid: UUID,
        workspace_id: UUID,
    ) -> list[Project]:
        stmt = (
            select(Project)
            .options(selectinload(Project.current_workflow_step))
            .where(Project.workflow_template_id == template_id)
            .where(Project.workspace_id == workspace_id)
            .order_by(Project.updated_at.desc())
        )
        if not is_master:
            member_projects = select(ProjectMember.project_id).where(ProjectMember.user_id == user_uuid)
            stmt = stmt.where(or_(Project.created_by == user_uuid, Project.id.in_(member_projects)))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_project_code(self, code: str, workspace_id: UUID) -> Optional[Project]:
        c = code.strip()
        if not c:
            return None
        q = select(Project).where(Project.project_code == c, Project.workspace_id == workspace_id)
        return (await self._session.execute(q)).scalar_one_or_none()

    async def create_with_architecture(
        self,
        *,
        name: str,
        client_name: Optional[str],
        created_by: UUID,
        workspace_id: UUID,
        project_kind: str,
        workflow_phase: str,
        workflow_template_id: UUID,
        current_workflow_step_id: UUID,
        project_code: Optional[str] = None,
        location_text: Optional[str] = None,
        estimated_area_sqm: Optional[float] = None,
        floor_levels_count: Optional[int] = None,
        deadline: Optional[date] = None,
        responsible_user_id: Optional[UUID] = None,
        responsible_external_name: Optional[str] = None,
        responsible_external_email: Optional[str] = None,
    ) -> Project:
        # Siempre sembramos el checklist por defecto; las transiciones solo lo exigen en fase Arranque.
        bootstrap = default_bootstrap_criteria()
        pc = project_code.strip() if project_code else None
        pc = pc or None
        loc = location_text.strip() if location_text else None
        loc = loc or None
        project = Project(
            name=name,
            client_name=client_name,
            project_kind=project_kind,
            created_by=created_by,
            workspace_id=workspace_id,
            workflow_phase=workflow_phase,
            workflow_template_id=workflow_template_id,
            current_workflow_step_id=current_workflow_step_id,
            workflow_meta=_default_workflow_meta(),
            project_bootstrap_criteria=bootstrap,
            specifications_document={},
            project_code=pc,
            location_text=loc,
            estimated_area_sqm=estimated_area_sqm,
            floor_levels_count=floor_levels_count,
            deadline=deadline,
            responsible_user_id=responsible_user_id,
            responsible_external_name=responsible_external_name,
            responsible_external_email=responsible_external_email,
        )
        self._session.add(project)
        await self._session.flush()
        area_names = default_area_names_for_project_kind(project_kind)
        arch_groups = [
            {
                "id": str(uuid.uuid4()),
                "kind": "fase",
                "title": title,
                "order": idx,
                "items": [],
            }
            for idx, title in enumerate(area_names)
        ]
        arch = ProjectArchitectureData(
            project_id=project.id,
            document={"groups": arch_groups},
            materiales=[],
            last_updated_by=created_by,
        )
        self._session.add(arch)
        await self._session.flush()
        now = datetime.now(timezone.utc)
        for name in area_names:
            self._session.add(
                ProjectFileFolder(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    parent_id=None,
                    name=name,
                    created_by=created_by,
                    created_at=now,
                )
            )
        await self._session.flush()
        project.updated_at = project.created_at
        await self._session.flush()
        await self.add_project_member(project.id, created_by)
        await self._session.refresh(project, ["architecture_data"])
        return project

    async def save_architecture(
        self,
        project_uuid: UUID,
        document: dict,
        materiales: list,
        user_uuid: UUID,
    ) -> Optional[ProjectArchitectureData]:
        result = await self._session.execute(
            select(ProjectArchitectureData).where(ProjectArchitectureData.project_id == project_uuid)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.document = document
        row.materiales = materiales
        row.last_updated_by = user_uuid
        row.updated_at = datetime.now(timezone.utc)
        proj = await self._session.get(Project, project_uuid)
        if proj is not None:
            touch_project_updated_at(proj)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def record_event(
        self,
        *,
        project_id: UUID,
        actor_user_id: Optional[UUID],
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        ev = ProjectEvent(
            project_id=project_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            payload=payload,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(ev)
        await self._session.flush()

    async def count_project_files(self, project_id: UUID) -> int:
        q = select(func.count()).select_from(ProjectFile).where(ProjectFile.project_id == project_id)
        return int((await self._session.execute(q)).scalar_one())
