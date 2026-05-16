from __future__ import annotations

from typing import Callable

import typer

from services.orchestrator.app.experimental_auth import ExperimentalCodexAuthProvider


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
                "token_path": status.token_path,
                "expires_at": status.expires_at,
                "detail": status.detail,
                "metadata": status.metadata,
            }
        )

    @codex_auth_app.command("login")
    def codex_login() -> None:
        print_error(
            "Native experimental Codex OAuth is not implemented yet. Use the `codex_sidecar` bridge for execution today."
        )
        raise typer.Exit(code=1)

    @codex_auth_app.command("logout")
    def codex_logout() -> None:
        provider = provider_factory()
        provider.clear()
        print_json({"status": "cleared", "token_path": str(provider.token_path), "provider": provider.provider_name})
