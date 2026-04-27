from syncore_cli.config import CliConfig
from syncore_cli.tui import SyncoreTuiApp
from textual.css.query import NoMatches


class FakeClient:
    def __init__(self) -> None:
        self.created_payload = None
        self.scanned_workspace_id = None
        self.digest_task_id = None
        self.routed_payload = None

    def create_task(self, payload):
        self.created_payload = payload
        return {"id": "t-created", "title": payload["title"]}

    def scan_workspace(self, workspace_id):
        self.scanned_workspace_id = workspace_id
        return {"scan": {"languages": ["python"]}}

    def generate_digest(self, payload):
        self.digest_task_id = payload["task_id"]
        return {"summary": "digest"}

    def get_task(self, task_id):
        return {"task": {"id": task_id, "task_type": "analysis", "complexity": "low"}}

    def route_next_action(self, payload):
        self.routed_payload = payload
        return {"worker_role": "analyst", "model_tier": "balanced"}


def test_tui_initializes() -> None:
    app = SyncoreTuiApp(CliConfig(api_url="http://localhost:8000", timeout_seconds=1.0))
    assert app is not None


def test_action_new_task_creates_task(monkeypatch) -> None:
    app = SyncoreTuiApp(CliConfig(api_url="http://localhost:8000", timeout_seconds=1.0))
    fake = FakeClient()
    app._client = fake
    app._selected_workspace_name = "syncore"
    app.notify = lambda *args, **kwargs: None
    app.action_refresh = lambda: None

    def _fake_push_screen(_screen, callback=None):
        assert callback is not None
        callback(
            {
            "title": "Implement feature",
            "description": "with tests",
            "task_type": "implementation",
            "complexity": "medium",
            }
        )

    app.push_screen = _fake_push_screen  # type: ignore[method-assign]
    app.action_new_task()

    assert fake.created_payload is not None
    assert fake.created_payload["task_type"] == "implementation"
    assert fake.created_payload["complexity"] == "medium"
    assert fake.created_payload["title"].startswith("[syncore] Implement feature")


def test_action_scan_workspace_calls_api() -> None:
    app = SyncoreTuiApp(CliConfig(api_url="http://localhost:8000", timeout_seconds=1.0))
    fake = FakeClient()
    app._client = fake
    app._workspaces = [{"id": "w1", "name": "syncore"}]
    app._selected_workspace_id = "w1"
    app.notify = lambda *args, **kwargs: None
    app.action_refresh = lambda: None

    app.action_scan_workspace()
    assert fake.scanned_workspace_id == "w1"


def test_action_generate_digest_calls_api() -> None:
    app = SyncoreTuiApp(CliConfig(api_url="http://localhost:8000", timeout_seconds=1.0))
    fake = FakeClient()
    app._client = fake
    app._tasks = [{"id": "t1", "title": "Task 1"}]
    app._selected_task_id = "t1"
    app.notify = lambda *args, **kwargs: None
    app.action_refresh = lambda: None

    app.action_generate_digest()
    assert fake.digest_task_id == "t1"


def test_action_route_next_calls_api() -> None:
    app = SyncoreTuiApp(CliConfig(api_url="http://localhost:8000", timeout_seconds=1.0))
    fake = FakeClient()
    app._client = fake
    app._tasks = [{"id": "t1", "title": "Task 1"}]
    app._selected_task_id = "t1"
    app.notify = lambda *args, **kwargs: None
    app.action_refresh = lambda: None

    app.action_route_next()
    assert fake.routed_payload is not None
    assert fake.routed_payload["task_type"] == "analysis"
    assert fake.routed_payload["complexity"] == "low"


def test_action_refresh_ignores_missing_pane_nodes() -> None:
    app = SyncoreTuiApp(CliConfig(api_url="http://localhost:8000", timeout_seconds=1.0))

    class _Client:
        def dashboard_summary(self):
            return {"health": "ok"}

        def list_workspaces(self):
            return []

        def list_tasks(self):
            return []

        def list_agent_runs(self):
            return []

    app._client = _Client()

    def _raise_no_matches(*_args, **_kwargs):
        raise NoMatches("no pane nodes in modal screen")

    app.query_one = _raise_no_matches  # type: ignore[method-assign]
    app.action_refresh()
