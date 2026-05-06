from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
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
    print_lines_panel,
    print_status_table,
    print_table,
)
from .tui import SyncoreTuiApp


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
openai_auth_app = typer.Typer(
    name="openai", help="OpenAI auth commands", **TYPER_KWARGS
)
app.add_typer(workspace_app, name="workspace")
app.add_typer(task_app, name="task")
app.add_typer(run_app, name="run")
app.add_typer(metrics_app, name="metrics")
app.add_typer(notifications_app, name="notifications")
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


def _latest_model_switch(events: list[dict[str, object]]) -> dict[str, object] | None:
    for event in reversed(events):
        if str(event.get("event_type")) != "model.switch.completed":
            continue
        event_data = event.get("event_data")
        if isinstance(event_data, dict):
            return event_data
    return None


def _truncate_text(value: object, limit: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _task_detail_lines(
    task: dict[str, object],
    events: list[dict[str, object]],
    baton: dict[str, object] | None,
    digest: dict[str, object] | None,
    execution_report: dict[str, object] | None,
) -> list[str]:
    task_payload = task.get("task", task) if isinstance(task, dict) else {}
    if not isinstance(task_payload, dict):
        task_payload = {}
    lines = [
        f"Task: {task_payload.get('title', '-')}",
        f"ID: {task_payload.get('id', '-')}",
        f"Status: {task_payload.get('status', '-')}",
        f"Type: {task_payload.get('task_type', '-')}",
        f"Complexity: {task_payload.get('complexity', '-')}",
        f"Workspace: {task_payload.get('workspace_id') or '-'}",
        "",
        f"Recent events: {len(events)}",
    ]
    if baton:
        lines.append(f"Latest baton: {baton.get('summary', baton.get('id', '-'))}")
    if digest:
        lines.append(f"Digest: {_truncate_text(digest.get('headline') or digest.get('summary', '-'))}")
    if execution_report:
        changed_files = execution_report.get("changed_files") or []
        verification_commands = execution_report.get("verification_commands") or []
        lines.extend(
            [
                "",
                "Execution outcome:",
                f"- outcome: {execution_report.get('outcome', '-')}",
                f"- meaningful_change: {execution_report.get('meaningful_change', '-')}",
                f"- verification: {execution_report.get('verification_status', '-')}",
                f"- reason: {_truncate_text(execution_report.get('summary_reason', '-'))}",
                f"- changed files: {len(changed_files)}",
                f"- verification commands: {len(verification_commands)}",
            ]
        )
        for path in list(changed_files)[:5]:
            lines.append(f"  • {path}")
    return lines


def _run_result_lines(result: dict[str, object]) -> list[str]:
    output_text = _truncate_text(result.get("output_text"), 500)
    return [
        f"Run ID: {result.get('run_id', '-')}",
        f"Task ID: {result.get('task_id', '-')}",
        f"Status: {result.get('status', '-')}",
        f"Prompt ref: {result.get('prompt_ref_id') or '-'}",
        f"Context ref: {result.get('context_ref_id') or '-'}",
        f"Output ref: {result.get('output_ref_id') or '-'}",
        f"Retrieval hint: {result.get('retrieval_hint') or '-'}",
        "",
        f"Summary: {_truncate_text(result.get('output_summary', '-'))}",
        "",
        "Output preview:",
        output_text or "(no output text)",
    ]


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


def _web_url() -> str:
    return os.getenv("SYNCORE_WEB_URL", "http://localhost:3000").rstrip("/")


def _ensure_web_running() -> str:
    web_url = _web_url()
    parsed = urlparse(web_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 3000
    if host not in {"localhost", "127.0.0.1"}:
        raise SyncoreApiError(
            f"Syncore Web UI is configured at {web_url}. Auto-start supports local URLs only."
        )

    health_url = f"{parsed.scheme or 'http'}://{host}:{port}"
    try:
        with urlopen(health_url, timeout=1.5):
            return web_url
    except URLError:
        pass

    repo_root = _repo_root()
    next_bin = repo_root / "apps/web/node_modules/.bin/next"
    if not next_bin.exists():
        raise SyncoreApiError(
            f"Missing Next.js dev binary at {next_bin}. Run `make install-local`."
        )

    env = os.environ.copy()
    env.setdefault("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000")
    env.setdefault("ORCHESTRATOR_INTERNAL_URL", env["NEXT_PUBLIC_API_BASE_URL"])

    log_dir = repo_root / ".syncore"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "web-cli.log"

    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            [str(next_bin), "dev", "--port", str(port)],
            cwd=repo_root / "apps/web",
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            with urlopen(health_url, timeout=1.5):
                return web_url
        except URLError:
            time.sleep(0.25)

    raise SyncoreApiError(
        f"Failed to start Web UI at {web_url}. See logs: {log_path}"
    )


def _open_browser(url: str) -> bool:
    if os.name == "nt":
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        except OSError:
            return False

    commands: list[list[str]] = []
    if os.getenv("WSL_DISTRO_NAME"):
        if shutil.which("wslview"):
            commands.append(["wslview", url])
        if shutil.which("cmd.exe"):
            commands.append(["cmd.exe", "/c", "start", "", url])
    elif sys.platform == "darwin":
        commands.append(["open", url])
    else:
        has_display = bool(os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))
        if has_display and shutil.which("xdg-open"):
            commands.append(["xdg-open", url])

    for command in commands:
        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except OSError:
            continue

    return False


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


@metrics_app.command("context")
def metrics_context(
    json_output: bool = typer.Option(False, "--json"),
    limit: int = typer.Option(200, "--limit", min=1, max=1000),
) -> None:
    client = _client()
    try:
        payload = client.context_efficiency_metrics(limit=limit)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    if json_output:
        print_json(payload)
        return

    totals = payload.get("totals", {})
    print_kv_panel(
        "Context Efficiency",
        {
            "bundle_count": payload.get("bundle_count", 0),
            "raw_tokens": totals.get("raw_tokens", 0),
            "optimized_tokens": totals.get("optimized_tokens", 0),
            "saved_tokens": totals.get("saved_tokens", 0),
            "savings_pct": totals.get("savings_pct", 0),
            "cost_saved_usd": (payload.get("cost_totals") or {}).get("saved_usd", "n/a"),
        },
    )


@metrics_app.command("layering")
def metrics_layering(
    json_output: bool = typer.Option(False, "--json"),
    limit: int = typer.Option(500, "--limit", min=1, max=2000),
) -> None:
    client = _client()
    try:
        payload = client.context_efficiency_metrics(limit=limit)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    if json_output:
        print_json(payload.get("layering_profiles", {}))
        return

    profiles = payload.get("layering_profiles", {})
    if not isinstance(profiles, dict) or not profiles:
        print_kv_panel("Layering Rollout", {"profiles": 0})
        return

    rows: list[list[str]] = []
    for profile, stats in profiles.items():
        if not isinstance(stats, dict):
            continue
        legacy_tokens = int(stats.get("legacy_tokens", 0) or 0)
        layered_tokens = int(stats.get("layered_tokens", 0) or 0)
        comparison_count = int(stats.get("comparison_count", 0) or 0)
        delta = legacy_tokens - layered_tokens
        pct = round((delta / legacy_tokens) * 100.0, 2) if legacy_tokens > 0 else 0.0
        rows.append(
            [
                str(profile),
                str(stats.get("bundle_count", 0)),
                str(stats.get("layering_modes", {})),
                str(delta),
                f"{pct}%",
                str(comparison_count),
            ]
        )
    rows.sort(key=lambda row: row[0])
    print_table(
        "Layering Rollout Profiles",
        ["profile", "bundles", "modes", "token_delta", "delta_pct", "samples"],
        rows,
    )


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
        try:
            model_switches = client.list_task_model_switches(task_id, limit=25)
        except SyncoreApiError:
            model_switches = []
        try:
            model_policy = client.get_task_model_policy(task_id)
        except SyncoreApiError:
            model_policy = None
        try:
            execution_report = client.get_task_execution_report(task_id)
        except SyncoreApiError:
            execution_report = None
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    payload = {
        "task": task,
        "recent_events": events,
        "latest_baton": baton,
        "digest": digest,
        "execution_report": execution_report,
        "latest_model_switch": _latest_model_switch(events),
        "model_switches": model_switches,
        "model_policy": model_policy,
    }
    if json_output:
        print_json(payload)
        return
    print_lines_panel(
        "Task Detail",
        _task_detail_lines(task, events, baton, digest, execution_report),
    )


@task_app.command("model-policy")
def task_model_policy(
    task_id: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    client = _client()
    try:
        policy = client.get_task_model_policy(task_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    if json_output:
        print_json(policy)
        return
    print_kv_panel("Task Model Policy", policy)


@task_app.command("set-model-policy")
def task_set_model_policy(
    task_id: str,
    default_provider: str | None = typer.Option(None, "--default-provider"),
    default_model: str | None = typer.Option(None, "--default-model"),
    plan_provider: str | None = typer.Option(None, "--plan-provider"),
    plan_model: str | None = typer.Option(None, "--plan-model"),
    execute_provider: str | None = typer.Option(None, "--execute-provider"),
    execute_model: str | None = typer.Option(None, "--execute-model"),
    review_provider: str | None = typer.Option(None, "--review-provider"),
    review_model: str | None = typer.Option(None, "--review-model"),
    fallback_order: str | None = typer.Option(None, "--fallback-order"),
    prefer_reviewer_provider: bool | None = typer.Option(None, "--prefer-reviewer-provider/--no-prefer-reviewer-provider"),
    optimization_goal: str | None = typer.Option(None, "--optimization-goal"),
    allow_cross_provider_switching: bool | None = typer.Option(None, "--allow-cross-provider-switching/--no-allow-cross-provider-switching"),
    maintain_context_continuity: bool | None = typer.Option(None, "--maintain-context-continuity/--no-maintain-context-continuity"),
    minimum_context_window: int | None = typer.Option(None, "--minimum-context-window"),
    max_latency_tier: str | None = typer.Option(None, "--max-latency-tier"),
    max_cost_tier: str | None = typer.Option(None, "--max-cost-tier"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    client = _client()
    payload: dict[str, object] = {}
    mapping = {
        "default_provider": default_provider,
        "default_model": default_model,
        "plan_provider": plan_provider,
        "plan_model": plan_model,
        "execute_provider": execute_provider,
        "execute_model": execute_model,
        "review_provider": review_provider,
        "review_model": review_model,
    }
    for key, value in mapping.items():
        if value is not None:
            payload[key] = value
    if fallback_order is not None:
        payload["fallback_order"] = [item.strip() for item in fallback_order.split(",") if item.strip()]
    if prefer_reviewer_provider is not None:
        payload["prefer_reviewer_provider"] = prefer_reviewer_provider
    if optimization_goal is not None:
        payload["optimization_goal"] = optimization_goal
    if allow_cross_provider_switching is not None:
        payload["allow_cross_provider_switching"] = allow_cross_provider_switching
    if maintain_context_continuity is not None:
        payload["maintain_context_continuity"] = maintain_context_continuity
    if minimum_context_window is not None:
        payload["minimum_context_window"] = minimum_context_window
    if max_latency_tier is not None:
        payload["max_latency_tier"] = max_latency_tier
    if max_cost_tier is not None:
        payload["max_cost_tier"] = max_cost_tier
    try:
        policy = client.update_task_model_policy(task_id, payload)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    if json_output:
        print_json(policy)
        return
    print_kv_panel("Updated Task Model Policy", policy)


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


@task_app.command("set-prefs")
def task_set_prefs(
    task_id: str,
    preferred_agent_role: str = typer.Option("coder", "--agent-role"),
    preferred_provider: str = typer.Option("", "--provider"),
    preferred_model: str = typer.Option("", "--model"),
    execution_prompt: str = typer.Option("", "--prompt"),
    requires_approval: bool = typer.Option(False, "--requires-approval"),
    sdlc_enforce: bool = typer.Option(False, "--sdlc-enforce"),
) -> None:
    client = _client()
    payload = {
        "task_id": task_id,
        "event_type": "task.preferences",
        "event_data": {
            "preferred_agent_role": preferred_agent_role.strip().lower() or "coder",
            "execution_prompt": execution_prompt.strip(),
            "requires_approval": "true" if requires_approval else "false",
            "sdlc_enforce": "true" if sdlc_enforce else "false",
        },
    }
    provider = preferred_provider.strip().lower()
    model = preferred_model.strip()
    if provider:
        payload["event_data"]["preferred_provider"] = provider
    if model:
        payload["event_data"]["preferred_model"] = model
    try:
        event = client.create_project_event(payload)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    print_json(event)


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
            _truncate_text(run.get("output_summary") or run.get("error_message") or "", 48),
            str(run.get("updated_at")),
        ]
        for run in runs
    ]
    print_table(
        "Agent Runs",
        ["id", "task_id", "role", "status", "result", "updated_at"],
        rows,
    )


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


@run_app.command("execute")
def run_execute(
    task_id: str,
    prompt: str = typer.Argument(...),
    target_agent: str = typer.Option("coder", "--target-agent"),
    token_budget: int = typer.Option(8000, "--token-budget"),
    provider: str | None = typer.Option(None, "--provider"),
    model: str | None = typer.Option(None, "--model"),
    agent_role: str = typer.Option("coder", "--agent-role"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    client = _client()
    payload = {
        "task_id": task_id,
        "prompt": prompt,
        "target_agent": target_agent,
        "token_budget": token_budget,
        "provider": provider,
        "target_model": model,
        "agent_role": agent_role,
    }
    try:
        response = client.execute_run_auto(payload)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    if json_output:
        print_json(response)
        return
    print_kv_panel("Run Executed", response)


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
    print_lines_panel("Run Result", _run_result_lines(result))


@run_app.command("cancel")
def run_cancel(run_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    client = _client()
    try:
        payload = client.cancel_agent_run(run_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    if json_output:
        print_json(payload)
        return
    print_kv_panel("Run Canceled", payload)


@run_app.command("resume")
def run_resume(run_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    client = _client()
    try:
        payload = client.resume_agent_run(run_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    if json_output:
        print_json(payload)
        return
    print_kv_panel("Run Resumed", payload)


@app.command("events")
def events(task_id: str) -> None:
    client = _client()
    try:
        payload = client.list_task_events(task_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    print_json(payload)


@app.command(
    "inspect",
    help="Inspect a task with execution outcome, digest, baton, and recent event context in one operator-friendly view.",
)
def inspect_task(task_id: str) -> None:
    task_show(task_id, json_output=False)


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


@notifications_app.command("list")
def notifications_list(
    json_output: bool = typer.Option(False, "--json"),
    acknowledged: bool | None = typer.Option(None, "--acknowledged"),
    limit: int = typer.Option(100, "--limit", min=1, max=500),
) -> None:
    client = _client()
    try:
        payload = client.list_notifications(acknowledged=acknowledged, limit=limit)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)

    items = payload.get("items", []) if isinstance(payload, dict) else []
    if json_output:
        print_json(payload)
        return
    rows = [
        [
            str(item.get("id")),
            str(item.get("category")),
            str(item.get("title")),
            "yes" if item.get("acknowledged") else "no",
            str(item.get("created_at")),
        ]
        for item in items
    ]
    print_table(
        "Notifications",
        ["id", "category", "title", "ack", "created_at"],
        rows,
    )


@notifications_app.command("show")
def notifications_show(
    notification_id: str, json_output: bool = typer.Option(False, "--json")
) -> None:
    client = _client()
    try:
        payload = client.get_notification(notification_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    if json_output:
        print_json(payload)
        return
    print_kv_panel("Notification", payload)


@notifications_app.command("ack")
def notifications_ack(
    notification_id: str, json_output: bool = typer.Option(False, "--json")
) -> None:
    client = _client()
    try:
        payload = client.acknowledge_notification(notification_id)
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    if json_output:
        print_json(payload)
        return
    print_kv_panel("Acknowledged", payload)


@app.command("providers")
def providers(json_output: bool = typer.Option(False, "--json")) -> None:
    client = _client()
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
        _ensure_api_running(config)
        web_url = _ensure_web_running()
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

    selected_workspace_name = str(workspace.get("name", workspace_id))
    should_open_tui = tui or not web and not headless
    if web:
        workspace_url = f"{web_url}/workspaces"
        if _open_browser(workspace_url):
            typer.echo(f"Web UI: {workspace_url}")
        else:
            typer.echo(f"Web UI ready: {workspace_url}")
    if headless:
        typer.echo(f"Services ready: API={config.api_url} WEB={web_url}")
        return
    if should_open_tui:
        SyncoreTuiApp(
            config,
            selected_workspace_id=workspace_id,
            selected_workspace_name=selected_workspace_name,
        ).run()


@app.command("web", help="Start the local API and Web UI, then open the browser.")
def web() -> None:
    config = load_config()
    try:
        _ensure_api_running(config)
        web_url = _ensure_web_running()
    except SyncoreApiError as error:
        print_error(str(error))
        raise typer.Exit(code=1)
    if _open_browser(web_url):
        typer.echo(f"Web UI: {web_url}")
    else:
        typer.echo(f"Web UI ready: {web_url}")


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
