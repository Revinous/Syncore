from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Protocol

from .codex_client import (
    DEFAULT_CALLBACK_PORT,
    DEVICE_VERIFICATION_URL,
    CodexAuthHttpClient,
    CodexOAuthError,
    build_browser_login_state,
    open_browser,
)
from .models import ExperimentalAuthStatus, TokenBundle
from .oauth_server import OAuthCallbackServer
from .store import FileTokenStore, TokenStore, storage_is_secure


class ExperimentalAuthProvider(Protocol):
    def load(self) -> TokenBundle | None: ...

    def save(self, bundle: TokenBundle) -> None: ...

    def clear(self) -> None: ...

    def refresh(self) -> TokenBundle: ...

    def status(self) -> ExperimentalAuthStatus: ...

    def current_access_token(self) -> str | None: ...


class ExperimentalCodexAuthProvider:
    provider_name = "codex_oauth_experimental"

    def __init__(
        self,
        store: TokenStore | None = None,
        client: CodexAuthHttpClient | None = None,
    ) -> None:
        self._store = store or FileTokenStore(_default_codex_token_path())
        self._client = client or CodexAuthHttpClient()

    @property
    def token_path(self) -> Path:
        return self._store.path

    def load(self) -> TokenBundle | None:
        return self._store.load()

    def save(self, bundle: TokenBundle) -> None:
        self._store.save(bundle)

    def clear(self) -> None:
        self._store.clear()

    def login_browser(
        self,
        *,
        callback_port: int = DEFAULT_CALLBACK_PORT,
        no_browser: bool = False,
    ) -> tuple[TokenBundle, str]:
        state, pkce, auth_url = build_browser_login_state(callback_port)
        server = OAuthCallbackServer(callback_port)
        server.start()
        try:
            if not no_browser:
                open_browser(auth_url)
            callback = server.wait_for_callback(timeout_seconds=300)
        finally:
            server.stop()
        if callback.error:
            raise CodexOAuthError(
                f"Codex OAuth callback failed: {callback.error}"
                + (f" ({callback.error_description})" if callback.error_description else "")
            )
        if not callback.code or not callback.state:
            raise CodexOAuthError("Codex OAuth callback did not return a code and state.")
        if callback.state != state:
            raise CodexOAuthError("Codex OAuth callback state mismatch.")
        bundle = self._client.exchange_code_for_tokens(callback.code, pkce, callback_port)
        self._store.save(bundle)
        return bundle, auth_url

    def login_device(self) -> tuple[TokenBundle, dict[str, str | int]]:
        response = self._client.request_device_code()
        authorization_code, pkce = self._client.poll_device_authorization(
            response.device_auth_id,
            response.user_code,
            response.interval_seconds,
        )
        bundle = self._client.exchange_device_code_for_tokens(authorization_code, pkce)
        self._store.save(bundle)
        return bundle, {
            "verification_url": DEVICE_VERIFICATION_URL,
            "user_code": response.user_code,
            "interval_seconds": response.interval_seconds,
        }

    def refresh(self) -> TokenBundle:
        bundle = self._store.load()
        if bundle is None or not bundle.refresh_token:
            raise CodexOAuthError("No refreshable Codex OAuth credentials are stored.")
        refreshed = self._client.refresh_tokens(bundle.refresh_token)
        if refreshed.refresh_token is None:
            refreshed = replace(refreshed, refresh_token=bundle.refresh_token)
        self._store.save(refreshed)
        return refreshed

    def status(self) -> ExperimentalAuthStatus:
        bundle = self._store.load()
        return ExperimentalAuthStatus(
            provider=self.provider_name,
            mode="experimental",
            implementation_state="prototype",
            authenticated=bundle is not None,
            can_refresh=bundle is not None and bool(bundle.refresh_token),
            storage_secure=storage_is_secure(self._store.path),
            token_path=str(self._store.path),
            expires_at=bundle.expires_at if bundle is not None else None,
            detail=(
                "Native experimental Codex OAuth prototype is available for local auth. "
                "Execution routing should still prefer codex_sidecar until a native "
                "executor is added."
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
