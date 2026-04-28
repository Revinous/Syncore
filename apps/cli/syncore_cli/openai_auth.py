from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class OpenAIAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAICredentials:
    api_key: str


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
            raise OpenAIAuthError(f"Could not read OpenAI credentials: {error}") from error

        api_key = str(payload.get("api_key", "")).strip()
        if not api_key:
            return None
        return OpenAICredentials(api_key=api_key)

    def save(self, credentials: OpenAICredentials) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"api_key": credentials.api_key}
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()


class OpenAIModelClient:
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    def list_models(self, api_key: str) -> list[str]:
        url = "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            response = httpx.get(url, headers=headers, timeout=self._timeout_seconds)
        except httpx.HTTPError as error:
            raise OpenAIAuthError(f"Failed to connect to OpenAI API: {error}") from error

        data: Any
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            data = response.json()
        else:
            data = response.text

        if response.status_code >= 400:
            raise OpenAIAuthError(f"OpenAI API error {response.status_code}: {data}")

        raw_models = data.get("data", []) if isinstance(data, dict) else []
        model_ids = sorted(
            [
                str(item.get("id"))
                for item in raw_models
                if isinstance(item, dict) and str(item.get("id", "")).strip()
            ]
        )
        return model_ids

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
