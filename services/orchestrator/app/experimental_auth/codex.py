from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import ExperimentalAuthStatus, TokenBundle
from .store import FileTokenStore, TokenStore


class ExperimentalAuthProvider(Protocol):
    def load(self) -> TokenBundle | None: ...

    def save(self, bundle: TokenBundle) -> None: ...

    def clear(self) -> None: ...

    def refresh(self) -> TokenBundle: ...

    def status(self) -> ExperimentalAuthStatus: ...

    def current_access_token(self) -> str | None: ...


class ExperimentalCodexAuthProvider:
    provider_name = "codex_oauth_experimental"

    def __init__(self, store: TokenStore | None = None) -> None:
        self._store = store or FileTokenStore(_default_codex_token_path())

    @property
    def token_path(self) -> Path:
        return self._store.path

    def load(self) -> TokenBundle | None:
        return self._store.load()

    def save(self, bundle: TokenBundle) -> None:
        self._store.save(bundle)

    def clear(self) -> None:
        self._store.clear()

    def refresh(self) -> TokenBundle:
        raise RuntimeError(
            "Native Codex OAuth refresh is not implemented in Syncore yet. "
            "Use the `codex_sidecar` bridge for live execution today."
        )

    def status(self) -> ExperimentalAuthStatus:
        bundle = self._store.load()
        return ExperimentalAuthStatus(
            provider=self.provider_name,
            mode="experimental",
            implementation_state="not_implemented",
            authenticated=bundle is not None,
            can_refresh=bundle is not None and bool(bundle.refresh_token),
            token_path=str(self._store.path),
            expires_at=bundle.expires_at if bundle is not None else None,
            detail=(
                "Native Codex OAuth is not implemented in Syncore yet. "
                "Use the `codex_sidecar` local bridge for execution."
            ),
            metadata=bundle.metadata if bundle is not None else {},
        )

    def current_access_token(self) -> str | None:
        bundle = self._store.load()
        if bundle is None:
            return None
        return bundle.access_token


def _default_codex_token_path() -> Path:
    return Path.home() / ".syncore" / "auth" / "codex" / "token.json"
