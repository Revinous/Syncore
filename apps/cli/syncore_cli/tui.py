from __future__ import annotations

import re
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from .client import SyncoreApiClient, SyncoreApiError
from .config import CliConfig
from .openai_auth import OpenAIAuthError, OpenAIAuthStore, OpenAIModelClient, OpenAICredentials


TASK_TYPES = (
    "analysis",
    "implementation",
    "integration",
    "review",
    "memory_retrieval",
    "memory_update",
)
COMPLEXITY_LEVELS = ("low", "medium", "high")
AGENT_ROLES = ("planner", "coder", "reviewer", "analyst", "memory")
MODEL_PROVIDERS = ("local_echo", "openai", "anthropic", "google", "xai", "other")
PROVIDER_MODEL_CATALOG: dict[str, list[str]] = {
    "local_echo": ["local_echo"],
    "openai": ["gpt-5.4", "gpt-5.5", "gpt-5.2-codex"],
    "anthropic": ["claude-sonnet-4-20250514", "claude-3-7-sonnet-latest"],
    "google": ["gemini-2.5-pro", "gemini-2.5-flash"],
    "xai": ["grok-3", "grok-3-mini"],
    "other": [],
}
DEFAULT_PROVIDER = "local_echo"
DEFAULT_MODEL = "local_echo"


