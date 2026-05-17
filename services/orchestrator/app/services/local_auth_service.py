from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import httpx


class LocalAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAICredentials:
    api_key: str


@dataclass(frozen=True)
class OpenAIAuthStatus:
    configured: bool
    storage_secure: bool
    token_path: str
    detail: str


class OpenAIAuthStore:
    def __init__(self, path: str | None = None) -> None:
        default_path = Path.home() / ".syncore" / "openai_credentials.json"
        self._path = Path(path or os.getenv("SYNCORE_OPENAI_AUTH_PATH") or default_path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> OpenAICredentials | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LocalAuthError(f"Could not read OpenAI credentials: {error}") from error
        api_key = str(payload.get("api_key", "")).strip()
        if not api_key:
            return None
        return OpenAICredentials(api_key=api_key)

    def save(self, credentials: OpenAICredentials) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._path.parent, 0o700)
        except OSError:
            pass
        payload = {"api_key": credentials.api_key}
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._path.parent,
            prefix=f".{self._path.name}.",
            delete=False,
        ) as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            temp_path = Path(handle.name)
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            pass
        temp_path.replace(self._path)

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()

    def status(self) -> OpenAIAuthStatus:
        return OpenAIAuthStatus(
            configured=self.load() is not None,
            storage_secure=_storage_is_secure(self._path),
            token_path=str(self._path),
            detail=(
                "Local OpenAI API credentials are stored for browser and CLI use."
                if self.load() is not None
                else "No local OpenAI API credentials are configured yet."
            ),
        )


class OpenAIModelClient:
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    def list_models(self, api_key: str) -> list[str]:
        url = "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            response = httpx.get(url, headers=headers, timeout=self._timeout_seconds)
        except httpx.HTTPError as error:
            raise LocalAuthError(f"Failed to connect to OpenAI API: {error}") from error
        data: Any
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            data = response.json()
        else:
            data = response.text
        if response.status_code >= 400:
            raise LocalAuthError(f"OpenAI API error {response.status_code}: {data}")
        raw_models = data.get("data", []) if isinstance(data, dict) else []
        return sorted(
            [
                str(item.get("id"))
                for item in raw_models
                if isinstance(item, dict) and str(item.get("id", "")).strip()
            ]
        )

    def list_text_models(self, api_key: str) -> list[str]:
        model_ids = self.list_models(api_key)
        excluded_prefixes = (
            "whisper",
            "tts",
            "gpt-image",
            "dall",
            "text-embedding",
            "omni-moderation",
            "text-moderation",
            "gpt-realtime",
            "gpt-audio",
            "chatgpt-",
        )
        preferred = [
            model
            for model in model_ids
            if not model.startswith(excluded_prefixes) and "transcribe" not in model
        ]
        return preferred or model_ids


class LocalOpenAIAuthService:
    def __init__(
        self,
        store: OpenAIAuthStore | None = None,
        model_client: OpenAIModelClient | None = None,
    ) -> None:
        self._store = store or OpenAIAuthStore()
        self._model_client = model_client or OpenAIModelClient()

    def status(self) -> OpenAIAuthStatus:
        return self._store.status()

    def save_api_key(self, api_key: str) -> list[str]:
        normalized = api_key.strip()
        if not normalized:
            raise LocalAuthError("OpenAI API key must not be empty.")
        models = self._model_client.list_text_models(normalized)
        self._store.save(OpenAICredentials(api_key=normalized))
        return models

    def list_models(self) -> list[str]:
        credentials = self._store.load()
        if credentials is None:
            raise LocalAuthError("No local OpenAI API key is configured.")
        return self._model_client.list_text_models(credentials.api_key)

    def clear(self) -> None:
        self._store.clear()


def _storage_is_secure(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return False
    return mode == 0o600
