from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import DEMO_JWT_SECRET, Settings, get_settings
from app.models.user import User
from app.services.password_reset_service import PasswordResetService


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_production_settings_reject_demo_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", DEMO_JWT_SECRET)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.asyncio
async def test_request_reset_raises_503_in_production_without_smtp(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 64)
    monkeypatch.setenv("COORDINATION_SMOKE_MODE", "false")
    get_settings.cache_clear()

    session = AsyncMock()
    user = User(
        id=__import__("uuid").uuid4(),
        email="tester@dupla.demo",
        first_name="T",
        last_name="U",
        password_hash="hash",
    )
    service = PasswordResetService(session)
    service._users = MagicMock()
    service._users.get_by_email = AsyncMock(return_value=user)
    service._tokens = MagicMock()
    service._tokens.invalidate_unused_for_user = AsyncMock()
    service._tokens.add = MagicMock()
    service._email = MagicMock()
    service._email.is_configured = False

    with pytest.raises(HTTPException) as exc:
        await service.request_reset("tester@dupla.demo")
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_request_reset_sends_email_when_smtp_configured(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()

    session = AsyncMock()
    user = User(
        id=__import__("uuid").uuid4(),
        email="tester@dupla.demo",
        first_name="T",
        last_name="U",
        password_hash="hash",
    )
    service = PasswordResetService(session)
    service._users = MagicMock()
    service._users.get_by_email = AsyncMock(return_value=user)
    service._tokens = MagicMock()
    service._tokens.invalidate_unused_for_user = AsyncMock()
    service._tokens.add = MagicMock()
    service._email = MagicMock()
    service._email.is_configured = True
    service._email.send_password_reset = AsyncMock()

    message, dev_token = await service.request_reset("tester@dupla.demo")
    assert "correo" in message.lower()
    assert dev_token is None
    service._email.send_password_reset.assert_awaited_once()
