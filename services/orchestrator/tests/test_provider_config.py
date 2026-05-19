import json

from app.config import Settings
from app.services.provider_config import (
    configured_provider_hints,
    is_configured_secret,
    resolve_openai_api_key,
)


def test_is_configured_secret_rejects_placeholders() -> None:
    assert is_configured_secret("sk-live") is True
    assert is_configured_secret(" replace_me ") is False
    assert is_configured_secret("changeme") is False
    assert is_configured_secret("") is False
    assert is_configured_secret(None) is False


def test_resolve_openai_api_key_uses_configured_value(monkeypatch):
    monkeypatch.delenv("SYNCORE_OPENAI_AUTH_PATH", raising=False)
    assert resolve_openai_api_key("sk-live-from-env") == "sk-live-from-env"


def test_resolve_openai_api_key_uses_auth_file_when_placeholder(monkeypatch, tmp_path):
    auth_file = tmp_path / "openai_credentials.json"
    auth_file.write_text(json.dumps({"api_key": "sk-from-file"}), encoding="utf-8")
    monkeypatch.setenv("SYNCORE_OPENAI_AUTH_PATH", str(auth_file))
    assert resolve_openai_api_key("replace_me") == "sk-from-file"


def test_resolve_openai_api_key_returns_none_without_valid_sources(monkeypatch, tmp_path):
    missing = tmp_path / "missing.json"
    monkeypatch.setenv("SYNCORE_OPENAI_AUTH_PATH", str(missing))
    assert resolve_openai_api_key("replace_me") is None


def test_configured_provider_hints_ignores_placeholder_provider_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.provider_config.ExperimentalCodexAuthProvider",
        lambda: type("_Auth", (), {"current_access_token": lambda self: "token-123"})(),
    )
    auth_file = tmp_path / "openai_credentials.json"
    auth_file.write_text(json.dumps({"api_key": "sk-file"}), encoding="utf-8")
    monkeypatch.setenv("SYNCORE_OPENAI_AUTH_PATH", str(auth_file))
    settings = Settings(
        openai_api_key="replace_me",
        anthropic_api_key="replace_me",
        gemini_api_key="changeme",
        codex_sidecar_enabled=True,
        codex_sidecar_base_url="http://localhost:9999",
        codex_sidecar_api_key="replace_me",
    )

    providers, hints = configured_provider_hints(settings)

    assert "openai" in providers
    assert "codex_oauth_experimental" in providers
    assert "anthropic" not in providers
    assert "gemini" not in providers
    assert "codex_sidecar" not in providers
    assert hints["codex_oauth_experimental"] == "gpt-5.5"
