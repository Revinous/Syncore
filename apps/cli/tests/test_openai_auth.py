from __future__ import annotations

import json

import httpx

from syncore_cli.openai_auth import OpenAICredentials, OpenAIAuthStore, OpenAIModelClient


class DummyResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self.reason_phrase = "OK" if status_code < 400 else "Error"
        self.headers = {"content-type": "application/json"}
        self._payload = payload

    def json(self):
        return self._payload


def test_auth_store_save_load_clear(tmp_path) -> None:
    path = tmp_path / "openai_credentials.json"
    store = OpenAIAuthStore(path=str(path))
    creds = OpenAICredentials(api_key="sk-test")
    store.save(creds)

    loaded = store.load()
    assert loaded is not None
    assert loaded.api_key == "sk-test"
    assert json.loads(path.read_text(encoding="utf-8"))["api_key"] == "sk-test"

    store.clear()
    assert store.load() is None


def test_model_client_lists_text_models(monkeypatch) -> None:
    def fake_get(url: str, headers=None, timeout=None):
        assert url == "https://api.openai.com/v1/models"
        assert headers["Authorization"].startswith("Bearer ")
        return DummyResponse(
            200,
            {
                "data": [
                    {"id": "gpt-5.4"},
                    {"id": "gpt-image-1"},
                    {"id": "gpt-5.2-codex"},
                    {"id": "text-embedding-3-small"},
                ]
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    client = OpenAIModelClient(timeout_seconds=1.0)
    models = client.list_text_models("sk-test")
    assert "gpt-5.4" in models
    assert "gpt-5.2-codex" in models
    assert "gpt-image-1" not in models
