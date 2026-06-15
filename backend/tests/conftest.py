import os
import socket
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.chat_conversation import (
    GENERAL_CONVERSATION_UUID,
    ChatConversation,
    ChatConversationKind,
)
from app.models.module import Module
from app.models.plan_delivery_request import PlanDeliveryRequest  # noqa: F401 — metadata for create_all
from app.models.project_member import ProjectMember  # noqa: F401 — metadata for create_all
from app.models.task_board import TaskList
from app.models.user import User, UserModule, UserRole
from app.security.password import hash_password

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


@pytest_asyncio.fixture()
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        await s.execute(
            text(
                "TRUNCATE subcontract_quote_lines, subcontract_quotes, user_notifications, architecture_revisions, "
                "plan_delivery_requests, project_clash_jobs, project_files, project_events, project_members, chat_messages, chat_conversation_members, chat_conversations, "
                "task_cards, task_lists, project_architecture_data, projects, user_modules, users, modules "
                "RESTART IDENTITY CASCADE"
            )
        )
        await s.commit()

        s.add(Module(id=MODULE_ID, name="Arquitectura"))
        s.add(
            TaskList(
                id=uuid.UUID("a0000001-0000-4000-8000-000000000001"),
                title="Por hacer",
                position=0,
            )
        )
        s.add(
            TaskList(
                id=uuid.UUID("a0000001-0000-4000-8000-000000000004"),
                title="Bloqueado",
                position=1,
            )
        )
        s.add(
            TaskList(
                id=uuid.UUID("a0000001-0000-4000-8000-000000000002"),
                title="En progreso",
                position=2,
            )
        )
        s.add(
            TaskList(
                id=uuid.UUID("a0000001-0000-4000-8000-000000000005"),
                title="En revisión",
                position=3,
            )
        )
        s.add(
            TaskList(
                id=uuid.UUID("a0000001-0000-4000-8000-000000000003"),
                title="Hecho",
                position=4,
            )
        )
        master_id = uuid.uuid4()
        s.add(
            User(
                id=master_id,
                email="master@dupla.demo",
                first_name="María",
                last_name="López",
                password_hash=hash_password("master123"),
                role=UserRole.GERENCIA,
                must_change_password=False,
            )
        )
        s.add(UserModule(user_id=master_id, module_id=MODULE_ID))
        tester_id = uuid.uuid4()
        s.add(
            User(
                id=tester_id,
                email="tester@dupla.demo",
                first_name="Carlos",
                last_name="Ruiz",
                password_hash=hash_password("testpass123"),
                role=UserRole.CONTROL,
                must_change_password=False,
            )
        )
        s.add(UserModule(user_id=tester_id, module_id=MODULE_ID))
        worker_id = uuid.uuid4()
        s.add(
            User(
                id=worker_id,
                email="worker@dupla.demo",
                first_name="Ana",
                last_name="Martín",
                password_hash=hash_password("workerpass123"),
                role=UserRole.PRESUPUESTO,
                must_change_password=False,
            )
        )
        s.add(UserModule(user_id=worker_id, module_id=MODULE_ID))
        s.add(
            ChatConversation(
                id=GENERAL_CONVERSATION_UUID,
                kind=ChatConversationKind.GENERAL,
                title=None,
                created_at=datetime.now(timezone.utc),
                last_message_at=None,
            )
        )
        await s.commit()
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
