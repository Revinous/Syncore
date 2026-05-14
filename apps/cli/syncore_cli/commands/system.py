from __future__ import annotations

from typing import Callable

import typer

from syncore_cli.client import SyncoreApiClient, SyncoreApiError
from syncore_cli.config import CliConfig


ClientFactory = Callable[[CliConfig | None], SyncoreApiClient]
ResolveOrCreateWorkspace = Callable[[SyncoreApiClient, str], tuple[str, dict[str, object]]]
LaunchTui = Callable[[CliConfig, str | None, str | None], None]


def register_system_commands(
    app: typer.Typer,
    *,
    client_factory: ClientFactory,
    load_config: Callable[[], CliConfig],
    ensure_api_running: Callable[[CliConfig], None],
    ensure_web_running: Callable[[], str],
    open_browser: Callable[[str], bool],
    launch_tui: LaunchTui,
    resolve_or_create_workspace: ResolveOrCreateWorkspace,
    print_error: Callable[[str], None],
    print_json: Callable[[object], None],
    print_kv_panel: Callable[[str, object], None],
    print_status_table: Callable[[object, object], None],
    print_table: Callable[[str, list[str], list[list[str]]], None],
) -> None:
    def build_client(config: CliConfig | None = None) -> SyncoreApiClient:
        if config is None:
            return client_factory()
        return client_factory(config)

    @app.command("status")
    def status(json_output: bool = typer.Option(False, "--json")) -> None:
        client = build_client()
        try:
            health = client.health()
            services = client.services_health()
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        if json_output:
            print_json({"health": health, "services": services})
            return
        print_status_table(health, services)

    @app.command("dashboard")
    def dashboard(json_output: bool = typer.Option(False, "--json")) -> None:
        client = build_client()
        try:
            summary = client.dashboard_summary()
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        if json_output:
            print_json(summary)
            return
        print_kv_panel("Dashboard", summary)

    @app.command("diagnostics")
    def diagnostics() -> None:
        client = build_client()
        try:
            payload = {
                "overview": client.diagnostics(),
                "config": client.diagnostics_config(),
                "routes": client.diagnostics_routes(),
                "health": client.health(),
                "services": client.services_health(),
            }
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(payload)

    @app.command("providers")
    def providers(json_output: bool = typer.Option(False, "--json")) -> None:
        client = build_client()
        try:
            rows = client.list_run_providers()
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        if json_output:
            print_json(rows)
            return
        table_rows = [
            [
                str(item.get("provider")),
                str(item.get("model_hint")),
                str(item.get("supports_streaming")),
                str(item.get("supports_system_prompt")),
            ]
            for item in rows
        ]
        print_table(
            "Run Providers",
            ["provider", "model_hint", "streaming", "system_prompt"],
            table_rows,
        )

    @app.command(
        "open",
        help=(
            "Start local Syncore services if needed, resolve or create a workspace, "
            "and open the requested operator surface."
        ),
    )
    def open_workspace(
        workspace_id_or_name: str = typer.Argument(
            ...,
            help=(
                "Workspace id, workspace name, or local repo directory to open. "
                "If a local directory is not registered yet, Syncore creates the workspace first."
            ),
            metavar="WORKSPACE",
        ),
        web: bool = typer.Option(
            False,
            "--web",
            help=(
                "Open the Web UI in your browser after starting local services. "
                "Use this when you want the browser control panel instead of the TUI."
            ),
        ),
        tui: bool = typer.Option(
            False,
            "--tui",
            help=(
                "Open the terminal UI after startup. This is the default if you do not pass "
                "--web or --headless."
            ),
        ),
        headless: bool = typer.Option(
            False,
            "--headless",
            help=(
                "Start local services and resolve the workspace without opening the Web UI or TUI. "
                "Use this for background startup or scripting."
            ),
        ),
    ) -> None:
        config = load_config()
        try:
            ensure_api_running(config)
            web_url = ensure_web_running()
            client = build_client(config)
            workspace_id, workspace = resolve_or_create_workspace(client, workspace_id_or_name)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        typer.echo(
            f"Opening workspace: {workspace.get('name', workspace_id)} "
            f"({workspace.get('root_path', 'unknown')})"
        )

        selected_workspace_name = str(workspace.get("name", workspace_id))
        should_open_tui = tui or (not web and not headless)
        if web:
            workspace_url = f"{web_url}/workspaces"
            if open_browser(workspace_url):
                typer.echo(f"Web UI: {workspace_url}")
            else:
                typer.echo(f"Web UI ready: {workspace_url}")
        if headless:
            typer.echo(f"Services ready: API={config.api_url} WEB={web_url}")
            return
        if should_open_tui:
            launch_tui(config, workspace_id, selected_workspace_name)

    @app.command("web", help="Start the local API and Web UI, then open the browser.")
    def web() -> None:
        config = load_config()
        try:
            ensure_api_running(config)
            resolved_web_url = ensure_web_running()
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        if open_browser(resolved_web_url):
            typer.echo(f"Web UI: {resolved_web_url}")
        else:
            typer.echo(f"Web UI ready: {resolved_web_url}")

    @app.command("tui")
    def tui() -> None:
        config = load_config()
        try:
            ensure_api_running(config)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        launch_tui(config, None, None)