class NewTaskScreen(ModalScreen[dict[str, str] | None]):
    CSS = """
    #new-task-modal {
      width: 84;
      height: auto;
      border: round $accent;
      padding: 1 2;
      background: $surface;
      align-horizontal: center;
      align-vertical: middle;
    }
    #new-task-actions {
      height: auto;
      layout: horizontal;
      margin-top: 1;
    }
    #new-task-actions Button {
      margin-right: 1;
    }
    #new-task-error {
      color: $error;
      height: auto;
      margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+n", "next_model", "Next Model"),
        ("ctrl+p", "prev_model", "Prev Model"),
        ("tab", "complete_model", "Complete Model"),
    ]

    def __init__(
        self,
        workspace_name: str | None = None,
        available_models: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._workspace_name = workspace_name
        self._available_models = available_models or []
        self._matching_models: list[str] = list(self._available_models[:10])
        self._model_cursor = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="new-task-modal"):
            yield Label("Create Task")
            yield Label(f"Workspace: {self._workspace_name or 'none'}")
            yield Input(
                value=DEFAULT_PROVIDER,
                placeholder="provider (local_echo|openai|anthropic|google|xai|other)",
                id="task-provider",
            )
            yield Input(
                value="",
                placeholder="preferred_model (required)",
                id="task-model",
            )
            if self._available_models:
                yield Label(
                    "Available models: " + ", ".join(self._available_models[:12]),
                    id="task-model-list",
                )
            yield Input(value="medium", placeholder="complexity", id="task-complexity")
            yield Input(placeholder="Task title", id="task-title")
            yield Input(placeholder="Description (optional)", id="task-description")
            yield Input(value="implementation", placeholder="task_type", id="task-type")
            yield Input(
                value="coder",
                placeholder="preferred_agent_role",
                id="task-agent-role",
            )
            yield Input(
                value="false",
                placeholder="requires_approval (true/false)",
                id="task-requires-approval",
            )
            yield Input(
                placeholder="execution prompt (optional)",
                id="task-prompt",
            )
            yield Static("", id="new-task-error")
            with Horizontal(id="new-task-actions"):
                yield Button("Create", id="new-task-create", variant="success")
                yield Button("Cancel", id="new-task-cancel")

    def on_mount(self) -> None:
        self.query_one("#task-provider", Input).focus()
        self._refresh_model_matches()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_next_model(self) -> None:
        if not self._matching_models:
            return
        self._model_cursor = (self._model_cursor + 1) % len(self._matching_models)
        self._apply_selected_model()

    def action_prev_model(self) -> None:
        if not self._matching_models:
            return
        self._model_cursor = (self._model_cursor - 1) % len(self._matching_models)
        self._apply_selected_model()

    def action_complete_model(self) -> None:
        if not self._matching_models:
            return
        self._apply_selected_model()
        self.query_one("#task-prompt", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "task-prompt":
            self._submit()
            return
        if event.input.id == "task-model":
            if self._matching_models:
                self._apply_selected_model()
            self.query_one("#task-complexity", Input).focus()
            return
        if event.input.id == "task-provider":
            self.query_one("#task-model", Input).focus()
            return
        next_field = {
            "task-complexity": "task-title",
            "task-title": "task-description",
            "task-description": "task-type",
            "task-type": "task-agent-role",
            "task-agent-role": "task-requires-approval",
            "task-requires-approval": "task-prompt",
        }.get(event.input.id or "")
        if next_field:
            self.query_one(f"#{next_field}", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "task-model":
            self._refresh_model_matches()
        if event.input.id == "task-provider":
            self._refresh_model_matches()

    def _provider_filtered_models(self) -> list[str]:
        provider = self.query_one("#task-provider", Input).value.strip().lower()
        if not provider:
            provider = DEFAULT_PROVIDER
        if provider == "other":
            return list(self._available_models)
        catalog_models = PROVIDER_MODEL_CATALOG.get(provider, [])
        if provider == "openai":
            dynamic_openai = [m for m in self._available_models if m.startswith(("gpt", "o1", "o3", "o4"))]
            for model in dynamic_openai:
                if model not in catalog_models:
                    catalog_models.append(model)
        return catalog_models if catalog_models else list(self._available_models)

    def _refresh_model_matches(self) -> None:
        scoped_models = self._provider_filtered_models()
        if not scoped_models:
            return

        query = self.query_one("#task-model", Input).value.strip()
        if not query:
            self._matching_models = list(scoped_models[:10])
            self._model_cursor = 0
            self._render_model_matches()
            return

        try:
            pattern = re.compile(query, re.IGNORECASE)
            matches = [model for model in scoped_models if pattern.search(model)]
        except re.error:
            literal = re.escape(query)
            pattern = re.compile(literal, re.IGNORECASE)
            matches = [model for model in scoped_models if pattern.search(model)]

        self._matching_models = matches[:10]
        self._model_cursor = 0
        self._render_model_matches()

    def _render_model_matches(self) -> None:
        if not self._available_models:
            return
        label = self.query_one("#task-model-list", Label)
        provider = self.query_one("#task-provider", Input).value.strip().lower() or "all"
        if not self._matching_models:
            label.update(f"Model matches ({provider}, regex): no matches")
            return
        rendered: list[str] = []
        for index, model in enumerate(self._matching_models):
            marker = ">" if index == self._model_cursor else "-"
            rendered.append(f"{marker} {model}")
        label.update(f"Model matches ({provider}, regex): " + " | ".join(rendered))

    def _apply_selected_model(self) -> None:
        if not self._matching_models:
            return
        selected = self._matching_models[self._model_cursor]
        model_input = self.query_one("#task-model", Input)
        model_input.value = selected
        self._render_model_matches()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-task-cancel":
            self.dismiss(None)
            return
        if event.button.id == "new-task-create":
            self._submit()

    def _submit(self) -> None:
        provider = self.query_one("#task-provider", Input).value.strip().lower()
        title = self.query_one("#task-title", Input).value.strip()
        description = self.query_one("#task-description", Input).value.strip()
        task_type = self.query_one("#task-type", Input).value.strip().lower()
        complexity = self.query_one("#task-complexity", Input).value.strip().lower()
        agent_role = self.query_one("#task-agent-role", Input).value.strip().lower()
        requires_approval = (
            self.query_one("#task-requires-approval", Input).value.strip().lower()
        )
        preferred_model = self.query_one("#task-model", Input).value.strip()
        prompt = self.query_one("#task-prompt", Input).value.strip()

        if not title:
            self.query_one("#new-task-error", Static).update("Task title is required.")
            return
        if not provider:
            self.query_one("#new-task-error", Static).update("Provider is required.")
            return
        if provider not in MODEL_PROVIDERS:
            provider = "other"
        if task_type not in TASK_TYPES:
            task_type = "implementation"
        if complexity not in COMPLEXITY_LEVELS:
            complexity = "medium"
        if agent_role not in AGENT_ROLES:
            agent_role = "coder"
        if not preferred_model:
            self.query_one("#new-task-error", Static).update("Model is required.")
            return

        self.dismiss(
            {
                "title": title,
                "description": description,
                "preferred_provider": provider,
                "task_type": task_type,
                "complexity": complexity,
                "preferred_agent_role": agent_role,
                "preferred_model": preferred_model,
                "execution_prompt": prompt,
                "requires_approval": "true"
                if requires_approval in {"true", "1", "yes", "on"}
                else "false",
            }
        )


class SyncoreTuiApp(App[None]):
    CSS = """
    Screen {
      layout: vertical;
    }
    #body {
      layout: horizontal;
      height: 1fr;
    }
    .pane {
      border: solid gray;
      padding: 1;
      width: 1fr;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("d", "show_dashboard", "Dashboard"),
        ("w", "show_workspaces", "Workspaces"),
        ("t", "show_tasks", "Tasks"),
        ("a", "show_runs", "Runs"),
        ("x", "show_diagnostics", "Diagnostics"),
        ("v", "open_detail", "Open Detail"),
        ("b", "back_view", "Back"),
        ("j", "next_item", "Next"),
        ("k", "prev_item", "Prev"),
        ("n", "new_task", "New Task"),
        ("i", "openai_signin", "OpenAI Signin"),
        ("m", "refresh_models", "Refresh Models"),
        ("s", "scan_workspace", "Scan Workspace"),
        ("g", "generate_digest", "Generate Digest"),
        ("o", "route_next", "Route Next"),
        ("p", "start_agent_run", "Start Run"),
        ("e", "execute_task", "Execute"),
        ("z", "toggle_autonomy", "Autonomy"),
        ("y", "approve_task", "Approve"),
        ("u", "reject_task", "Reject"),
    ]

    current_view = reactive("dashboard")

    def __init__(
        self,
        config: CliConfig,
        selected_workspace_id: str | None = None,
        selected_workspace_name: str | None = None,
    ) -> None:
        super().__init__()
        self._client = SyncoreApiClient(config.api_url, config.timeout_seconds)
        self._openai_store = OpenAIAuthStore()
        self._openai_client = OpenAIModelClient(timeout_seconds=config.timeout_seconds)
        self._config = config
        self._selected_workspace_id = selected_workspace_id
        self._selected_workspace_name = selected_workspace_name
        self._selected_task_id: str | None = None
        self._selected_task_title: str | None = None
        self._selected_workspace_index = 0
        self._selected_task_index = 0
        self._selected_run_index = 0
        self._workspaces: list[dict[str, Any]] = []
        self._tasks: list[dict[str, Any]] = []
        self._runs: list[dict[str, Any]] = []
        self._summary: dict[str, Any] = {}
        self._services: dict[str, Any] = {}
        self._diag_config: dict[str, Any] = {}
        self._diag_routes: dict[str, Any] = {}
        self._task_events: list[dict[str, Any]] = []
        self._task_batons: list[dict[str, Any]] = []
        self._task_runs: list[dict[str, Any]] = []
        self._latest_task_run: dict[str, Any] | None = None
        self._task_latest_baton: dict[str, Any] | None = None
        self._task_routing: dict[str, Any] | None = None
        self._task_digest: dict[str, Any] | None = None
        self._task_preferences: dict[str, str] = {}
        self._last_scan: dict[str, Any] | None = None
        self._last_view: str | None = None
        self._available_models: list[str] = list(PROVIDER_MODEL_CATALOG["local_echo"])
        self._autonomy_enabled = False
        self._last_autonomy_processed = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(classes="pane"):
                yield Static("Left", id="left")
            with Vertical(classes="pane"):
                yield Static("Center", id="center")
            with Vertical(classes="pane"):
                yield Static("Right", id="right")
        yield Footer()

    def on_mount(self) -> None:
        self._load_available_models()
        self.set_interval(3.0, self.action_refresh)
        self.action_refresh()

    def _load_available_models(self) -> None:
        merged: list[str] = []
        for models in PROVIDER_MODEL_CATALOG.values():
            for model in models:
                if model not in merged:
                    merged.append(model)

        credentials = self._openai_store.load()
        if credentials is None:
            self._available_models = merged
            return
        try:
            openai_models = self._openai_client.list_text_models(credentials.api_key)
        except OpenAIAuthError:
            self._available_models = merged
            return

        for model in openai_models:
            if model not in merged:
                merged.append(model)
        self._available_models = merged

    def action_refresh(self) -> None:
        try:
            self._summary = self._client.dashboard_summary()
            self._workspaces = self._safe_request(self._client.list_workspaces, [])
            self._tasks = self._safe_request(self._client.list_tasks, [])
            self._runs = self._safe_request(self._client.list_agent_runs, [])
            if self._autonomy_enabled:
                autonomy = self._safe_request(
                    lambda: self._client.autonomy_scan_once(limit=50), None
                )
                if isinstance(autonomy, dict):
                    processed = int(autonomy.get("processed", 0) or 0)
                    self._last_autonomy_processed = processed
            if self.current_view == "diagnostics":
                self._services = self._safe_request(self._client.services_health, {})
                self._diag_config = self._safe_request(self._client.diagnostics_config, {})
                self._diag_routes = self._safe_request(self._client.diagnostics_routes, {})

            self._sync_workspace_selection()
            self._sync_task_selection()
            self._sync_run_selection()
            self._refresh_task_context()

            if not self._update_panes():
                return
            self.sub_title = (
                f"API {self._config.api_url} | "
                f"{self._summary.get('health', 'unknown')} | "
                f"view={self.current_view}"
            )
        except SyncoreApiError as error:
            if not self._update_panes(
                left="Offline",
                center="Could not load data",
                right=str(error),
            ):
                return
            self.sub_title = f"API offline: {self._config.api_url}"

    def _safe_request(self, fn, default):
        try:
            return fn()
        except SyncoreApiError:
            return default

    def _update_panes(
        self,
        *,
        left: str | None = None,
        center: str | None = None,
        right: str | None = None,
    ) -> bool:
        try:
            left_widget = self.query_one("#left", Static)
            center_widget = self.query_one("#center", Static)
            right_widget = self.query_one("#right", Static)
        except NoMatches:
            return False

        left_widget.update(left if left is not None else self._render_left_pane())
        center_widget.update(center if center is not None else self._render_center_pane())
        right_widget.update(right if right is not None else self._render_right_pane())
        return True

    def _sync_workspace_selection(self) -> None:
        if not self._workspaces:
            self._selected_workspace_index = 0
            self._selected_workspace_id = None
            self._selected_workspace_name = None
            return

        if self._selected_workspace_id:
            for index, workspace in enumerate(self._workspaces):
                if str(workspace.get("id")) == self._selected_workspace_id:
                    self._selected_workspace_index = index
                    self._selected_workspace_name = str(workspace.get("name", "unknown"))
                    return

        self._selected_workspace_index = min(
            self._selected_workspace_index, len(self._workspaces) - 1
        )
        selected = self._workspaces[self._selected_workspace_index]
        self._selected_workspace_id = str(selected.get("id"))
        self._selected_workspace_name = str(selected.get("name", "unknown"))

    def _sync_task_selection(self) -> None:
        if not self._tasks:
            self._selected_task_index = 0
            self._selected_task_id = None
            self._selected_task_title = None
            return

        if self._selected_task_id:
            for index, task in enumerate(self._tasks):
                if str(task.get("id")) == self._selected_task_id:
                    self._selected_task_index = index
                    self._selected_task_title = str(task.get("title", "unknown"))
                    return

        self._selected_task_index = min(self._selected_task_index, len(self._tasks) - 1)
        selected = self._tasks[self._selected_task_index]
        self._selected_task_id = str(selected.get("id"))
        self._selected_task_title = str(selected.get("title", "unknown"))

    def _sync_run_selection(self) -> None:
        if not self._runs:
            self._selected_run_index = 0
            return
        self._selected_run_index = min(self._selected_run_index, len(self._runs) - 1)

    def _selected_workspace(self) -> dict[str, Any] | None:
        if not self._workspaces:
            return None
        return self._workspaces[self._selected_workspace_index]

    def _selected_task(self) -> dict[str, Any] | None:
        if not self._tasks:
            return None
        return self._tasks[self._selected_task_index]

    def _selected_run(self) -> dict[str, Any] | None:
        if not self._runs:
            return None
        return self._runs[self._selected_run_index]

    def _refresh_task_context(self) -> None:
        task = self._selected_task()
        if task is None:
            self._task_events = []
            self._task_batons = []
            self._task_runs = []
            self._latest_task_run = None
            self._task_latest_baton = None
            self._task_routing = None
            self._task_digest = None
            self._task_preferences = {}
            return

        task_id = str(task.get("id"))
        self._task_events = self._safe_request(
            lambda: self._client.list_task_events(task_id), []
        )
        self._task_batons = self._safe_request(
            lambda: self._client.list_task_batons(task_id), []
        )
        self._task_runs = [run for run in self._runs if str(run.get("task_id")) == task_id]
        self._latest_task_run = self._latest_by_timestamp(self._task_runs)
        self._task_latest_baton = self._safe_request(
            lambda: self._client.latest_task_baton(task_id), None
        )
        self._task_routing = self._safe_request(
            lambda: self._client.get_task_routing(task_id), None
        )
        self._task_digest = self._safe_request(
            lambda: self._client.get_task_digest(task_id), None
        )
        self._task_preferences = self._extract_task_preferences(self._task_events)

    def _latest_by_timestamp(
        self, records: list[dict[str, Any]], field: str = "updated_at"
    ) -> dict[str, Any] | None:
        if not records:
            return None
        return max(records, key=lambda record: str(record.get(field, "")))

    def _extract_task_preferences(self, events: list[dict[str, Any]]) -> dict[str, str]:
        for event in reversed(events):
            if str(event.get("event_type")) != "task.preferences":
                continue
            data = event.get("event_data")
            if not isinstance(data, dict):
                continue
            preferred_model = str(data.get("preferred_model") or "").strip()
            preferred_provider = str(data.get("preferred_provider") or "").strip()
            preferred_agent = str(data.get("preferred_agent_role") or "").strip()
            execution_prompt = str(data.get("execution_prompt") or "").strip()
            requires_approval = str(data.get("requires_approval") or "").strip()
            return {
                "preferred_provider": preferred_provider,
                "preferred_model": preferred_model,
                "preferred_agent_role": preferred_agent,
                "execution_prompt": execution_prompt,
                "requires_approval": requires_approval,
            }
        return {}

    def _render_left_pane(self) -> str:
        if self.current_view == "dashboard":
            return self._render_dashboard_left()
        if self.current_view == "workspaces":
            return self._render_workspaces_left()
        if self.current_view == "tasks":
            return self._render_tasks_left()
        if self.current_view == "task_detail":
            return self._render_task_detail_left()
        if self.current_view == "runs":
            return self._render_runs_left()
        if self.current_view == "diagnostics":
            return self._render_diagnostics_left()
        return "Unknown view"

    def _render_center_pane(self) -> str:
        if self.current_view == "dashboard":
            return self._render_dashboard_center()
        if self.current_view == "workspaces":
            return self._render_workspaces_center()
        if self.current_view == "tasks":
            return self._render_tasks_center()
        if self.current_view == "task_detail":
            return self._render_task_detail_center()
        if self.current_view == "runs":
            return self._render_runs_center()
        if self.current_view == "diagnostics":
            return self._render_diagnostics_center()
        return ""

    def _render_right_pane(self) -> str:
        actions_hint = "Actions: n s g o p e"
        if self.current_view == "task_detail":
            actions_hint = "Actions: s g o p e y u"
        elif self.current_view == "runs":
            actions_hint = "Actions: g o p e"
        elif self.current_view == "diagnostics":
            actions_hint = "Actions: m i"

        lines = [
            f"API: {self._config.api_url}",
            f"Runtime: {self._summary.get('runtime_mode')}",
            f"Health: {self._summary.get('health')}",
            f"Workspace: {self._selected_workspace_name or 'none'}",
            f"Task: {self._selected_task_title or 'none'}",
            "",
            "Views: d/w/t/a/x | detail: v/b",
            "Nav: j/k | Refresh: r | Quit: q",
            actions_hint,
            "OpenAI: i=signin m=models",
            (
                f"Autonomy: {'ON' if self._autonomy_enabled else 'OFF'} "
                "(z=toggle)"
            ),
        ]
        if self._autonomy_enabled:
            lines.append(f"Autonomy last scan processed: {self._last_autonomy_processed}")
        if self._task_preferences:
            lines.extend(
                [
                    "",
                    "Task prefs:",
                    f"provider={self._task_preferences.get('preferred_provider', '-')}",
                    f"model={self._task_preferences.get('preferred_model', '-')}",
                    f"agent={self._task_preferences.get('preferred_agent_role', '-')}",
                    f"requires_approval={self._task_preferences.get('requires_approval', '-')}",
                ]
            )
        return "\n".join(lines)

    def _render_dashboard_left(self) -> str:
        return "\n".join(
            [
                "Dashboard",
                f"Workspaces: {self._summary.get('workspace_count', len(self._workspaces))}",
                f"Open tasks: {self._summary.get('open_task_count', 0)}",
                f"Active runs: {self._summary.get('active_run_count', 0)}",
                "",
                "Recent tasks:",
                *[
                    f"- {task.get('title')} [{task.get('status')}]"
                    for task in self._tasks[:6]
                ],
            ]
        )

    def _render_dashboard_center(self) -> str:
        events = self._summary.get("recent_events", []) or []
        batons = self._summary.get("recent_batons", []) or []
        lines = ["Recent events:"]
        lines.extend(
            [
                f"- {event.get('event_type')} task={event.get('task_id')}"
                for event in events[:8]
            ]
        )
        lines.append("")
        lines.append("Recent batons:")
        lines.extend(
            [
                f"- {baton.get('summary', baton.get('id'))} task={baton.get('task_id')}"
                for baton in batons[:8]
            ]
        )
        return "\n".join(lines)

    def _render_workspaces_left(self) -> str:
        lines = ["Workspaces (j/k to select)"]
        for index, workspace in enumerate(self._workspaces):
            marker = "*" if index == self._selected_workspace_index else "-"
            lines.append(f"{marker} {workspace.get('name')} ({workspace.get('id')})")
        return "\n".join(lines)

    def _render_workspaces_center(self) -> str:
        workspace = self._selected_workspace()
        if workspace is None:
            return "No workspace registered."
        lines = [
            "Selected workspace",
            f"id: {workspace.get('id')}",
            f"name: {workspace.get('name')}",
            f"path: {workspace.get('root_path')}",
            f"branch: {workspace.get('branch') or '-'}",
            f"runtime: {workspace.get('runtime_mode')}",
            "",
            "Press s to scan selected workspace.",
        ]
        if self._last_scan:
            scan = self._last_scan.get("scan", {})
            lines.extend(
                [
                    "",
                    f"languages: {', '.join(scan.get('languages', [])) or '-'}",
                    f"frameworks: {', '.join(scan.get('frameworks', [])) or '-'}",
                    f"package managers: {', '.join(scan.get('package_managers', [])) or '-'}",
                    f"docs: {', '.join(scan.get('docs', [])) or '-'}",
                ]
            )
        return "\n".join(lines)

    def _render_tasks_left(self) -> str:
        lines = ["Tasks (j/k to select, v for detail)"]
        for index, task in enumerate(self._tasks):
            marker = "*" if index == self._selected_task_index else "-"
            lines.append(
                f"{marker} {task.get('title')} [{task.get('status')}] "
                f"{task.get('complexity')}"
            )
        return "\n".join(lines)

    def _render_tasks_center(self) -> str:
        task = self._selected_task()
        if task is None:
            return "No tasks."
        return "\n".join(
            [
                "Selected task",
                f"id: {task.get('id')}",
                f"title: {task.get('title')}",
                f"status: {task.get('status')}",
                f"type: {task.get('task_type')}",
                f"complexity: {task.get('complexity')}",
                f"updated: {task.get('updated_at')}",
                "",
                "n=create task p=start run e=execute",
            ]
        )

    def _render_task_detail_left(self) -> str:
        task = self._selected_task()
        if task is None:
            return "No selected task."
        lines = [
            "Task Detail",
            f"id: {task.get('id')}",
            f"title: {task.get('title')}",
            f"type: {task.get('task_type')}",
            f"complexity: {task.get('complexity')}",
            "",
            "Recent events:",
        ]
        for event in self._task_events[-8:]:
            lines.append(f"- {event.get('event_type')}")
        return "\n".join(lines)

    def _render_task_detail_center(self) -> str:
        lines = ["Baton / Routing / Digest"]
        if self._latest_task_run:
            lines.extend(
                [
                    f"latest run: {self._latest_task_run.get('status')}",
                    f"run role: {self._latest_task_run.get('role')}",
                ]
            )
            output_summary = str(self._latest_task_run.get("output_summary") or "").strip()
            error_message = str(self._latest_task_run.get("error_message") or "").strip()
            if output_summary:
                lines.append(f"result: {output_summary}")
            elif error_message:
                lines.append(f"error: {error_message}")
            else:
                lines.append("result: (no output yet)")
        else:
            lines.append("latest run: none")
        if self._task_latest_baton:
            lines.append(
                f"latest baton: {self._task_latest_baton.get('summary', self._task_latest_baton.get('id'))}"
            )
        else:
            lines.append("latest baton: none")
        if self._task_routing:
            lines.append(
                f"routing: {self._task_routing.get('worker_role')} / "
                f"{self._task_routing.get('model_tier')}"
            )
        else:
            lines.append("routing: none")
        if self._task_digest:
            lines.append(
                f"digest: {self._task_digest.get('headline') or self._task_digest.get('summary', '')[:90]}"
            )
        else:
            lines.append("digest: none")
        lines.append("")
        lines.append("Hotkeys: g=digest o=route p=run e=execute b=back")
        return "\n".join(lines)

    def _render_runs_left(self) -> str:
        lines = ["Agent Runs (j/k to select, v for task detail)"]
        for index, run in enumerate(self._runs):
            marker = "*" if index == self._selected_run_index else "-"
            lines.append(
                f"{marker} {run.get('id')} role={run.get('role')} "
                f"status={run.get('status')} task={run.get('task_id')}"
            )
        return "\n".join(lines)

    def _render_runs_center(self) -> str:
        run = self._selected_run()
        if run is None:
            return "No runs."
        return "\n".join(
            [
                "Selected run",
                f"id: {run.get('id')}",
                f"task_id: {run.get('task_id')}",
                f"role: {run.get('role')}",
                f"status: {run.get('status')}",
                f"updated: {run.get('updated_at')}",
            ]
        )

    def _render_diagnostics_left(self) -> str:
        dependencies = self._services.get("dependencies", []) if self._services else []
        lines = [
            "Diagnostics",
            f"health: {self._summary.get('health', 'unknown')}",
            "",
            "service dependencies:",
        ]
        for dependency in dependencies:
            lines.append(
                f"- {dependency.get('name')}: {dependency.get('status')} "
                f"({dependency.get('detail', '')})"
            )
        return "\n".join(lines)

    def _render_diagnostics_center(self) -> str:
        routes = self._diag_routes.get("routes", []) if self._diag_routes else []
        return "\n".join(
            [
                "Config",
                f"runtime_mode: {self._diag_config.get('runtime_mode', '-')}",
                f"db_backend: {self._diag_config.get('db_backend', '-')}",
                f"redis_required: {self._diag_config.get('redis_required', '-')}",
                "",
                f"routes_count: {len(routes)}",
                f"sample_routes: {', '.join(routes[:6]) if routes else '-'}",
            ]
        )

    def _switch(self, view: str) -> None:
        if self.current_view != view:
            self._last_view = self.current_view
        self.current_view = view
        self.action_refresh()

    def action_show_dashboard(self) -> None:
        self._switch("dashboard")

    def action_show_workspaces(self) -> None:
        self._switch("workspaces")

    def action_show_tasks(self) -> None:
        self._switch("tasks")

    def action_show_runs(self) -> None:
        self._switch("runs")

    def action_show_diagnostics(self) -> None:
        self._switch("diagnostics")

    def action_open_detail(self) -> None:
        if self.current_view == "tasks":
            self._switch("task_detail")
            return
        if self.current_view == "runs":
            run = self._selected_run()
            if run is None:
                return
            task_id = str(run.get("task_id"))
            for idx, task in enumerate(self._tasks):
                if str(task.get("id")) == task_id:
                    self._selected_task_index = idx
                    self._selected_task_id = task_id
                    self._selected_task_title = str(task.get("title", "unknown"))
                    break
            self._switch("task_detail")

    def action_back_view(self) -> None:
        if self._last_view:
            current = self._last_view
            self._last_view = self.current_view
            self.current_view = current
            self.action_refresh()
            return
        if self.current_view == "task_detail":
            self._switch("tasks")

    def action_next_item(self) -> None:
        if self.current_view == "workspaces" and self._workspaces:
            self._selected_workspace_index = (self._selected_workspace_index + 1) % len(
                self._workspaces
            )
            workspace = self._workspaces[self._selected_workspace_index]
            self._selected_workspace_id = str(workspace.get("id"))
            self._selected_workspace_name = str(workspace.get("name", "unknown"))
        elif self.current_view in {"tasks", "task_detail"} and self._tasks:
            self._selected_task_index = (self._selected_task_index + 1) % len(self._tasks)
            task = self._tasks[self._selected_task_index]
            self._selected_task_id = str(task.get("id"))
            self._selected_task_title = str(task.get("title", "unknown"))
        elif self.current_view == "runs" and self._runs:
            self._selected_run_index = (self._selected_run_index + 1) % len(self._runs)
        self.action_refresh()

    def action_prev_item(self) -> None:
        if self.current_view == "workspaces" and self._workspaces:
            self._selected_workspace_index = (self._selected_workspace_index - 1) % len(
                self._workspaces
            )
            workspace = self._workspaces[self._selected_workspace_index]
            self._selected_workspace_id = str(workspace.get("id"))
            self._selected_workspace_name = str(workspace.get("name", "unknown"))
        elif self.current_view in {"tasks", "task_detail"} and self._tasks:
            self._selected_task_index = (self._selected_task_index - 1) % len(self._tasks)
            task = self._tasks[self._selected_task_index]
            self._selected_task_id = str(task.get("id"))
            self._selected_task_title = str(task.get("title", "unknown"))
        elif self.current_view == "runs" and self._runs:
            self._selected_run_index = (self._selected_run_index - 1) % len(self._runs)
        self.action_refresh()

    def action_new_task(self) -> None:
        if self.current_view == "task_detail":
            self.notify("Task detail view: press b to return before creating a new task.")
            return
        self.push_screen(
            NewTaskScreen(
                workspace_name=self._selected_workspace_name,
                available_models=self._available_models,
            ),
            callback=self._handle_new_task_payload,
        )

    def _handle_new_task_payload(self, payload: dict[str, str] | None) -> None:
        if payload is None:
            return

        title = payload["title"]
        description = payload["description"].strip()
        if description:
            title = f"{title} - {description}"

        create_payload = {
            "title": title,
            "task_type": payload["task_type"],
            "complexity": payload["complexity"],
            "workspace_id": self._selected_workspace_id,
        }
        try:
            created = self._client.create_task(create_payload)
            task_id = str(created.get("id"))
            self._client.create_project_event(
                {
                    "task_id": task_id,
                    "event_type": "task.preferences",
                    "event_data": {
                        "preferred_provider": payload.get("preferred_provider", DEFAULT_PROVIDER),
                        "preferred_model": payload.get("preferred_model", DEFAULT_MODEL),
                        "preferred_agent_role": payload.get("preferred_agent_role", "coder"),
                        "execution_prompt": payload.get("execution_prompt", ""),
                        "requires_approval": payload.get("requires_approval", "false"),
                    },
                }
            )
        except SyncoreApiError as error:
            self.notify(str(error), severity="error")
            return

        self._selected_task_id = str(created.get("id"))
        self._selected_task_title = str(created.get("title", "unknown"))
        self.notify(f"Created task {self._selected_task_id}")
        self.current_view = "task_detail"
        self.action_refresh()

    def action_refresh_models(self) -> None:
        credentials = self._openai_store.load()
        if credentials is None:
            self._load_available_models()
            self.notify("Loaded local model catalog. Press i to connect OpenAI for account models.")
            self.action_refresh()
            return
        try:
            self._openai_client.list_text_models(credentials.api_key)
        except OpenAIAuthError as error:
            self.notify(str(error), severity="error")
            return
        self._load_available_models()
        count = len(self._available_models)
        self.notify(f"Loaded {count} OpenAI models.")
        self.action_refresh()

    def action_openai_signin(self) -> None:
        self.push_screen(OpenAISignInScreen(), callback=self._handle_openai_signin_payload)

    def _handle_openai_signin_payload(self, payload: dict[str, str] | None) -> None:
        if payload is None:
            return
        api_key = payload.get("api_key", "").strip()
        if not api_key:
            self.notify("API key cannot be empty.", severity="error")
            return

        try:
            models = self._openai_client.list_text_models(api_key)
        except OpenAIAuthError as error:
            self.notify(str(error), severity="error")
            return

        self._openai_store.save(OpenAICredentials(api_key=api_key))
        self._load_available_models()
        self.notify(f"Connected to OpenAI. {len(models)} models available.")
        self.action_refresh()

    def action_scan_workspace(self) -> None:
        workspace = self._selected_workspace()
        if workspace is None:
            self.notify("No workspace available to scan.", severity="warning")
            return
        workspace_id = str(workspace.get("id"))
        try:
            self._last_scan = self._client.scan_workspace(workspace_id)
        except SyncoreApiError as error:
            self.notify(str(error), severity="error")
            return

        scan = self._last_scan.get("scan", {})
        languages = scan.get("languages", [])
        label = ", ".join(languages) if languages else "none"
        self.notify(f"Scanned workspace {workspace.get('name')}: {label}")
        self.action_refresh()

    def action_generate_digest(self) -> None:
        task = self._selected_task()
        if task is None:
            self.notify("No task available for digest.", severity="warning")
            return
        task_id = str(task.get("id"))
        try:
            self._task_digest = self._client.generate_digest({"task_id": task_id, "limit": 50})
        except SyncoreApiError as error:
            self.notify(str(error), severity="error")
            return

        self.notify(f"Generated digest for task {task_id}")
        self.action_refresh()

    def action_route_next(self) -> None:
        task = self._selected_task()
        if task is None:
            self.notify("No task available for routing.", severity="warning")
            return
        task_id = str(task.get("id"))
        try:
            task_payload = self._client.get_task(task_id).get("task", {})
            self._task_routing = self._client.route_next_action(
                {
                    "task_type": task_payload.get("task_type", "analysis"),
                    "complexity": task_payload.get("complexity", "medium"),
                    "requires_memory": True,
                }
            )
        except SyncoreApiError as error:
            self.notify(str(error), severity="error")
            return

        self.notify(
            "Routed task "
            f"{task_id}: {self._task_routing.get('worker_role')}/"
            f"{self._task_routing.get('model_tier')}"
        )
        self.action_refresh()

    def action_start_agent_run(self) -> None:
        task = self._selected_task()
        if task is None:
            self.notify("No selected task.", severity="warning")
            return
        task_id = str(task.get("id"))
        role = self._task_preferences.get("preferred_agent_role", "coder")
        if role not in AGENT_ROLES:
            role = "coder"
        try:
            self._client.create_agent_run(
                {"task_id": task_id, "role": role, "status": "queued"}
            )
        except SyncoreApiError as error:
            self.notify(str(error), severity="error")
            return
        self.notify(f"Queued agent run for task {task_id} ({role})")
        self.current_view = "runs"
        self.action_refresh()

    def action_execute_task(self) -> None:
        task = self._selected_task()
        if task is None:
            self.notify("No selected task.", severity="warning")
            return

        task_id = str(task.get("id"))
        preferred_role = self._task_preferences.get("preferred_agent_role", "coder")
        if preferred_role not in AGENT_ROLES:
            preferred_role = "coder"
        preferred_model = self._task_preferences.get("preferred_model", DEFAULT_MODEL)
        preferred_provider = self._task_preferences.get("preferred_provider", DEFAULT_PROVIDER)
        if preferred_provider not in MODEL_PROVIDERS:
            preferred_provider = DEFAULT_PROVIDER
        prompt = self._task_preferences.get("execution_prompt") or str(task.get("title", ""))
        payload = {
            "task_id": task_id,
            "prompt": prompt,
            "target_agent": preferred_role,
            "target_model": preferred_model or DEFAULT_MODEL,
            "provider": preferred_provider if preferred_provider != "other" else None,
            "agent_role": preferred_role,
            "token_budget": 8000,
            "max_output_tokens": 1200,
            "temperature": 0.2,
        }

        try:
            response = self._client.execute_run(payload)
        except SyncoreApiError as error:
            self.notify(str(error), severity="error")
            return

        self.notify(
            f"Executed task {task_id} on {response.get('target_model')} "
            f"status={response.get('status')}"
        )
        self.current_view = "runs"
        self.action_refresh()

    def action_toggle_autonomy(self) -> None:
        self._autonomy_enabled = not self._autonomy_enabled
        self._last_autonomy_processed = 0
        if self._autonomy_enabled:
            self.notify("Autonomy enabled in TUI (scan loop via /autonomy/scan-once).")
        else:
            self.notify("Autonomy disabled in TUI.")
        self.action_refresh()

    def action_approve_task(self) -> None:
        task = self._selected_task()
        if task is None:
            self.notify("No selected task.", severity="warning")
            return
        task_id = str(task.get("id"))
        try:
            result = self._client.autonomy_approve_task(task_id, reason="Approved from TUI")
        except SyncoreApiError as error:
            self.notify(str(error), severity="error")
            return
        self.notify(f"Autonomy approval: {task_id} -> {result.get('status')}")
        self.action_refresh()

    def action_reject_task(self) -> None:
        task = self._selected_task()
        if task is None:
            self.notify("No selected task.", severity="warning")
            return
        task_id = str(task.get("id"))
        try:
            result = self._client.autonomy_reject_task(task_id, reason="Rejected from TUI")
        except SyncoreApiError as error:
            self.notify(str(error), severity="error")
            return
        self.notify(f"Autonomy rejection: {task_id} -> {result.get('status')}")
        self.action_refresh()


