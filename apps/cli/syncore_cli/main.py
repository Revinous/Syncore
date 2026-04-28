from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import typer

from .client import SyncoreApiClient, SyncoreApiError
from .config import load_config
from .openai_auth import OpenAIAuthError, OpenAIAuthStore, OpenAIModelClient, OpenAICredentials
from .render import (
    print_error,
    print_json,
    print_kv_panel,
    print_status_table,
    print_table,
)
from .tui import SyncoreTuiApp

app = typer.Typer(help="Syncore CLI")
workspace_app = typer.Typer(help="Workspace commands")
task_app = typer.Typer(help="Task commands")
run_app = typer.Typer(help="Agent run commands")
auth_app = typer.Typer(help="Authentication commands")
openai_auth_app = typer.Typer(help="OpenAI auth commands")
app.add_typer(workspace_app, name="workspace")
app.add_typer(task_app, name="task")
app.add_typer(run_app, name="run")
app.add_typer(auth_app, name="auth")
auth_app.add_typer(openai_auth_app, name="openai")


def _repo_root() -> Path:
    explicit = os.getenv("SYNCORE_REPO_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def _client(config=None) -> SyncoreApiClient:
    if config is None:
        config = load_config()
    return SyncoreApiClient(config.api_url, config.timeout_seconds)


def _openai_store() -> OpenAIAuthStore:
    return OpenAIAuthStore()


def _openai_models_client(config=None) -> OpenAIModelClient:
    if config is None:
        config = load_config()
    return OpenAIModelClient(timeout_seconds=config.timeout_seconds)


def _resolve_workspace_id(client: SyncoreApiClient, identifier: str) -> str:
    try:
        return str(UUID(identifier))
    except ValueError:
        pass

    workspaces = client.list_workspaces()
    for workspace in workspaces:
        if workspace.get("name") == identifier:
            return str(workspace["id"])

    raise SyncoreApiError(f"Workspace not found: {identifier}")


def _normalize_path(path_str: str) -> Path:
    candidate = Path(path_str).expanduser()
    if not candidate.is_absolute():
        caller_cwd = os.getenv("SYNCORE_CALLER_CWD")
        base = Path(caller_cwd) if caller_cwd else Path.cwd()
        candidate = base / candidate
    return candidate.resolve()


def _find_workspace_by_root(
    workspaces: list[dict[str, object]], root_path: Path
) -> dict[str, object] | None:
    root = str(root_path)
    for workspace in workspaces:
        if str(workspace.get("root_path", "")) == root:
            return workspace
    return None


def _resolve_or_create_workspace(
    client: SyncoreApiClient, workspace_id_or_name: str
) -> tuple[str, dict[str, object]]:
    workspaces = client.list_workspaces()
    for workspace in workspaces:
        if str(workspace.get("id")) == workspace_id_or_name:
            workspace_id = str(workspace["id"])
            return workspace_id, client.get_workspace(workspace_id)
        if str(workspace.get("name")) == workspace_id_or_name:
            workspace_id = str(workspace["id"])
            return workspace_id, client.get_workspace(workspace_id)

    path_candidate = _normalize_path(workspace_id_or_name)
    if path_candidate.exists() and path_candidate.is_dir():
        existing = _find_workspace_by_root(workspaces, path_candidate)
        if existing is not None:
            workspace_id = str(existing["id"])
            return workspace_id, client.get_workspace(workspace_id)

        created = client.create_workspace(
            {
                "name": path_candidate.name or "workspace",
                "root_path": str(path_candidate),
                "repo_url": None,
                "branch": None,
                "runtime_mode": "native",
                "metadata": {},
            }
        )
        workspace_id = str(created["id"])
        return workspace_id, client.get_workspace(workspace_id)

    raise SyncoreApiError(
        f"Workspace not found: {workspace_id_or_name}. "
        "Pass an existing workspace name/id or a local directory path."
    )


def _ensure_api_running(config) -> None:
    client = _client(config)
    try:
        client.health()
        return
    except SyncoreApiError:
        pass

    parsed = urlparse(config.api_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8000
    if host not in {"localhost", "127.0.0.1"}:
        raise SyncoreApiError(
            f"Syncore API is offline at {config.api_url}. Auto-start supports local URLs only."
        )

    runtime_mode = os.getenv("SYNCORE_RUNTIME_MODE", "native")
    db_backend = os.getenv("SYNCORE_DB_BACKEND", "sqlite")
    if runtime_mode != "native" or db_backend != "sqlite":
        raise SyncoreApiError(
            "Syncore API is offline and auto-start requires SYNCORE_RUNTIME_MODE=native and SYNCORE_DB_BACKEND=sqlite."
        )

    repo_root = _repo_root()
    python_bin = repo_root / ".venv/bin/python"
    if not python_bin.exists():
        raise SyncoreApiError(f"Missing virtualenv at {python_bin}. Run `make install-local`.")

    env = os.environ.copy()
    env.setdefault("SYNCORE_RUNTIME_MODE", "native")
    env.setdefault("SYNCORE_DB_BACKEND", "sqlite")
    env.setdefault("SQLITE_DB_PATH", ".syncore/syncore.db")
    env.setdefault("REDIS_REQUIRED", "false")

    subprocess.run(
        ["bash", str(repo_root / "scripts/init_local_sqlite.sh")],
        cwd=repo_root,
        env=env,
        check=True,
    )

    log_dir = repo_root / ".syncore"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "orchestrator-cli.log"

    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            [
                str(python_bin),
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                "services/orchestrator",
                "--host",
                host,
                "--port",
                str(port),
            ],
            cwd=repo_root,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            client.health()
            return
        except SyncoreApiError:
            time.sleep(0.25)

    raise SyncoreApiError(
        f"Failed to start orchestrator at {config.api_url}. See logs: {log_path}"
    )


@openai_auth_app.command("login")
def openai_login(
    api_key: str = typer.Option("", "--api-key", prompt=True, hide_input=True)
) -> None:
    if not api_key.strip():
        print_error("API key cannot be empty")
        raise typer.Exit(code=1)

    store = _openai_store()
    models_client = _openai_models_client()
    try:
        models = models_client.list_text_models(api_key.strip())
    except OpenAIAuthError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    store.save(OpenAICredentials(api_key=api_key.strip()))
    print_json(
        {
            "status": "connected",
            "credential_path": str(store.path),
            "available_models": models[:25],
            "model_count": len(models),
        }
    )


@openai_auth_app.command("logout")
def openai_logout() -> None:
    store = _openai_store()
    store.clear()
    print_json({"status": "disconnected"})


@openai_auth_app.command("status")
def openai_status() -> None:
    store = _openai_store()
    credentials = store.load()
    if credentials is None:
        print_json({"connected": False, "credential_path": str(store.path)})
        return
    print_json({"connected": True, "credential_path": str(store.path)})


@openai_auth_app.command("models")
def openai_models(json_output: bool = typer.Option(False, "--json")) -> None:
    store = _openai_store()
    credentials = store.load()
    if credentials is None:
        print_error("Not connected. Run `syncore auth openai login`.")
        raise typer.Exit(code=1)

    models_client = _openai_models_client()
    try:
        models = models_client.list_text_models(credentials.api_key)
    except OpenAIAuthError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    if json_output:
        print_json({"models": models, "count": len(models)})
        return

    rows = [[model] for model in models]
    print_table("OpenAI Models", ["id"], rows)


@app.command("status")
def status(json_output: bool = typer.Option(False, "--json")) -> None:
    client = _client()
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
    client = _client()
    try:
        summary = client.dashboard_summary()
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    if json_output:
        print_json(summary)
        return

    print_kv_panel("Dashboard", summary)


@workspace_app.command("list")
def workspace_list(json_output: bool = typer.Option(False, "--json")) -> None:
    client = _client()
    try:
        workspaces = client.list_workspaces()
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    if json_output:
        print_json(workspaces)
        return

    rows = [
        [
            str(workspace.get("id")),
            str(workspace.get("name")),
            str(workspace.get("root_path")),
            str(workspace.get("branch") or "-"),
            str(workspace.get("runtime_mode") or "-"),
        ]
        for workspace in workspaces
    ]
    print_table("Workspaces", ["id", "name", "root_path", "branch", "runtime"], rows)


@workspace_app.command("add")
def workspace_add(
    path: str,
    name: str = typer.Option(..., "--name"),
    repo_url: str | None = typer.Option(None, "--repo-url"),
    branch: str | None = typer.Option(None, "--branch"),
) -> None:
    client = _client()
    payload = {
        "name": name,
        "root_path": path,
        "repo_url": repo_url,
        "branch": branch,
        "runtime_mode": "native",
        "metadata": {},
    }
    try:
        created = client.create_workspace(payload)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    print_json(created)


@workspace_app.command("show")
def workspace_show(workspace_id_or_name: str) -> None:
    client = _client()
    try:
        workspace_id = _resolve_workspace_id(client, workspace_id_or_name)
        workspace = client.get_workspace(workspace_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    print_json(workspace)


@workspace_app.command("scan")
def workspace_scan(workspace_id_or_name: str) -> None:
    client = _client()
    try:
        workspace_id = _resolve_workspace_id(client, workspace_id_or_name)
        result = client.scan_workspace(workspace_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    print_json(result)


@workspace_app.command("files")
def workspace_files(workspace_id_or_name: str) -> None:
    client = _client()
    try:
        workspace_id = _resolve_workspace_id(client, workspace_id_or_name)
        files = client.list_workspace_files(workspace_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    print_json(files)


@task_app.command("list")
def task_list(
    workspace: str | None = typer.Option(None, "--workspace"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    client = _client()
    try:
        workspace_id = _resolve_workspace_id(client, workspace) if workspace else None
        tasks = client.list_tasks(workspace_id=workspace_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    if json_output:
        print_json(tasks)
        return

    rows = [
        [
            str(task.get("id")),
            str(task.get("title")),
            str(task.get("status")),
            str(task.get("complexity")),
            str(task.get("workspace_id") or ""),
            str(task.get("updated_at")),
        ]
        for task in tasks
    ]
    print_table(
        "Tasks",
        ["id", "title", "status", "complexity", "workspace_id", "updated_at"],
        rows,
    )


@task_app.command("create")
def task_create(
    title: str,
    workspace: str | None = typer.Option(None, "--workspace"),
    description: str | None = typer.Option(None, "--description"),
    task_type: str = typer.Option("implementation", "--type"),
    complexity: str = typer.Option("medium", "--complexity"),
) -> None:
    client = _client()
    workspace_id: str | None = None
    if workspace:
        try:
            workspace_id = _resolve_workspace_id(client, workspace)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

    full_title = title
    if description:
        full_title = f"{full_title} - {description}"

    payload = {
        "title": full_title,
        "task_type": task_type,
        "complexity": complexity,
        "workspace_id": workspace_id,
    }
    try:
        task = client.create_task(payload)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    print_json(task)


@task_app.command("show")
def task_show(task_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    client = _client()
    try:
        task = client.get_task(task_id)
        events = client.list_task_events(task_id)
        try:
            baton = client.latest_task_baton(task_id)
        except SyncoreApiError:
            baton = None
        try:
            digest = client.get_task_digest(task_id)
        except SyncoreApiError:
            digest = None
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    payload = {
        "task": task,
        "recent_events": events,
        "latest_baton": baton,
        "digest": digest,
    }
    if json_output:
        print_json(payload)
        return
    print_kv_panel("Task Detail", payload)


@task_app.command("switch-model")
def task_switch_model(
    task_id: str,
    provider: str = typer.Option(..., "--provider"),
    model: str = typer.Option(..., "--model"),
    target_agent: str = typer.Option("coder", "--target-agent"),
    token_budget: int = typer.Option(8000, "--token-budget"),
    reason: str | None = typer.Option(None, "--reason"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    client = _client()
    payload = {
        "provider": provider,
        "model": model,
        "target_agent": target_agent,
        "token_budget": token_budget,
        "reason": reason,
    }
    try:
        result = client.switch_task_model(task_id, payload)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    if json_output:
        print_json(result)
        return
    print_kv_panel("Task Model Switch", result)


@run_app.command("list")
def run_list() -> None:
    client = _client()
    try:
        runs = client.list_agent_runs()
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    rows = [
        [
            str(run.get("id")),
            str(run.get("task_id")),
            str(run.get("role")),
            str(run.get("status")),
            str(run.get("updated_at")),
        ]
        for run in runs
    ]
    print_table("Agent Runs", ["id", "task_id", "role", "status", "updated_at"], rows)


@run_app.command("start")
def run_start(
    task_id: str, agent_role: str = typer.Option(..., "--agent-role")
) -> None:
    client = _client()
    try:
        run = client.create_agent_run(
            {
                "task_id": task_id,
                "role": agent_role,
                "status": "queued",
            }
        )
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    print_json(run)


@run_app.command("result")
def run_result(
    run_id: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    client = _client()
    try:
        result = client.get_agent_run_result(run_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    if json_output:
        print_json(result)
        return
    print_kv_panel("Run Result", result)


@app.command("events")
def events(task_id: str) -> None:
    client = _client()
    try:
        payload = client.list_task_events(task_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    print_json(payload)


@app.command("baton")
def baton(task_id: str) -> None:
    client = _client()
    try:
        latest = client.latest_task_baton(task_id)
    except SyncoreApiError:
        latest = None

    try:
        packets = client.list_task_batons(task_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    print_json({"latest": latest, "packets": packets})


@app.command("route")
def route(task_id: str) -> None:
    client = _client()
    try:
        task_detail = client.get_task(task_id)
        task = task_detail.get("task", {})
        decision = client.route_next_action(
            {
                "task_type": task.get("task_type", "analysis"),
                "complexity": task.get("complexity", "medium"),
                "requires_memory": True,
            }
        )
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    print_json(decision)


@app.command("digest")
def digest(task_id: str) -> None:
    client = _client()
    try:
        payload = client.generate_digest({"task_id": task_id, "limit": 50})
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    print_json(payload)


@app.command("diagnostics")
def diagnostics() -> None:
    client = _client()
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


@app.command("open")
def open_workspace(workspace_id_or_name: str) -> None:
    config = load_config()
    try:
        _ensure_api_running(config)
        client = _client(config)
        workspace_id, workspace = _resolve_or_create_workspace(
            client, workspace_id_or_name
        )
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    typer.echo(
        f"Opening workspace: {workspace.get('name', workspace_id)} "
        f"({workspace.get('root_path', 'unknown')})"
    )
    SyncoreTuiApp(
        config,
        selected_workspace_id=workspace_id,
        selected_workspace_name=str(workspace.get("name", workspace_id)),
    ).run()


@app.command("tui")
def tui() -> None:
    config = load_config()
    try:
        _ensure_api_running(config)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    SyncoreTuiApp(config).run()


if __name__ == "__main__":
    app()
