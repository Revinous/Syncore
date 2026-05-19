from __future__ import annotations

import json
import os
from pathlib import Path

from app.config import Settings
from app.experimental_auth import ExperimentalCodexAuthProvider

PLACEHOLDER_SECRETS = {
    "",
    "replace_me",
    "changeme",
    "your_api_key_here",
    "your-key-here",
    "example",
    "example_key",
    "example-token",
}


def is_configured_secret(value: str | None) -> bool:
    normalized = (value or "").strip()
    return bool(normalized) and normalized.lower() not in PLACEHOLDER_SECRETS


def resolve_openai_api_key(configured_api_key: str | None) -> str | None:
    configured = (configured_api_key or "").strip()
    if is_configured_secret(configured):
        return configured

    auth_path = os.getenv("SYNCORE_OPENAI_AUTH_PATH")
    if auth_path:
        path = Path(auth_path).expanduser()
    else:
        path = Path.home() / ".syncore" / "openai_credentials.json"

    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    file_key = str(payload.get("api_key", "")).strip()
    return file_key if is_configured_secret(file_key) else None


def configured_provider_hints(settings: Settings) -> tuple[set[str], dict[str, str]]:
    configured = {"local_echo"}
    hints = {"local_echo": "local_echo"}

    if resolve_openai_api_key(settings.openai_api_key):
        configured.add("openai")
        hints["openai"] = "gpt-5.4"
    if is_configured_secret(settings.anthropic_api_key):
        configured.add("anthropic")
        hints["anthropic"] = "claude-3-7-sonnet-latest"
    if is_configured_secret(settings.gemini_api_key):
        configured.add("gemini")
        hints["gemini"] = "gemini-2.5-pro"
    if (
        settings.codex_sidecar_enabled
        and is_configured_secret(settings.codex_sidecar_api_key)
        and settings.codex_sidecar_base_url.strip()
    ):
        configured.add("codex_sidecar")
        hints["codex_sidecar"] = "gpt-5.5"
    if ExperimentalCodexAuthProvider().current_access_token():
        configured.add("codex_oauth_experimental")
        hints["codex_oauth_experimental"] = "gpt-5.5"
    return configured, hints
