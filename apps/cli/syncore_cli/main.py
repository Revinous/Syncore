from __future__ import annotations

import typer

from .commands.metrics import register_metrics_commands
from .commands.notifications import register_notification_commands
from .commands.codex_auth import register_codex_auth_commands
from .commands.openai_auth import register_openai_auth_commands
from .commands.run import register_run_commands
from .commands.system import register_system_commands
from .commands.task import register_task_commands
from .commands.workspace import register_workspace_commands
from .config import load_config
from .dependencies import (
    build_client,
    codex_auth_provider,
    openai_models_client,
    openai_store,
    start_api,
    start_web,
    try_open_browser,
)
from .openai_auth import OpenAIModelClient, OpenAIAuthStore
from .presentation import (
    latest_model_switch,
    run_result_lines,
    task_detail_lines,
    truncate_text,
)
from .render import (
    print_error,
    print_json,
    print_kv_panel,
    print_lines_panel,
    print_status_table,
    print_table,
)
from .tui import SyncoreTuiApp
from .workspace_resolution import resolve_or_create_workspace, resolve_workspace_id


TYPER_KWARGS = {
    "rich_markup_mode": None,
    "pretty_exceptions_enable": False,
}

app = typer.Typer(name="syncore", help="Syncore CLI", **TYPER_KWARGS)
workspace_app = typer.Typer(name="workspace", help="Workspace commands", **TYPER_KWARGS)
task_app = typer.Typer(name="task", help="Task commands", **TYPER_KWARGS)
run_app = typer.Typer(name="run", help="Agent run commands", **TYPER_KWARGS)
metrics_app = typer.Typer(name="metrics", help="Metrics commands", **TYPER_KWARGS)
notifications_app = typer.Typer(
    name="notifications", help="Notification inbox commands", **TYPER_KWARGS
)
auth_app = typer.Typer(name="auth", help="Authentication commands", **TYPER_KWARGS)
codex_auth_app = typer.Typer(
    name="codex", help="Experimental Codex auth commands", **TYPER_KWARGS
)
openai_auth_app = typer.Typer(
    name="openai", help="OpenAI auth commands", **TYPER_KWARGS
)
app.add_typer(workspace_app, name="workspace")
app.add_typer(task_app, name="task")
app.add_typer(run_app, name="run")
app.add_typer(metrics_app, name="metrics")
app.add_typer(notifications_app, name="notifications")
app.add_typer(auth_app, name="auth")
auth_app.add_typer(codex_auth_app, name="codex")
auth_app.add_typer(openai_auth_app, name="openai")


# Keep thin wrappers here so CLI tests can monkeypatch stable public seams.
def _client(config=None):
    return build_client(config)


def _client_for_commands(config=None):
    if config is None:
        return _client()
    return _client(config)


def _ensure_api_running(config) -> None:
    start_api(config)


def _ensure_web_running() -> str:
    return start_web()


def _open_browser(url: str) -> bool:
    return try_open_browser(url)


def _launch_tui(config, selected_workspace_id: str | None, selected_workspace_name: str | None) -> None:
    SyncoreTuiApp(
        config,
        selected_workspace_id=selected_workspace_id,
        selected_workspace_name=selected_workspace_name,
    ).run()


def _openai_store() -> OpenAIAuthStore:
    return openai_store()


def _openai_models_client(config=None) -> OpenAIModelClient:
    return openai_models_client(config)


def _codex_auth_provider():
    return codex_auth_provider()


register_workspace_commands(
    workspace_app,
    client_factory=lambda: _client(),
    resolve_workspace_id=resolve_workspace_id,
    print_error=print_error,
    print_json=print_json,
)

register_system_commands(
    app,
    client_factory=lambda config=None: _client_for_commands(config),
    load_config=lambda: load_config(),
    ensure_api_running=lambda config: _ensure_api_running(config),
    ensure_web_running=lambda: _ensure_web_running(),
    open_browser=lambda url: _open_browser(url),
    launch_tui=_launch_tui,
    resolve_or_create_workspace=lambda client, workspace_id_or_name: resolve_or_create_workspace(
        client, workspace_id_or_name
    ),
    print_error=print_error,
    print_json=print_json,
    print_kv_panel=print_kv_panel,
    print_lines_panel=print_lines_panel,
    print_status_table=print_status_table,
    print_table=print_table,
)

register_metrics_commands(
    metrics_app,
    client_factory=lambda: _client(),
    print_error=print_error,
    print_json=print_json,
    print_kv_panel=print_kv_panel,
    print_table=print_table,
)

register_run_commands(
    run_app,
    client_factory=lambda: _client(),
    run_result_lines=run_result_lines,
    truncate_text=truncate_text,
    print_error=print_error,
    print_json=print_json,
    print_kv_panel=print_kv_panel,
    print_lines_panel=print_lines_panel,
    print_table=print_table,
)

register_notification_commands(
    notifications_app,
    client_factory=lambda: _client(),
    print_error=print_error,
    print_json=print_json,
    print_kv_panel=print_kv_panel,
    print_table=print_table,
)

register_task_commands(
    task_app,
    app,
    client_factory=lambda: _client(),
    resolve_workspace_id=resolve_workspace_id,
    task_detail_lines=task_detail_lines,
    latest_model_switch=latest_model_switch,
    print_error=print_error,
    print_json=print_json,
    print_kv_panel=print_kv_panel,
    print_lines_panel=print_lines_panel,
    print_table=print_table,
)

register_openai_auth_commands(
    openai_auth_app,
    store_factory=lambda: _openai_store(),
    models_client_factory=lambda: _openai_models_client(),
    print_error=print_error,
    print_json=print_json,
    print_table=print_table,
)

register_codex_auth_commands(
    codex_auth_app,
    provider_factory=lambda: _codex_auth_provider(),
    print_error=print_error,
    print_json=print_json,
)


if __name__ == "__main__":
    app()
