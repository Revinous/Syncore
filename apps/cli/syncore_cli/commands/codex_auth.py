from __future__ import annotations

from typing import Callable

import typer

from services.orchestrator.app.experimental_auth import ExperimentalCodexAuthProvider
from services.orchestrator.app.experimental_auth.codex_client import DEFAULT_CALLBACK_PORT, CodexOAuthError


CodexProviderFactory = Callable[[], ExperimentalCodexAuthProvider]


def register_codex_auth_commands(
    codex_auth_app: typer.Typer,
    *,
    provider_factory: CodexProviderFactory,
    print_error: Callable[[str], None],
    print_json: Callable[[object], None],
) -> None:
    @codex_auth_app.command("status")
    def codex_status() -> None:
        provider = provider_factory()
        status = provider.status()
        print_json(
            {
                "provider": status.provider,
                "mode": status.mode,
                "implementation_state": status.implementation_state,
                "authenticated": status.authenticated,
                "can_refresh": status.can_refresh,
                "storage_secure": status.storage_secure,
                "token_path": status.token_path,
                "expires_at": status.expires_at,
                "detail": status.detail,
                "metadata": status.metadata,
            }
        )

    @codex_auth_app.command("login")
    def codex_login(
        device: bool = typer.Option(
            False,
            "--device",
            help="Use the experimental device flow instead of the browser callback flow.",
        ),
        no_browser: bool = typer.Option(
            False,
            "--no-browser",
            help="Do not try to open the browser automatically for the callback flow.",
        ),
        callback_port: int = typer.Option(
            DEFAULT_CALLBACK_PORT,
            "--callback-port",
            min=1,
            max=65535,
            help="Local port for the loopback OAuth callback server.",
        ),
    ) -> None:
        provider = provider_factory()
        try:
            if device:
                bundle, device_info = provider.login_device()
                print_json(
                    {
                        "status": "connected",
                        "provider": provider.provider_name,
                        "mode": "experimental",
                        "login_flow": "device",
                        "token_path": str(provider.token_path),
                        "expires_at": bundle.expires_at,
                        "metadata": bundle.metadata,
                        "verification_url": device_info["verification_url"],
                        "user_code": device_info["user_code"],
                    }
                )
                return
            bundle, auth_url = provider.login_browser(
                callback_port=callback_port,
                no_browser=no_browser,
            )
        except CodexOAuthError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        print_json(
            {
                "status": "connected",
                "provider": provider.provider_name,
                "mode": "experimental",
                "login_flow": "browser",
                "token_path": str(provider.token_path),
                "expires_at": bundle.expires_at,
                "metadata": bundle.metadata,
                "auth_url": auth_url,
            }
        )

    @codex_auth_app.command("refresh")
    def codex_refresh() -> None:
        provider = provider_factory()
        try:
            bundle = provider.refresh()
        except CodexOAuthError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(
            {
                "status": "refreshed",
                "provider": provider.provider_name,
                "token_path": str(provider.token_path),
                "expires_at": bundle.expires_at,
                "metadata": bundle.metadata,
            }
        )

    @codex_auth_app.command("logout")
    def codex_logout() -> None:
        provider = provider_factory()
        provider.clear()
        print_json(
            {
                "status": "cleared",
                "token_path": str(provider.token_path),
                "provider": provider.provider_name,
            }
        )
