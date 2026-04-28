from syncore_cli.config import CliConfig
from syncore_cli.tui import SyncoreTuiApp
from textual.css.query import NoMatches


class FakeClient:
    def __init__(self) -> None:
        self.created_payload = None
        self.created_event_payload = None
        self.scanned_workspace_id = None
        self.digest_task_id = None
        self.routed_payload = None
        self.started_run_payload = None
        self.executed_payload = None
        self.autonomy_calls = 0

    def create_task(self, payload):
        self.created_payload = payload
        return {"id": "t-created", "title": payload["title"]}

    def create_project_event(self, payload):
        self.created_event_payload = payload
        return {"id": "e1", **payload}

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

    def create_agent_run(self, payload):
        self.started_run_payload = payload
        return {"id": "r1", **payload}

    def execute_run(self, payload):
        self.executed_payload = payload
        return {"status": "completed", "target_model": payload["target_model"]}

    def autonomy_scan_once(self, limit: int = 50):
        self.autonomy_calls += 1
        return {"processed": 1, "results": []}

    def dashboard_summary(self):
        return {"health": "ok", "runtime_mode": "native"}

    def list_workspaces(self):
        return []

    def list_tasks(self):
        return []

    def list_agent_runs(self):
        return []


def test_tui_initializes() -> None:
    app = SyncoreTuiApp(CliConfig(api_url="http://localhost:8000", timeout_seconds=1.0))
    assert app is not None


def test_action_new_task_creates_task(monkeypatch) -> None:
    app = SyncoreTuiApp(CliConfig(api_url="http://localhost:8000", timeout_seconds=1.0))
    fake = FakeClient()
    app._client = fake
    app._selected_workspace_id = "w1"
    app._selected_workspace_name = "syncore"
    app.notify = lambda *args, **kwargs: None
    app.action_refresh = lambda: None

    def _fake_push_screen(_screen, callback=None):
        assert callback is not None
        callback(
            {
                "title": "Implement feature",
                "description": "with tests",
                "preferred_provider": "openai",
                "task_type": "implementation",
                "complexity": "medium",
                "preferred_model": "gpt-5.5",
                "preferred_agent_role": "coder",
                "execution_prompt": "Implement and test the feature.",
            }
        )

    app.push_screen = _fake_push_screen  # type: ignore[method-assign]
    app.action_new_task()

    assert fake.created_payload is not None
    assert fake.created_payload["task_type"] == "implementation"
    assert fake.created_payload["complexity"] == "medium"
    assert fake.created_payload["title"].startswith("Implement feature")
    assert fake.created_payload["workspace_id"] == "w1"
    assert fake.created_event_payload is not None
    assert fake.created_event_payload["event_type"] == "task.preferences"
    assert fake.created_event_payload["event_data"]["preferred_model"] == "gpt-5.5"
    assert fake.created_event_payload["event_data"]["preferred_provider"] == "openai"


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


def test_action_start_agent_run_uses_preferences() -> None:
    app = SyncoreTuiApp(CliConfig(api_url="http://localhost:8000", timeout_seconds=1.0))
    fake = FakeClient()
    app._client = fake
    app._tasks = [{"id": "t1", "title": "Task 1"}]
    app._task_preferences = {"preferred_agent_role": "reviewer"}
    app.notify = lambda *args, **kwargs: None
    app.action_refresh = lambda: None

    app.action_start_agent_run()
    assert fake.started_run_payload is not None
    assert fake.started_run_payload["task_id"] == "t1"
    assert fake.started_run_payload["role"] == "reviewer"


def test_action_execute_task_uses_model_preferences() -> None:
    app = SyncoreTuiApp(CliConfig(api_url="http://localhost:8000", timeout_seconds=1.0))
    fake = FakeClient()
    app._client = fake
    app._tasks = [{"id": "t1", "title": "Task 1"}]
    app._task_preferences = {
        "preferred_agent_role": "coder",
        "preferred_model": "gpt-5.5",
        "execution_prompt": "Do the thing",
    }
    app.notify = lambda *args, **kwargs: None
    app.action_refresh = lambda: None

    app.action_execute_task()
    assert fake.executed_payload is not None
    assert fake.executed_payload["task_id"] == "t1"
    assert fake.executed_payload["target_model"] == "gpt-5.5"
    assert fake.executed_payload["prompt"] == "Do the thing"


def test_toggle_autonomy_runs_scan_on_refresh() -> None:
    app = SyncoreTuiApp(CliConfig(api_url="http://localhost:8000", timeout_seconds=1.0))
    fake = FakeClient()
    app._client = fake
    app.notify = lambda *args, **kwargs: None
    app._update_panes = lambda **kwargs: True  # type: ignore[method-assign]

    app.action_toggle_autonomy()
    assert app._autonomy_enabled is True
    assert fake.autonomy_calls >= 1
    assert app._last_autonomy_processed == 1


def test_new_task_model_regex_filter_and_complete() -> None:
    from syncore_cli.tui import NewTaskScreen

    screen = NewTaskScreen(
        workspace_name="syncore",
        available_models=["gpt-5.4", "gpt-5.2-codex", "o3-mini"],
    )
    # Build simple stubs without mounting Textual.
    class _Input:
        def __init__(self, value: str = "") -> None:
            self.value = value

    class _Label:
        def __init__(self) -> None:
            self.text = ""

        def update(self, value: str) -> None:
            self.text = value

    task_provider = _Input("openai")
    task_model = _Input("gpt")
    task_title = _Input("")
    label = _Label()

    def _query_one(selector, _type=None):
        if selector == "#task-provider":
            return task_provider
        if selector == "#task-model":
            return task_model
        if selector == "#task-title":
            return task_title
        if selector == "#task-model-list":
            return label
        raise AssertionError(selector)

    screen.query_one = _query_one  # type: ignore[method-assign]
    screen._refresh_model_matches()
    assert "gpt-5.4" in screen._matching_models
    assert "gpt-5.2-codex" in screen._matching_models
    screen.action_next_model()
    assert task_model.value in screen._matching_models
    assert "gpt-" in label.text


def test_new_task_provider_scopes_matches() -> None:
    from syncore_cli.tui import NewTaskScreen

    screen = NewTaskScreen(
        workspace_name="syncore",
        available_models=["gpt-5.4", "claude-3-7-sonnet", "gemini-2.5-pro"],
    )

    class _Input:
        def __init__(self, value: str = "") -> None:
            self.value = value

    class _Label:
        def __init__(self) -> None:
            self.text = ""

        def update(self, value: str) -> None:
            self.text = value

    task_provider = _Input("anthropic")
    task_model = _Input("")
    task_title = _Input("")
    label = _Label()

    def _query_one(selector, _type=None):
        if selector == "#task-provider":
            return task_provider
        if selector == "#task-model":
            return task_model
        if selector == "#task-title":
            return task_title
        if selector == "#task-model-list":
            return label
        raise AssertionError(selector)

    screen.query_one = _query_one  # type: ignore[method-assign]
    screen._refresh_model_matches()
    assert all(model.startswith("claude") for model in screen._matching_models)
    assert "anthropic" in label.text
