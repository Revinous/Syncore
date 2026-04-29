from __future__ import annotations

import json

from typer.testing import CliRunner

from syncore_cli.main import app


class FakeClient:
    def __init__(self) -> None:
        self._workspaces = [
            {
                "id": "w1",
                "name": "syncore",
                "root_path": "/tmp",
                "branch": None,
                "runtime_mode": "native",
            }
        ]

    def health(self):
        return {"status": "ok"}

    def services_health(self):
        return {"dependencies": [{"name": "sqlite", "status": "ok"}]}

    def dashboard_summary(self):
        return {"workspace_count": 0, "open_task_count": 0, "active_run_count": 0}

    def list_workspaces(self):
        return self._workspaces

    def create_workspace(self, payload):
        created = payload | {"id": f"w{len(self._workspaces) + 1}"}
        self._workspaces.append(created)
        return created

    def get_workspace(self, workspace_id: str):
        for workspace in self._workspaces:
            if workspace["id"] == workspace_id:
                return workspace
        return {"id": workspace_id, "name": "syncore"}

    def scan_workspace(self, workspace_id: str):
        return {"workspace": {"id": workspace_id}, "scan": {"languages": ["python"]}}

    def list_workspace_files(self, workspace_id: str):
        return {"workspace_id": workspace_id, "files": ["README.md"], "count": 1}

    def list_tasks(self, workspace_id: str | None = None):
        return [
            {
                "id": "t1",
                "title": "demo",
                "status": "new",
                "complexity": "medium",
                "updated_at": "now",
            }
        ]

    def create_task(self, payload):
        self.created_task_payload = payload
        return {"id": "t2", **payload}

    def get_task(self, task_id: str):
        return {
            "task": {"id": task_id, "task_type": "analysis", "complexity": "medium"}
        }

    def switch_task_model(self, task_id: str, payload):
        return {
            "task_id": task_id,
            "previous_provider": "openai",
            "previous_model": "gpt-4.1-mini",
            "preferred_provider": payload["provider"],
            "preferred_model": payload["model"],
            "target_agent": payload["target_agent"],
            "token_budget": payload["token_budget"],
            "context_bundle_id": "11111111-1111-1111-1111-111111111111",
            "estimated_token_count": 512,
            "included_refs": [],
        }

    def list_agent_runs(self):
        return [
            {
                "id": "r1",
                "task_id": "t1",
                "role": "coder",
                "status": "running",
                "updated_at": "now",
            }
        ]

    def create_agent_run(self, payload):
        return {"id": "r2", **payload}

    def get_agent_run_result(self, run_id: str):
        return {
            "run_id": run_id,
            "task_id": "t1",
            "status": "completed",
            "output_summary": "summary",
            "output_ref_id": "ctxref_1",
            "output_text": "full output",
            "retrieval_hint": "GET /context/references/{ref_id}",
        }

    def cancel_agent_run(self, run_id: str):
        return {"id": run_id, "status": "blocked", "error_message": "Canceled by operator."}

    def resume_agent_run(self, run_id: str):
        return {"id": run_id, "status": "queued"}

    def list_task_events(self, task_id: str):
        return [{"id": "e1", "task_id": task_id, "event_type": "started"}]

    def create_project_event(self, payload):
        self.created_event_payload = payload
        return payload

    def list_task_batons(self, task_id: str):
        return [{"id": "b1", "task_id": task_id}]

    def latest_task_baton(self, task_id: str):
        return {"id": "b1", "task_id": task_id}

    def route_next_action(self, payload):
        return {"worker_role": "analyst", "model_tier": "balanced", "reasoning": "ok"}

    def get_task_digest(self, task_id: str):
        return {"task_id": task_id, "summary": "digest"}

    def generate_digest(self, payload):
        return payload | {"summary": "digest"}

    def diagnostics(self):
        return {"service": "orchestrator"}

    def diagnostics_config(self):
        return {"db_backend": "sqlite"}

    def diagnostics_routes(self):
        return {"routes": ["GET /health"]}

    def list_run_providers(self):
        return [
            {
                "provider": "local_echo",
                "model_hint": "local_echo",
                "supports_streaming": True,
                "supports_system_prompt": True,
            }
        ]

    def context_efficiency_metrics(self, limit: int = 200):
        return {
            "bundle_count": max(limit, 1),
            "totals": {
                "raw_tokens": 1000,
                "optimized_tokens": 700,
                "saved_tokens": 300,
                "savings_pct": 30.0,
            },
            "by_model": {"gpt-4.1-mini": {"bundle_count": 1, "raw_tokens": 1000, "optimized_tokens": 700, "saved_tokens": 300}},
            "layering_profiles": {
                "implementation|high|gpt-4.1-mini|coder": {
                    "bundle_count": 3,
                    "layering_modes": {"dual": 3},
                    "legacy_tokens": 3453,
                    "layered_tokens": 3450,
                    "comparison_count": 3,
                }
            },
            "recent_bundles": [],
        }

    def list_notifications(self, acknowledged: bool | None = None, limit: int = 100):
        return {
            "items": [
                {
                    "id": "n1",
                    "category": "research.finding",
                    "title": "Research update",
                    "body": "Upgrade path available",
                    "acknowledged": False,
                    "created_at": "now",
                }
            ][:limit]
        }

    def get_notification(self, notification_id: str):
        return {
            "id": notification_id,
            "category": "research.finding",
            "title": "Research update",
            "body": "Upgrade path available",
            "acknowledged": False,
            "created_at": "now",
        }

    def acknowledge_notification(self, notification_id: str):
        return {
            "notification": {
                "id": notification_id,
                "category": "research.finding",
                "title": "Research update",
                "body": "Upgrade path available",
                "acknowledged": True,
                "created_at": "now",
            }
        }


