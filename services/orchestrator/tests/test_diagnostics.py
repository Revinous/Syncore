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


def test_diagnostics_config_redacts_connection_values(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:pass@db.example:5432/app")
    monkeypatch.setenv("REDIS_URL", "redis://:secret@redis.example:6379/0")
    monkeypatch.setenv("CODEX_SIDECAR_ENABLED", "true")
    monkeypatch.setenv("CODEX_SIDECAR_BASE_URL", "http://127.0.0.1:4010")
    monkeypatch.setenv("CODEX_SIDECAR_API_KEY", "sidecar-secret")

    client = TestClient(create_app())
    response = client.get("/diagnostics/config")
    assert response.status_code == 200
    payload = response.json()

    assert payload["postgres_dsn"] == "postgresql://***@db.example:5432/app"
    assert payload["redis_url"] == "redis://***@redis.example:6379/0"
    assert payload["codex_sidecar"]["enabled"] is True
    assert payload["codex_sidecar"]["configured"] is True
    assert payload["codex_sidecar"]["api_key_configured"] is True
    assert payload["codex_sidecar"]["base_url"] == "http://127.0.0.1:4010"
    assert payload["codex_sidecar"]["provider"] == "codex_sidecar"
    assert payload["codex_sidecar"]["executable"] is False
    assert "official OpenAI Platform" in payload["codex_sidecar"]["warning"]
    assert payload["codex_sidecar"]["required_settings"] == [
        "CODEX_SIDECAR_ENABLED",
        "CODEX_SIDECAR_BASE_URL",
        "CODEX_SIDECAR_API_KEY",
    ]
    assert payload["codex_oauth_experimental"]["provider"] == "codex_oauth_experimental"
    assert payload["codex_oauth_experimental"]["provider_registered"] is False
    assert payload["codex_oauth_experimental"]["executable"] is False
    assert payload["codex_oauth_experimental"]["authenticated"] is False
    assert payload["codex_oauth_experimental"]["storage_secure"] is False
    assert payload["codex_oauth_experimental"]["implementation_state"] == "prototype"


def test_diagnostics_sidecar_reports_missing_api_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEX_SIDECAR_ENABLED", "true")
    monkeypatch.setenv("CODEX_SIDECAR_BASE_URL", "http://127.0.0.1:4010")
    monkeypatch.delenv("CODEX_SIDECAR_API_KEY", raising=False)

    client = TestClient(create_app())
    response = client.get("/diagnostics")
    assert response.status_code == 200
    payload = response.json()

    assert payload["codex_sidecar"]["enabled"] is True
    assert payload["codex_sidecar"]["configured"] is False
    assert payload["codex_sidecar"]["detail"] == "enabled but API key is missing"
    assert "CODEX_SIDECAR_API_KEY" in payload["codex_sidecar"]["recommended_action"]
    assert payload["codex_oauth_experimental"]["recommended_action"].startswith(
        "Run `syncore auth codex login`"
    )
