import json

from app.services.run_execution_service import _resolve_openai_api_key


def test_resolve_openai_api_key_uses_configured_value(monkeypatch):
    monkeypatch.delenv("SYNCORE_OPENAI_AUTH_PATH", raising=False)
    assert _resolve_openai_api_key("sk-live-from-env") == "sk-live-from-env"


def test_resolve_openai_api_key_uses_auth_file_when_placeholder(monkeypatch, tmp_path):
    auth_file = tmp_path / "openai_credentials.json"
    auth_file.write_text(json.dumps({"api_key": "sk-from-file"}), encoding="utf-8")
    monkeypatch.setenv("SYNCORE_OPENAI_AUTH_PATH", str(auth_file))
    assert _resolve_openai_api_key("replace_me") == "sk-from-file"


def test_resolve_openai_api_key_returns_none_without_valid_sources(monkeypatch, tmp_path):
    missing = tmp_path / "missing.json"
    monkeypatch.setenv("SYNCORE_OPENAI_AUTH_PATH", str(missing))
    assert _resolve_openai_api_key("replace_me") is None
