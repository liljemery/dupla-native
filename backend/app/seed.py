import asyncio
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Tuple

from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError

from app.db.session import AsyncSessionLocal
from app.domain.bootstrap_defaults import default_bootstrap_criteria
from app.domain.project_kind import ProjectKind
from app.domain.tutorial_project import (
    TUTORIAL_PROJECT_NAME,
    TUTORIAL_PROJECT_UUID,
    TUTORIAL_TASK_CARD_UUID,
    TUTORIAL_TASK_TITLE,
)
from app.domain.workflow_phase import WorkflowPhase
from app.domain.workflow_template_phase import effective_workflow_phase_for_step
from app.models.workspace import DEFAULT_WORKSPACE_UUID
from app.services.workspace_bootstrap_service import bootstrap_workspace_resources, task_list_uuid_for_workspace
from app.models.module import Module
from app.models.project import Project, ProjectArchitectureData
from app.models.task_board import TaskCard, TaskList
from app.models.user import User, UserModule, UserRole
from app.repositories.project_repository import ProjectRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.repositories.workflow_template_repository import WorkflowTemplateRepository
from app.security.password import hash_password
from app.seed_default_workflow_template import ensure_default_workflow_template_if_missing


_MISSING_SCHEMA_HINT = (
    "No hay tablas en la base de datos. Aplica las migraciones antes del seed:\n"
    "  cd backend && alembic upgrade head\n"
    "Luego vuelve a ejecutar: python -m app.seed"
)

# Demo: Gerencia (admin total), Control (proyectos), Presupuesto (operario ejemplo).
SEED_USERS: Tuple[Tuple[str, str, str, str, UserRole], ...] = (
    ("master@dupla.demo", "María", "López", "master123", UserRole.GERENCIA),
    ("tester@dupla.demo", "Carlos", "Ruiz", "testpass123", UserRole.CONTROL),
    ("worker@dupla.demo", "Ana", "Martín", "workerpass123", UserRole.PRESUPUESTO),
)


async def seed() -> None:
    try:
        await _seed_impl()
    except ProgrammingError as e:
        orig = getattr(e, "orig", None)
        err = str(orig) if orig is not None else str(e)
        orig_name = type(orig).__name__ if orig is not None else ""
        if "does not exist" in err or "UndefinedTable" in orig_name:
            raise RuntimeError(_MISSING_SCHEMA_HINT) from e
        raise


async def _ensure_module(session) -> None:
    mod = await session.execute(select(Module).where(Module.id == 1))
    if mod.scalar_one_or_none() is None:
        session.add(Module(id=1, name="Arquitectura"))


async def _ensure_workspace_members(session) -> None:
    await bootstrap_workspace_resources(session, DEFAULT_WORKSPACE_UUID)
    repo = WorkspaceRepository(session)
    for email, _, _, _, role in SEED_USERS:
        uid = await _user_id_by_email(session, email)
        if uid is None:
            continue
        if role == UserRole.GERENCIA:
            continue
        if not await repo.user_is_member(uid, DEFAULT_WORKSPACE_UUID):
            await repo.add_member(DEFAULT_WORKSPACE_UUID, uid)
        user = (await session.execute(select(User).where(User.id == uid))).scalar_one()
        if user.active_workspace_id is None:
            user.active_workspace_id = DEFAULT_WORKSPACE_UUID


async def _ensure_general_conversation(session) -> None:
    await bootstrap_workspace_resources(session, DEFAULT_WORKSPACE_UUID)


async def _ensure_user(
    session,
    email: str,
    first_name: str,
    last_name: str,
    password_plain: str,
    role: UserRole,
) -> None:
    result = await session.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        # Si el usuario ya existía (p. ej. de un seed anterior sin nombres), rellenar nombres vacíos.
        fn = (existing.first_name or "").strip()
        ln = (existing.last_name or "").strip()
        if not fn and not ln:
            existing.first_name = first_name
            existing.last_name = last_name
        return
    uid = uuid.uuid4()
    session.add(
        User(
            id=uid,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=hash_password(password_plain),
            role=role,
            must_change_password=False,
        )
    )
    session.add(UserModule(user_id=uid, module_id=1))


def _seed_workflow_meta() -> dict[str, Any]:
    """Alineado con `ProjectRepository` / creación de proyectos."""
    return {
        "budget_pipeline": {
            "subcontracts_done": False,
            "volumetry_done": False,
            "cost_analysis_done": False,
            "budget_marked_complete": False,
            "client_approved_version_label": None,
            "volumetry": {},
            "cost_analysis": {},
            "budget_versions": [],
        
        }
    }


async def _user_id_by_email(session, email: str) -> uuid.UUID | None:
    r = await session.execute(select(User.id).where(User.email == email))
    return r.scalar_one_or_none()


