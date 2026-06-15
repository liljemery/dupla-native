import pytest
from pydantic import ValidationError

from app.config import DEMO_JWT_SECRET, Settings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_development_allows_demo_jwt_secret(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("JWT_SECRET", DEMO_JWT_SECRET)
    settings = Settings()
    assert settings.app_env == "development"
    assert settings.jwt_secret == DEMO_JWT_SECRET


def test_production_rejects_demo_jwt_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", DEMO_JWT_SECRET)
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings()


def test_staging_rejects_coordination_smoke_mode(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("JWT_SECRET", "a" * 64)
    monkeypatch.setenv("COORDINATION_SMOKE_MODE", "true")
    with pytest.raises(ValidationError, match="COORDINATION_SMOKE_MODE"):
        Settings()
