from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from app.services.local_settings_service import LocalExecutionSettingsStore


def test_settings_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SYNCORE_LOCAL_SETTINGS_PATH", str(tmp_path / "settings.json"))
    auth_file = tmp_path / "openai_credentials.json"
    auth_file.write_text('{"api_key":"sk-test"}\n', encoding="utf-8")
    monkeypatch.setenv("SYNCORE_OPENAI_AUTH_PATH", str(auth_file))
    get_settings.cache_clear()
    from app.main import create_app

    client = TestClient(create_app())

    response = client.get("/settings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["resolved_default_provider"] == "local_echo"
    assert "openai" in payload["available_provider_preferences"]

    update = client.put("/settings", json={"default_provider_preference": "openai"})
    assert update.status_code == 200
    updated = update.json()
    assert updated["default_provider_preference"] == "openai"
    assert updated["resolved_default_provider"] == "openai"

    store = LocalExecutionSettingsStore(str(tmp_path / "settings.json"))
    saved = store.load()
    assert saved is not None
    assert saved.default_provider_preference == "openai"
