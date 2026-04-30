from __future__ import annotations

import httpx

from syncore_cli.client import SyncoreApiClient


class DummyResponse:
    def __init__(self) -> None:
        self.status_code = 200
        self.reason_phrase = "OK"
        self.headers = {"content-type": "application/json"}

    def json(self):
        return {"status": "ok"}


def test_client_builds_correct_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_request(method: str, url: str, json=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        return DummyResponse()

    monkeypatch.setattr(httpx, "request", fake_request)
    client = SyncoreApiClient("http://localhost:8000")
    result = client.health()

    assert captured["method"] == "GET"
    assert captured["url"] == "http://localhost:8000/health"
    assert result["status"] == "ok"


def test_client_builds_project_event_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_request(method: str, url: str, json=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        return DummyResponse()

    monkeypatch.setattr(httpx, "request", fake_request)
    client = SyncoreApiClient("http://localhost:8000")
    client.create_project_event(
        {"task_id": "00000000-0000-0000-0000-000000000001", "event_type": "x", "event_data": {}}
    )

    assert captured["method"] == "POST"
    assert captured["url"] == "http://localhost:8000/project-events"


def test_client_builds_execute_run_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_request(method: str, url: str, json=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        return DummyResponse()

    monkeypatch.setattr(httpx, "request", fake_request)
    client = SyncoreApiClient("http://localhost:8000")
    client.execute_run(
        {
            "task_id": "00000000-0000-0000-0000-000000000001",
            "prompt": "p",
            "target_agent": "coder",
            "target_model": "gpt-5.4",
            "agent_role": "coder",
        }
    )

    assert captured["method"] == "POST"
    assert captured["url"] == "http://localhost:8000/runs/execute"


def test_client_builds_execute_auto_run_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_request(method: str, url: str, json=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        return DummyResponse()

    monkeypatch.setattr(httpx, "request", fake_request)
    client = SyncoreApiClient("http://localhost:8000")
    client.execute_run_auto(
        {
            "task_id": "00000000-0000-0000-0000-000000000001",
            "prompt": "p",
            "target_agent": "coder",
        }
    )

    assert captured["method"] == "POST"
    assert captured["url"] == "http://localhost:8000/runs/execute-auto"


def test_client_builds_model_switches_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_request(method: str, url: str, json=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        return DummyResponse()

    monkeypatch.setattr(httpx, "request", fake_request)
    client = SyncoreApiClient("http://localhost:8000")
    client.list_task_model_switches("task-1", limit=25)

    assert captured["method"] == "GET"
    assert captured["url"] == "http://localhost:8000/tasks/task-1/model-switches?limit=25"


def test_client_builds_autonomy_scan_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_request(method: str, url: str, json=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        return DummyResponse()

    monkeypatch.setattr(httpx, "request", fake_request)
    client = SyncoreApiClient("http://localhost:8000")
    client.autonomy_scan_once(limit=25)

    assert captured["method"] == "POST"
    assert captured["url"] == "http://localhost:8000/autonomy/scan-once?limit=25"


def test_client_builds_autonomy_approve_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_request(method: str, url: str, json=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        return DummyResponse()

    monkeypatch.setattr(httpx, "request", fake_request)
    client = SyncoreApiClient("http://localhost:8000")
    client.autonomy_approve_task("task-1", reason="ok")

    assert captured["method"] == "POST"
    assert captured["url"] == "http://localhost:8000/autonomy/tasks/task-1/approve"


def test_client_builds_autonomy_reject_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_request(method: str, url: str, json=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        return DummyResponse()

    monkeypatch.setattr(httpx, "request", fake_request)
    client = SyncoreApiClient("http://localhost:8000")
    client.autonomy_reject_task("task-1", reason="no")

    assert captured["method"] == "POST"
    assert captured["url"] == "http://localhost:8000/autonomy/tasks/task-1/reject"
