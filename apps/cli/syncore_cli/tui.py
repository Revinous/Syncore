from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static

from .client import SyncoreApiClient, SyncoreApiError
from .config import CliConfig
from .openai_auth import (
    OpenAIAuthError,
    OpenAIAuthStore,
    OpenAIModelClient,
    OpenAICredentials,
)
from . import tui_render
from .tui_screens import (
    AGENT_ROLES,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    MODEL_PROVIDERS,
    PROVIDER_MODEL_CATALOG,
    NewTaskScreen,
    OpenAISignInScreen,
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
        ("f", "show_notifications", "Notifications"),
        ("c", "show_metrics", "Metrics"),
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
        ("h", "ack_notification", "Ack Notification"),
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
        self._context_efficiency: dict[str, Any] = {}
        self._notifications: list[dict[str, Any]] = []
        self._selected_notification_index = 0
        self._task_events: list[dict[str, Any]] = []
        self._task_batons: list[dict[str, Any]] = []
        self._task_runs: list[dict[str, Any]] = []
        self._latest_task_run: dict[str, Any] | None = None
        self._latest_run_result: dict[str, Any] | None = None
        self._task_latest_baton: dict[str, Any] | None = None
        self._task_routing: dict[str, Any] | None = None
        self._task_digest: dict[str, Any] | None = None
        self._task_execution_report: dict[str, Any] | None = None
        self._task_preferences: dict[str, str] = {}
        self._latest_model_switch: dict[str, Any] | None = None
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
            list_notifications = getattr(self._client, "list_notifications", None)
            if callable(list_notifications):
                notifications_payload = self._safe_request(
                    lambda: list_notifications(acknowledged=False, limit=100),
                    {"items": []},
                )
            else:
                notifications_payload = {"items": []}
            self._notifications = (
                notifications_payload.get("items", [])
                if isinstance(notifications_payload, dict)
                else []
            )
            if self._autonomy_enabled:
                autonomy = self._safe_request(
                    lambda: self._client.autonomy_scan_once(limit=50), None
                )
                if isinstance(autonomy, dict):
                    processed = int(autonomy.get("processed", 0) or 0)
                    self._last_autonomy_processed = processed
            if self.current_view == "diagnostics":
                self._services = self._safe_request(self._client.services_health, {})
                self._diag_config = self._safe_request(
                    self._client.diagnostics_config, {}
                )
                self._diag_routes = self._safe_request(
                    self._client.diagnostics_routes, {}
                )
            if self.current_view in {"dashboard", "metrics"}:
                metrics_fn = getattr(self._client, "context_efficiency_metrics", None)
                if callable(metrics_fn):
                    self._context_efficiency = self._safe_request(metrics_fn, {})
                else:
                    self._context_efficiency = {}

            self._sync_workspace_selection()
            self._sync_task_selection()
            self._sync_run_selection()
            self._sync_notification_selection()
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
        center_widget.update(
            center if center is not None else self._render_center_pane()
        )
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
                    self._selected_workspace_name = str(
                        workspace.get("name", "unknown")
                    )
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

    def _sync_notification_selection(self) -> None:
        if not self._notifications:
            self._selected_notification_index = 0
            return
        self._selected_notification_index = min(
            self._selected_notification_index, len(self._notifications) - 1
        )

    def _selected_notification(self) -> dict[str, Any] | None:
        if not self._notifications:
            return None
        return self._notifications[self._selected_notification_index]

    def _refresh_task_context(self) -> None:
        task = self._selected_task()
        if task is None:
            self._task_events = []
            self._task_batons = []
            self._task_runs = []
            self._latest_task_run = None
            self._latest_run_result = None
            self._task_latest_baton = None
            self._task_routing = None
            self._task_digest = None
            self._task_execution_report = None
            self._task_preferences = {}
            self._latest_model_switch = None
            return

        task_id = str(task.get("id"))
        self._task_events = self._safe_request(
            lambda: self._client.list_task_events(task_id), []
        )
        self._task_batons = self._safe_request(
            lambda: self._client.list_task_batons(task_id), []
        )
        self._task_runs = [
            run for run in self._runs if str(run.get("task_id")) == task_id
        ]
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
        self._task_execution_report = self._safe_request(
            lambda: self._client.get_task_execution_report(task_id), None
        )
        if self._latest_task_run is not None and self._latest_task_run.get("id"):
            self._latest_run_result = self._safe_request(
                lambda: self._client.get_agent_run_result(
                    str(self._latest_task_run.get("id"))
                ),
                None,
            )
        else:
            self._latest_run_result = None
        self._task_preferences = self._extract_task_preferences(self._task_events)
        self._latest_model_switch = self._extract_latest_model_switch(self._task_events)

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
            sdlc_enforce = str(data.get("sdlc_enforce") or "").strip()
            return {
                "preferred_provider": preferred_provider,
                "preferred_model": preferred_model,
                "preferred_agent_role": preferred_agent,
                "execution_prompt": execution_prompt,
                "requires_approval": requires_approval,
                "sdlc_enforce": sdlc_enforce,
            }
        return {}

    def _extract_latest_model_switch(
        self, events: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        for event in reversed(events):
            if str(event.get("event_type")) != "model.switch.completed":
                continue
            data = event.get("event_data")
            if isinstance(data, dict):
                return data
        return None

    def _render_left_pane(self) -> str:
        return tui_render.render_left_pane(self)

    def _render_center_pane(self) -> str:
        return tui_render.render_center_pane(self)

    def _render_right_pane(self) -> str:
        return tui_render.render_right_pane(self)

    def _render_task_detail_center(self) -> str:
        return tui_render.render_task_detail_center(self)

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

    def action_show_notifications(self) -> None:
        self._switch("notifications")

    def action_show_metrics(self) -> None:
        self._switch("metrics")

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
            self._selected_task_index = (self._selected_task_index + 1) % len(
                self._tasks
            )
            task = self._tasks[self._selected_task_index]
            self._selected_task_id = str(task.get("id"))
            self._selected_task_title = str(task.get("title", "unknown"))
        elif self.current_view == "runs" and self._runs:
            self._selected_run_index = (self._selected_run_index + 1) % len(self._runs)
        elif self.current_view == "notifications" and self._notifications:
            self._selected_notification_index = (
                self._selected_notification_index + 1
            ) % len(self._notifications)
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
            self._selected_task_index = (self._selected_task_index - 1) % len(
                self._tasks
            )
            task = self._tasks[self._selected_task_index]
            self._selected_task_id = str(task.get("id"))
            self._selected_task_title = str(task.get("title", "unknown"))
        elif self.current_view == "runs" and self._runs:
            self._selected_run_index = (self._selected_run_index - 1) % len(self._runs)
        elif self.current_view == "notifications" and self._notifications:
            self._selected_notification_index = (
                self._selected_notification_index - 1
            ) % len(self._notifications)
        self.action_refresh()

    def action_new_task(self) -> None:
        if self.current_view == "task_detail":
            self.notify(
                "Task detail view: press b to return before creating a new task."
            )
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
                        "preferred_provider": payload.get(
                            "preferred_provider", DEFAULT_PROVIDER
                        ),
                        "preferred_model": payload.get(
                            "preferred_model", DEFAULT_MODEL
                        ),
                        "preferred_agent_role": payload.get(
                            "preferred_agent_role", "coder"
                        ),
                        "execution_prompt": payload.get("execution_prompt", ""),
                        "requires_approval": payload.get("requires_approval", "false"),
                        "sdlc_enforce": payload.get("sdlc_enforce", "false"),
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
            self.notify(
                "Loaded local model catalog. Press i to connect OpenAI for account models."
            )
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
        self.push_screen(
            OpenAISignInScreen(), callback=self._handle_openai_signin_payload
        )

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
            self._task_digest = self._client.generate_digest(
                {"task_id": task_id, "limit": 50}
            )
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
        preferred_provider = self._task_preferences.get(
            "preferred_provider", DEFAULT_PROVIDER
        )
        if preferred_provider not in MODEL_PROVIDERS:
            preferred_provider = DEFAULT_PROVIDER
        prompt = self._task_preferences.get("execution_prompt") or str(
            task.get("title", "")
        )
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
            result = self._client.autonomy_approve_task(
                task_id, reason="Approved from TUI"
            )
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
            result = self._client.autonomy_reject_task(
                task_id, reason="Rejected from TUI"
            )
        except SyncoreApiError as error:
            self.notify(str(error), severity="error")
            return
        self.notify(f"Autonomy rejection: {task_id} -> {result.get('status')}")
        self.action_refresh()

    def action_ack_notification(self) -> None:
        item = self._selected_notification()
        if item is None:
            self.notify("No notification selected.", severity="warning")
            return
        notification_id = str(item.get("id"))
        try:
            self._client.acknowledge_notification(notification_id)
        except SyncoreApiError as error:
            self.notify(str(error), severity="error")
            return
        self.notify(f"Acknowledged notification {notification_id}")
        self.action_refresh()
