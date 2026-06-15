import os
import socket
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import redis.asyncio as redis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.module import Module
from app.models.plan_delivery_request import PlanDeliveryRequest  # noqa: F401 — metadata for create_all
from app.models.project_member import ProjectMember  # noqa: F401 — metadata for create_all
from app.models.user import User, UserModule, UserRole
from app.models.workspace import DEFAULT_WORKSPACE_UUID, Workspace, WorkspaceMember
from app.security.password import hash_password
from app.services.workspace_bootstrap_service import bootstrap_workspace_resources

MODULE_ID = 1


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://dupla:dupla@127.0.0.1:5432/dupla")


def _postgres_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


@pytest_asyncio.fixture(scope="session")
async def engine(database_url: str):
    if not _postgres_reachable("127.0.0.1", 5432):
        pytest.skip("PostgreSQL not reachable on 127.0.0.1:5432 (start local Postgres)")
    eng = create_async_engine(database_url, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


def _add_user(
    session: AsyncSession,
    *,
    email: str,
    first_name: str,
    last_name: str,
    password: str,
    role: UserRole,
    workspace_id: uuid.UUID,
) -> uuid.UUID:
    user_id = uuid.uuid4()
    session.add(
        User(
            id=user_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=hash_password(password),
            role=role,
            must_change_password=False,
            active_workspace_id=workspace_id,
        )
    )
    session.add(UserModule(user_id=user_id, module_id=MODULE_ID))
    session.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id))
    return user_id


@pytest_asyncio.fixture()
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        await s.execute(
            text(
                "TRUNCATE subcontract_quote_lines, subcontract_quotes, user_notifications, architecture_revisions, "
                "plan_delivery_requests, project_clash_jobs, project_budget_jobs, project_files, project_events, project_members, "
                "chat_messages, chat_conversation_members, chat_conversations, task_cards, task_lists, "
                "workflow_template_steps, workflow_templates, project_architecture_data, projects, "
                "workspace_members, workspaces, user_modules, users, modules "
                "RESTART IDENTITY CASCADE"
            )
        )
        await s.commit()

        s.add(Module(id=MODULE_ID, name="Arquitectura"))
        s.add(
            Workspace(
                id=DEFAULT_WORKSPACE_UUID,
                name="Workspace demo",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await s.flush()

        _add_user(
            s,
            email="master@dupla.demo",
            first_name="María",
            last_name="López",
            password="master123",
            role=UserRole.GERENCIA,
            workspace_id=DEFAULT_WORKSPACE_UUID,
        )
        _add_user(
            s,
            email="tester@dupla.demo",
            first_name="Carlos",
            last_name="Ruiz",
            password="testpass123",
            role=UserRole.CONTROL,
            workspace_id=DEFAULT_WORKSPACE_UUID,
        )
        _add_user(
            s,
            email="worker@dupla.demo",
            first_name="Ana",
            last_name="Martín",
            password="workerpass123",
            role=UserRole.PRESUPUESTO,
            workspace_id=DEFAULT_WORKSPACE_UUID,
        )

        await bootstrap_workspace_resources(s, DEFAULT_WORKSPACE_UUID)
        await s.commit()

        settings = get_settings()
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await redis_client.flushdb()
        finally:
            await redis_client.aclose()

        yield s


@pytest_asyncio.fixture()
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def auth_headers_async(client: AsyncClient) -> dict[str, str]:
    """Control (tester): proyectos, chat, tablero con escritura."""
    res = await client.post(
        "/api/auth/token",
        data={"username": "tester@dupla.demo", "password": "testpass123"},
    )
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture()
async def master_auth_headers_async(client: AsyncClient) -> dict[str, str]:
    """Gerencia: administración y acceso completo al tablero."""
    res = await client.post(
        "/api/auth/token",
        data={"username": "master@dupla.demo", "password": "master123"},
    )
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
