from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Protocol

from .models import TokenBundle


class TokenStore(Protocol):
    @property
    def path(self) -> Path: ...

    def load(self) -> TokenBundle | None: ...

    def save(self, bundle: TokenBundle) -> None: ...

    def clear(self) -> None: ...


class FileTokenStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).expanduser()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> TokenBundle | None:
        if not self._path.exists():
            return None
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        access_token = str(payload.get("access_token", "")).strip()
        if not access_token:
            return None
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        return TokenBundle(
            provider=str(payload.get("provider", "")) or "experimental",
            access_token=access_token,
            refresh_token=_optional_string(payload.get("refresh_token")),
            id_token=_optional_string(payload.get("id_token")),
            token_type=_optional_string(payload.get("token_type")) or "Bearer",
            expires_at=_optional_string(payload.get("expires_at")),
            metadata={str(key): value for key, value in metadata.items()},
        )

    def save(self, bundle: TokenBundle) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(self._path.parent, 0o700)
        payload = {
            "provider": bundle.provider,
            "access_token": bundle.access_token,
            "refresh_token": bundle.refresh_token,
            "id_token": bundle.id_token,
            "token_type": bundle.token_type,
            "expires_at": bundle.expires_at,
            "metadata": bundle.metadata,
        }
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(self._path.parent),
            delete=False,
        ) as handle:
            handle.write(json.dumps(payload, indent=2))
            tmp_path = Path(handle.name)
        _chmod_best_effort(tmp_path, 0o600)
        os.replace(tmp_path, self._path)
        _chmod_best_effort(self._path, 0o600)

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()


def _optional_string(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def storage_is_secure(path: str | Path) -> bool:
    resolved = Path(path).expanduser()
    if not resolved.exists():
        return False
    try:
        file_mode = resolved.stat().st_mode & 0o777
        parent_mode = resolved.parent.stat().st_mode & 0o777
    except OSError:
        return False
    return file_mode == 0o600 and parent_mode == 0o700


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass
