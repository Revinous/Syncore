from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile


class LocalSettingsError(RuntimeError):
    pass


KNOWN_PROVIDER_PREFERENCES = (
    "openai",
    "codex_oauth_experimental",
    "codex_sidecar",
    "anthropic",
    "gemini",
    "local_echo",
)


@dataclass(frozen=True)
class LocalExecutionSettings:
    default_provider_preference: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class LocalExecutionSettingsStatus:
    configured: bool
    storage_secure: bool
    settings_path: str
    default_provider_preference: str | None
    resolved_default_provider: str
    resolved_default_model: str
    detail: str
    updated_at: str | None = None


class LocalExecutionSettingsStore:
    def __init__(self, path: str | None = None) -> None:
        default_path = Path.home() / ".syncore" / "settings.json"
        self._path = Path(path or os.getenv("SYNCORE_LOCAL_SETTINGS_PATH") or default_path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> LocalExecutionSettings | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LocalSettingsError(f"Could not read local settings: {error}") from error
        preference = str(payload.get("default_provider_preference") or "").strip() or None
        updated_at = str(payload.get("updated_at") or "").strip() or None
        if preference and preference not in KNOWN_PROVIDER_PREFERENCES:
            preference = None
        return LocalExecutionSettings(
            default_provider_preference=preference,
            updated_at=updated_at,
        )

    def save(self, settings: LocalExecutionSettings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._path.parent, 0o700)
        except OSError:
            pass
        payload = {
            "default_provider_preference": settings.default_provider_preference,
            "updated_at": settings.updated_at
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
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


class LocalExecutionSettingsService:
    def __init__(self, store: LocalExecutionSettingsStore | None = None) -> None:
        self._store = store or LocalExecutionSettingsStore()

    @property
    def path(self) -> Path:
        return self._store.path

    def load(self) -> LocalExecutionSettings | None:
        return self._store.load()

    def save_default_provider_preference(self, provider: str | None) -> LocalExecutionSettings:
        normalized = (provider or "").strip().lower() or None
        if normalized is not None and normalized not in KNOWN_PROVIDER_PREFERENCES:
            available = ", ".join(KNOWN_PROVIDER_PREFERENCES)
            raise LocalSettingsError(
                f"Unknown default provider preference '{normalized}'. Available: {available}"
            )
        next_settings = LocalExecutionSettings(
            default_provider_preference=normalized,
            updated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        self._store.save(next_settings)
        return next_settings

    def status(
        self,
        *,
        configured_providers: set[str],
        provider_model_hints: dict[str, str],
        fallback_provider: str,
        fallback_model: str,
    ) -> LocalExecutionSettingsStatus:
        current = self._store.load()
        resolved_provider, resolved_model = resolve_default_provider_settings(
            configured_providers=configured_providers,
            provider_model_hints=provider_model_hints,
            fallback_provider=fallback_provider,
            fallback_model=fallback_model,
            stored_preference=current.default_provider_preference if current else None,
        )
        detail = (
            f"Local default provider preference is set to {current.default_provider_preference}."
            if current and current.default_provider_preference
            else (
                "No local default provider preference is set. "
                "Syncore is using the environment default."
            )
        )
        return LocalExecutionSettingsStatus(
            configured=current is not None and current.default_provider_preference is not None,
            storage_secure=_storage_is_secure(self._store.path),
            settings_path=str(self._store.path),
            default_provider_preference=(
                current.default_provider_preference if current else None
            ),
            resolved_default_provider=resolved_provider,
            resolved_default_model=resolved_model,
            detail=detail,
            updated_at=current.updated_at if current else None,
        )


def resolve_default_provider_settings(
    *,
    configured_providers: set[str],
    provider_model_hints: dict[str, str],
    fallback_provider: str,
    fallback_model: str,
    stored_preference: str | None,
) -> tuple[str, str]:
    preferred = (stored_preference or "").strip().lower()
    fallback = (fallback_provider or "local_echo").strip().lower()
    if preferred and preferred in configured_providers:
        provider = preferred
    elif fallback:
        provider = fallback
    elif "local_echo" in configured_providers:
        provider = "local_echo"
    else:
        provider = sorted(configured_providers)[0]
    model = provider_model_hints.get(provider) or (
        fallback_model if provider == fallback else provider
    )
    return provider, model


def _storage_is_secure(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return False
    return mode == 0o600
