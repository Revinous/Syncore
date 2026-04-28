from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_diagnostics_config_redacts_connection_values(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:pass@db.example:5432/app")
    monkeypatch.setenv("REDIS_URL", "redis://:secret@redis.example:6379/0")

    client = TestClient(create_app())
    response = client.get("/diagnostics/config")
    assert response.status_code == 200
    payload = response.json()

    assert payload["postgres_dsn"] == "postgresql://***@db.example:5432/app"
    assert payload["redis_url"] == "redis://***@redis.example:6379/0"