class OpenAISignInScreen(ModalScreen[dict[str, str] | None]):
    CSS = """
    #openai-login-modal {
      width: 76;
      height: auto;
      border: round $accent;
      padding: 1 2;
      background: $surface;
      align-horizontal: center;
      align-vertical: middle;
    }
    #openai-login-actions {
      height: auto;
      layout: horizontal;
      margin-top: 1;
    }
    #openai-login-actions Button {
      margin-right: 1;
    }
    #openai-login-error {
      color: $error;
      height: auto;
      margin-top: 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="openai-login-modal"):
            yield Label("Connect OpenAI")
            yield Label(
                "Paste API key (stored locally at ~/.syncore/openai_credentials.json)"
            )
            yield Input(password=True, placeholder="sk-...", id="openai-api-key")
            yield Static("", id="openai-login-error")
            with Horizontal(id="openai-login-actions"):
                yield Button("Connect", id="openai-login-connect", variant="success")
                yield Button("Cancel", id="openai-login-cancel")

    def on_mount(self) -> None:
        self.query_one("#openai-api-key", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "openai-api-key":
            self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "openai-login-cancel":
            self.dismiss(None)
            return
        if event.button.id == "openai-login-connect":
            self._submit()

    def _submit(self) -> None:
        api_key = self.query_one("#openai-api-key", Input).value.strip()
        if not api_key:
            self.query_one("#openai-login-error", Static).update("API key is required.")
            return
        self.dismiss({"api_key": api_key})