async def _ensure_tutorial_project_and_task(session) -> None:
    """Proyecto demo con tarea vinculada, accesible por los usuarios semilla para tutoriales."""
    master_id = await _user_id_by_email(session, "master@dupla.demo")
    if master_id is None:
        return

    inserted = await ensure_default_workflow_template_if_missing(session)
    if inserted:
        print(
            "[seed] workflow_templates estaba vacío: se insertó la plantilla estándar Dupla.",
            file=sys.stderr,
        )

    wtr = WorkflowTemplateRepository(session)
    tpl = await wtr.get_default_active_template(DEFAULT_WORKSPACE_UUID)
    if tpl is None:
        print(
            "[seed] Sin plantilla de flujo activa; se omite el proyecto tutorial.",
            file=sys.stderr,
        )
        return
    ordered_steps = await wtr.list_steps_ordered(tpl.id)
    if not ordered_steps:
        print(
            "[seed] La plantilla por defecto no tiene pasos; se omite el proyecto tutorial.",
            file=sys.stderr,
        )
        return
    initial_step = ordered_steps[0]
    initial_phase = effective_workflow_phase_for_step(0)

    repo = ProjectRepository(session)
    project = await session.get(Project, TUTORIAL_PROJECT_UUID)
    if project is None:
        now = datetime.now(timezone.utc)
        project = Project(
            id=TUTORIAL_PROJECT_UUID,
            name=TUTORIAL_PROJECT_NAME,
            client_name="Dupla (demo)",
            project_kind=ProjectKind.CLIENT.value,
            created_by=master_id,
            workspace_id=DEFAULT_WORKSPACE_UUID,
            workflow_phase=initial_phase,
            workflow_meta=_seed_workflow_meta(),
            project_bootstrap_criteria=default_bootstrap_criteria(),
            specifications_document={},
            workflow_template_id=tpl.id,
            current_workflow_step_id=initial_step.id,
            created_at=now,
            updated_at=now,
        )
        session.add(project)
        await session.flush()
        session.add(
            ProjectArchitectureData(
                project_id=TUTORIAL_PROJECT_UUID,
                document={"groups": []},
                materiales=[],
                last_updated_by=master_id,
                updated_at=now,
            ),
        )
        await session.flush()
        await repo.record_event(
            project_id=TUTORIAL_PROJECT_UUID,
            actor_user_id=master_id,
            event_type="PROJECT_CREATED",
            payload={
                "name": project.name,
                "client_name": project.client_name,
                "project_kind": project.project_kind,
            },
        )
        await session.flush()

    for email, _, _, _, _ in SEED_USERS:
        uid = await _user_id_by_email(session, email)
        if uid is not None:
            await repo.add_project_member(TUTORIAL_PROJECT_UUID, uid)

    if await session.get(TaskCard, TUTORIAL_TASK_CARD_UUID) is not None:
        return

    todo_list_uuid = task_list_uuid_for_workspace(DEFAULT_WORKSPACE_UUID, 0)
    max_pos_row = await session.execute(
        select(func.coalesce(func.max(TaskCard.position), -1)).where(
            TaskCard.list_id == todo_list_uuid,
            TaskCard.archived.is_(False),
        )
    )
    next_pos = int(max_pos_row.scalar_one()) + 1
    now = datetime.now(timezone.utc)
    tl = await session.get(TaskList, todo_list_uuid)
    list_title = tl.title if tl is not None else "Por hacer"
    card = TaskCard(
        id=TUTORIAL_TASK_CARD_UUID,
        list_id=todo_list_uuid,
        title=TUTORIAL_TASK_TITLE,
        description="Tarjeta de práctica para el tablero global vinculada al proyecto tutorial.",
        position=next_pos,
        created_by=master_id,
        assignee_id=None,
        archived=False,
        archived_at=None,
        created_at=now,
        project_id=TUTORIAL_PROJECT_UUID,
        created_in_phase=WorkflowPhase.BOOTSTRAPPING.value,
    )
    session.add(card)
    await session.flush()
    await repo.record_event(
        project_id=TUTORIAL_PROJECT_UUID,
        actor_user_id=master_id,
        event_type="TASK_CARD_CREATED",
        payload={
            "task_uuid": str(TUTORIAL_TASK_CARD_UUID),
            "title": TUTORIAL_TASK_TITLE,
            "list_uuid": str(todo_list_uuid),
            "list_title": list_title,
            "assignee_uuid": None,
            "created_in_phase": WorkflowPhase.BOOTSTRAPPING.value,
        },
    )


async def _seed_impl() -> None:
    async with AsyncSessionLocal() as session:
        await _ensure_module(session)
        await _ensure_general_conversation(session)
        await session.commit()

    async with AsyncSessionLocal() as session:
        for email, first_name, last_name, password_plain, role in SEED_USERS:
            await _ensure_user(session, email, first_name, last_name, password_plain, role)
        await session.commit()

    async with AsyncSessionLocal() as session:
        await _ensure_workspace_members(session)
        await session.commit()

    async with AsyncSessionLocal() as session:
        await _ensure_tutorial_project_and_task(session)
        await session.commit()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
