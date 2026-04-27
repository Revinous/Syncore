from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from .client import SyncoreApiClient, SyncoreApiError
from .config import CliConfig


TASK_TYPES = (
    "analysis",
    "implementation",
    "integration",
    "review",
    "memory_retrieval",
    "memory_update",
)
COMPLEXITY_LEVELS = ("low", "medium", "high")


class NewTaskScreen(ModalScreen[dict[str, str] | None]):
    CSS = """
    #new-task-modal {
      width: 72;
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

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, workspace_name: str | None = None) -> None:
        super().__init__()
        self._workspace_name = workspace_name

    def compose(self) -> ComposeResult:
        with Vertical(id="new-task-modal"):
            yield Label("Create Task")
            yield Label(
                f"Workspace: {self._workspace_name or 'none'} "
                "(included as title prefix)"
            )
            yield Input(placeholder="Task title", id="task-title")
            yield Input(
                placeholder="Description (optional)",
                id="task-description",
            )
            yield Input(
                value="implementation",
                placeholder="task_type",
                id="task-type",
            )
            yield Input(
                value="medium",
                placeholder="complexity",
                id="task-complexity",
            )
            yield Static("", id="new-task-error")
            with Horizontal(id="new-task-actions"):
                yield Button("Create", id="new-task-create", variant="success")
                yield Button("Cancel", id="new-task-cancel")

    def on_mount(self) -> None:
        self.query_one("#task-title", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "task-complexity":
            self._submit()
            return
        next_field = {
            "task-title": "task-description",
            "task-description": "task-type",
            "task-type": "task-complexity",
        }.get(event.input.id or "")
        if next_field:
            self.query_one(f"#{next_field}", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-task-cancel":
            self.dismiss(None)
            return
        if event.button.id == "new-task-create":
            self._submit()

    def _submit(self) -> None:
        title = self.query_one("#task-title", Input).value.strip()
        description = self.query_one("#task-description", Input).value.strip()
        task_type = self.query_one("#task-type", Input).value.strip().lower()
        complexity = self.query_one("#task-complexity", Input).value.strip().lower()

        if not title:
            self.query_one("#new-task-error", Static).update("Task title is required.")
            return
        if task_type not in TASK_TYPES:
            task_type = "implementation"
        if complexity not in COMPLEXITY_LEVELS:
            complexity = "medium"

        self.dismiss(
            {
                "title": title,
                "description": description,
                "task_type": task_type,
                "complexity": complexity,
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
        ("n", "new_task", "New Task"),
        ("s", "scan_workspace", "Scan Workspace"),
        ("g", "generate_digest", "Generate Digest"),
        ("o", "route_next", "Route Next"),
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
        self._config = config
        self._selected_workspace_id = selected_workspace_id
        self._selected_workspace_name = selected_workspace_name
        self._selected_task_id: str | None = None
        self._selected_task_title: str | None = None
        self._workspaces: list[dict[str, Any]] = []
        self._tasks: list[dict[str, Any]] = []
        self._runs: list[dict[str, Any]] = []
        self._summary: dict[str, Any] = {}
        self._last_scan: dict[str, Any] | None = None
        self._last_digest: dict[str, Any] | None = None
        self._last_route: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(classes="pane"):
                yield Static("Workspaces / Tasks", id="left")
            with Vertical(classes="pane"):
                yield Static("Agent Runs / Events", id="center")
            with Vertical(classes="pane"):
                yield Static("Detail", id="right")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(3.0, self.action_refresh)
        self.action_refresh()

    def action_refresh(self) -> None:
        try:
            self._summary = self._client.dashboard_summary()
            self._workspaces = self._safe_request(self._client.list_workspaces, [])
            self._tasks = self._safe_request(self._client.list_tasks, [])
            self._runs = self._safe_request(self._client.list_agent_runs, [])

            self._sync_workspace_selection()
            self._sync_task_selection()

            if not self._update_panes():
                return
            self.sub_title = (
                f"API {self._config.api_url} | "
                f"{self._summary.get('health', 'unknown')}"
            )
        except SyncoreApiError as error:
            if not self._update_panes(
                left="Offline",
                center="Could not load data",
                right=str(error),
            ):
                return
            self.sub_title = f"API offline: {self._config.api_url}"

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

    def _safe_request(self, fn, default):
        try:
            return fn()
        except SyncoreApiError:
            return default

    def _sync_workspace_selection(self) -> None:
        if not self._workspaces:
            self._selected_workspace_id = None
            self._selected_workspace_name = None
            return

        for workspace in self._workspaces:
            if str(workspace.get("id")) == self._selected_workspace_id:
                self._selected_workspace_name = str(workspace.get("name", "unknown"))
                return

        if self._selected_workspace_name:
            for workspace in self._workspaces:
                if str(workspace.get("name")) == self._selected_workspace_name:
                    self._selected_workspace_id = str(workspace.get("id"))
                    return

        first = self._workspaces[0]
        self._selected_workspace_id = str(first.get("id"))
        self._selected_workspace_name = str(first.get("name", "unknown"))

    def _sync_task_selection(self) -> None:
        if not self._tasks:
            self._selected_task_id = None
            self._selected_task_title = None
            return

        for task in self._tasks:
            if str(task.get("id")) == self._selected_task_id:
                self._selected_task_title = str(task.get("title", "unknown"))
                return

        first = self._tasks[0]
        self._selected_task_id = str(first.get("id"))
        self._selected_task_title = str(first.get("title", "unknown"))

    def _current_workspace(self) -> dict[str, Any] | None:
        if self._selected_workspace_id is None:
            return None
        for workspace in self._workspaces:
            if str(workspace.get("id")) == self._selected_workspace_id:
                return workspace
        return None

    def _current_task(self) -> dict[str, Any] | None:
        if self._selected_task_id is None:
            return None
        for task in self._tasks:
            if str(task.get("id")) == self._selected_task_id:
                return task
        return None

    def _render_left_pane(self) -> str:
        lines = [
            f"View: {self.current_view}",
            f"Workspaces: {self._summary.get('workspace_count', len(self._workspaces))}",
            f"Open tasks: {self._summary.get('open_task_count', 0)}",
            "",
            "Workspace list:",
        ]
        for workspace in self._workspaces[:5]:
            marker = (
                "*"
                if str(workspace.get("id")) == self._selected_workspace_id
                else "-"
            )
            lines.append(f"{marker} {workspace.get('name')} ({workspace.get('id')})")
        return "\n".join(lines)

    def _render_center_pane(self) -> str:
        lines = [
            f"Active runs: {self._summary.get('active_run_count', 0)}",
            f"Recent events: {len(self._summary.get('recent_events', []))}",
            "",
            "Task list:",
        ]
        for task in self._tasks[:5]:
            marker = "*" if str(task.get("id")) == self._selected_task_id else "-"
            lines.append(
                f"{marker} {task.get('title')} [{task.get('status')}] ({task.get('id')})"
            )
        return "\n".join(lines)

    def _render_right_pane(self) -> str:
        lines = [
            f"API: {self._config.api_url}",
            f"Runtime: {self._summary.get('runtime_mode')}",
            f"Health: {self._summary.get('health')}",
            f"Workspace: {self._selected_workspace_name or 'none'}",
            f"Task: {self._selected_task_title or 'none'}",
        ]
        if self._last_route:
            lines.append("")
            lines.append(
                "Last route: "
                f"{self._last_route.get('worker_role')} / {self._last_route.get('model_tier')}"
            )
        if self._last_digest:
            lines.append("")
            lines.append(
                "Last digest: "
                f"{self._last_digest.get('headline') or self._last_digest.get('summary', '')[:80]}"
            )
        if self._last_scan:
            scan = self._last_scan.get("scan", {})
            lines.append("")
            lines.append(f"Last scan languages: {', '.join(scan.get('languages', []))}")
        lines.append("")
        lines.append("n=new task s=scan g=digest o=route")
        return "\n".join(lines)

    def _switch(self, view: str) -> None:
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

    def action_new_task(self) -> None:
        self.push_screen(
            NewTaskScreen(workspace_name=self._selected_workspace_name),
            callback=self._handle_new_task_payload,
        )

    def _handle_new_task_payload(self, payload: dict[str, str] | None) -> None:
        if payload is None:
            return

        title = payload["title"]
        description = payload["description"].strip()
        workspace_name = self._selected_workspace_name
        if workspace_name:
            title = f"[{workspace_name}] {title}"
        if description:
            title = f"{title} - {description}"

        create_payload = {
            "title": title,
            "task_type": payload["task_type"],
            "complexity": payload["complexity"],
        }
        try:
            created = self._client.create_task(create_payload)
        except SyncoreApiError as error:
            self.notify(str(error), severity="error")
            return

        self._selected_task_id = str(created.get("id"))
        self._selected_task_title = str(created.get("title", "unknown"))
        self.notify(f"Created task {self._selected_task_id}")
        self.action_refresh()

    def action_scan_workspace(self) -> None:
        workspace = self._current_workspace()
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
        task = self._current_task()
        if task is None:
            self.notify("No task available for digest.", severity="warning")
            return
        task_id = str(task.get("id"))
        try:
            self._last_digest = self._client.generate_digest({"task_id": task_id, "limit": 50})
        except SyncoreApiError as error:
            self.notify(str(error), severity="error")
            return

        self.notify(f"Generated digest for task {task_id}")
        self.action_refresh()

    def action_route_next(self) -> None:
        task = self._current_task()
        if task is None:
            self.notify("No task available for routing.", severity="warning")
            return
        task_id = str(task.get("id"))

        try:
            task_detail = self._client.get_task(task_id)
            task_payload = task_detail.get("task", task_detail)
            self._last_route = self._client.route_next_action(
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
            f"{task_id}: {self._last_route.get('worker_role')}/"
            f"{self._last_route.get('model_tier')}"
        )
        self.action_refresh()
