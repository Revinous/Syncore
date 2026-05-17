from __future__ import annotations

import threading
import time
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
from .oauth_server import OAuthCallbackServer, find_available_callback_port
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
    _browser_flow_lock = threading.Lock()
    _browser_flow: _BrowserLoginFlow | None = None

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

    def start_browser_login(self, *, callback_port: int = DEFAULT_CALLBACK_PORT) -> str:
        with type(self)._browser_flow_lock:
            existing = type(self)._browser_flow
            if existing is not None and not existing.completed:
                return existing.auth_url
            resolved_port = find_available_callback_port(callback_port)
            state, pkce, auth_url = build_browser_login_state(resolved_port)
            server = OAuthCallbackServer(resolved_port)
            server.start()
            flow = _BrowserLoginFlow(
                auth_url=auth_url,
                state=state,
                pkce=pkce,
                callback_port=resolved_port,
                server=server,
                started_at=time.time(),
            )
            worker = threading.Thread(
                target=self._complete_browser_login,
                args=(flow,),
                daemon=True,
            )
            flow.thread = worker
            type(self)._browser_flow = flow
            worker.start()
            return auth_url

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
        pending = self.browser_login_pending()
        detail = (
            "Native experimental Codex OAuth prototype is available for local auth "
            "and direct execution."
        )
        if pending:
            detail = (
                "Browser OAuth flow is in progress. Complete the OpenAI auth page in the "
                "new tab, then return here."
            )
        return ExperimentalAuthStatus(
            provider=self.provider_name,
            mode="experimental",
            implementation_state="prototype",
            authenticated=bundle is not None,
            can_refresh=bundle is not None and bool(bundle.refresh_token),
            storage_secure=storage_is_secure(self._store.path),
            token_path=str(self._store.path),
            expires_at=bundle.expires_at if bundle is not None else None,
            detail=detail,
            metadata={
                **(bundle.metadata if bundle is not None else {}),
                "browser_login_pending": pending,
            },
        )

    def current_access_token(self) -> str | None:
        bundle = self._store.load()
        if bundle is None:
            return None
        return bundle.access_token

    def browser_login_pending(self) -> bool:
        with type(self)._browser_flow_lock:
            flow = type(self)._browser_flow
            return flow is not None and not flow.completed

    def _complete_browser_login(self, flow: _BrowserLoginFlow) -> None:
        try:
            callback = flow.server.wait_for_callback(timeout_seconds=300)
            if callback.error:
                raise CodexOAuthError(
                    f"Codex OAuth callback failed: {callback.error}"
                    + (
                        f" ({callback.error_description})"
                        if callback.error_description
                        else ""
                    )
                )
            if not callback.code or not callback.state:
                raise CodexOAuthError(
                    "Codex OAuth callback did not return a code and state."
                )
            if callback.state != flow.state:
                raise CodexOAuthError("Codex OAuth callback state mismatch.")
            bundle = self._client.exchange_code_for_tokens(
                callback.code,
                flow.pkce,
                flow.callback_port,
            )
            self._store.save(bundle)
        except (CodexOAuthError, OSError, RuntimeError, ValueError) as error:
            flow.error = str(error)
        finally:
            flow.completed = True
            flow.server.stop()
            with type(self)._browser_flow_lock:
                if type(self)._browser_flow is flow:
                    type(self)._browser_flow = None


class _BrowserLoginFlow:
    def __init__(
        self,
        *,
        auth_url: str,
        state: str,
        pkce,
        callback_port: int,
        server: OAuthCallbackServer,
        started_at: float,
    ) -> None:
        self.auth_url = auth_url
        self.state = state
        self.pkce = pkce
        self.callback_port = callback_port
        self.server = server
        self.started_at = started_at
        self.thread: threading.Thread | None = None
        self.completed = False
        self.error: str | None = None


def _default_codex_token_path() -> Path:
    return Path.home() / ".syncore" / "auth" / "codex" / "token.json"