class OfflineClient(FakeClient):
    def health(self):
        raise RuntimeError("offline")


def test_status_command_healthy(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("syncore_cli.main._client", lambda: FakeClient())
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "orchestrator" in result.stdout


def test_status_command_offline(monkeypatch) -> None:
    runner = CliRunner()

    class _Offline:
        def health(self):
            from syncore_cli.client import SyncoreApiError

            raise SyncoreApiError("offline")

    monkeypatch.setattr("syncore_cli.main._client", lambda: _Offline())
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "Error" in result.stdout


def test_workspace_list_renders(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("syncore_cli.main._client", lambda: FakeClient())
    result = runner.invoke(app, ["workspace", "list"])
    assert result.exit_code == 0
    assert "syncore" in result.stdout


def test_task_list_renders(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("syncore_cli.main._client", lambda: FakeClient())
    result = runner.invoke(app, ["task", "list"])
    assert result.exit_code == 0
    assert "demo" in result.stdout


def test_task_create_sends_payload(monkeypatch) -> None:
    runner = CliRunner()
    fake = FakeClient()
    monkeypatch.setattr("syncore_cli.main._client", lambda: fake)
    result = runner.invoke(
        app,
        ["task", "create", "Test task", "--type", "analysis", "--complexity", "low"],
    )
    assert result.exit_code == 0
    assert fake.created_task_payload["title"] == "Test task"
    assert fake.created_task_payload["task_type"] == "analysis"


def test_notifications_list_and_ack(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("syncore_cli.main._client", lambda: FakeClient())
    listed = runner.invoke(app, ["notifications", "list"])
    assert listed.exit_code == 0
    assert "research.finding" in listed.stdout

    acked = runner.invoke(app, ["notifications", "ack", "n1"])
    assert acked.exit_code == 0
    assert "Acknowledged" in acked.stdout


def test_task_set_prefs_sends_preference_event(monkeypatch) -> None:
    runner = CliRunner()
    fake = FakeClient()
    monkeypatch.setattr("syncore_cli.main._client", lambda: fake)
    result = runner.invoke(
        app,
        [
            "task",
            "set-prefs",
            "t1",
            "--agent-role",
            "reviewer",
            "--provider",
            "openai",
            "--model",
            "gpt-5.4",
            "--prompt",
            "Run full local checks",
            "--requires-approval",
            "--sdlc-enforce",
        ],
    )
    assert result.exit_code == 0
    assert fake.created_event_payload["event_type"] == "task.preferences"
    event_data = fake.created_event_payload["event_data"]
    assert event_data["preferred_agent_role"] == "reviewer"
    assert event_data["preferred_provider"] == "openai"
    assert event_data["preferred_model"] == "gpt-5.4"
    assert event_data["requires_approval"] == "true"
    assert event_data["sdlc_enforce"] == "true"


def test_json_output_is_valid(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("syncore_cli.main._client", lambda: FakeClient())
    result = runner.invoke(app, ["task", "list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)


def test_metrics_context_json_output(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("syncore_cli.main._client", lambda: FakeClient())
    result = runner.invoke(app, ["metrics", "context", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["totals"]["saved_tokens"] == 300


def test_metrics_layering_json_output(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("syncore_cli.main._client", lambda: FakeClient())
    result = runner.invoke(app, ["metrics", "layering", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "implementation|high|gpt-4.1-mini|coder" in payload


def test_open_command_resolves_workspace_and_launches_tui(monkeypatch) -> None:
    runner = CliRunner()
    fake = FakeClient()

    launched: dict[str, object] = {}

    class FakeTui:
        def __init__(self, config, selected_workspace_id=None, selected_workspace_name=None):
            launched["workspace_id"] = selected_workspace_id
            launched["workspace_name"] = selected_workspace_name

        def run(self):
            launched["ran"] = True

    monkeypatch.setattr("syncore_cli.main._client", lambda config=None: fake)
    monkeypatch.setattr("syncore_cli.main._ensure_api_running", lambda config: None)
    monkeypatch.setattr("syncore_cli.main.SyncoreTuiApp", FakeTui)

    result = runner.invoke(app, ["open", "syncore"])
    assert result.exit_code == 0
    assert launched["workspace_id"] == "w1"
    assert launched["workspace_name"] == "syncore"
    assert launched["ran"] is True


def test_open_command_creates_workspace_from_local_path(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    fake = FakeClient()
    project_dir = tmp_path / "demo-repo"
    project_dir.mkdir()

    launched: dict[str, object] = {}

    class FakeTui:
        def __init__(self, config, selected_workspace_id=None, selected_workspace_name=None):
            launched["workspace_id"] = selected_workspace_id
            launched["workspace_name"] = selected_workspace_name

        def run(self):
            launched["ran"] = True

    monkeypatch.setattr("syncore_cli.main._client", lambda config=None: fake)
    monkeypatch.setattr("syncore_cli.main._ensure_api_running", lambda config: None)
    monkeypatch.setattr("syncore_cli.main.SyncoreTuiApp", FakeTui)
    monkeypatch.setenv("SYNCORE_CALLER_CWD", str(tmp_path))

    result = runner.invoke(app, ["open", "demo-repo"])
    assert result.exit_code == 0
    assert launched["workspace_id"] == "w2"
    assert launched["workspace_name"] == "demo-repo"
    assert launched["ran"] is True


def test_openai_auth_models_command(monkeypatch) -> None:
    runner = CliRunner()

    class _Store:
        def load(self):
            from syncore_cli.openai_auth import OpenAICredentials

            return OpenAICredentials(api_key="sk-test")

    class _ModelsClient:
        def list_text_models(self, api_key: str):
            assert api_key == "sk-test"
            return ["gpt-5.4", "gpt-5.2-codex"]

    monkeypatch.setattr("syncore_cli.main._openai_store", lambda: _Store())
    monkeypatch.setattr("syncore_cli.main._openai_models_client", lambda config=None: _ModelsClient())
    result = runner.invoke(app, ["auth", "openai", "models", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 2


def test_run_result_json(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("syncore_cli.main._client", lambda: FakeClient())
    result = runner.invoke(app, ["run", "result", "r1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["run_id"] == "r1"
    assert payload["output_ref_id"] == "ctxref_1"


def test_task_switch_model_json(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("syncore_cli.main._client", lambda: FakeClient())
    result = runner.invoke(
        app,
        [
            "task",
            "switch-model",
            "t1",
            "--provider",
            "openai",
            "--model",
            "gpt-5.4",
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["task_id"] == "t1"
    assert payload["preferred_provider"] == "openai"
    assert payload["preferred_model"] == "gpt-5.4"


def test_providers_json(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("syncore_cli.main._client", lambda: FakeClient())
    result = runner.invoke(app, ["providers", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["provider"] == "local_echo"


def test_run_cancel_json(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("syncore_cli.main._client", lambda: FakeClient())
    result = runner.invoke(app, ["run", "cancel", "r1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"


def test_run_resume_json(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("syncore_cli.main._client", lambda: FakeClient())
    result = runner.invoke(app, ["run", "resume", "r1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "queued"
