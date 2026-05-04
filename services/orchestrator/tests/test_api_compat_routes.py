from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def _init_sqlite(db_path: Path) -> None:
    schema = Path("scripts/init_sqlite.sql").read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as connection:
        connection.executescript(schema)
        connection.commit()


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_compat_routes_work(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    client = TestClient(create_app())

    task = client.post(
        "/tasks",
        json={"title": "Compat", "task_type": "implementation", "complexity": "medium"},
    )
    task_id = task.json()["id"]

    run = client.post(
        "/agent-runs",
        json={"task_id": task_id, "role": "coder", "status": "running"},
    )
    run_id = run.json()["id"]

    client.post(
        "/project-events",
        json={"task_id": task_id, "event_type": "started", "event_data": {"status": "ok"}},
    )

    client.post(
        "/baton-packets",
        json={
            "task_id": task_id,
            "from_agent": "planner",
            "to_agent": "coder",
            "summary": "handoff",
            "payload": {
                "objective": "ship",
                "completed_work": ["task created"],
                "constraints": ["none"],
                "open_questions": ["none"],
                "next_best_action": "continue",
                "relevant_artifacts": ["README.md"],
            },
        },
    )

    assert client.get("/dashboard/summary").status_code == 200
    assert (
        client.post(
            f"/tasks/{task_id}/model-switch",
            json={
                "provider": "local_echo",
                "model": "local_echo",
                "target_agent": "coder",
                "token_budget": 1600,
            },
        ).status_code
        == 200
    )
    denied = client.post(
        f"/tasks/{task_id}/model-switch",
        json={
            "provider": "openai",
            "model": "gpt-5.4",
            "target_agent": "coder",
            "token_budget": 1600,
        },
    )
    assert denied.status_code == 400
    policy = client.get(f"/tasks/{task_id}/model-policy")
    assert policy.status_code == 200
    updated_policy = client.put(
        f"/tasks/{task_id}/model-policy",
        json={
            "plan_provider": "local_echo",
            "plan_model": "local_echo",
            "review_provider": "local_echo",
            "review_model": "local_echo",
            "fallback_order": ["local_echo"],
            "optimization_goal": "speed",
            "allow_cross_provider_switching": False,
            "maintain_context_continuity": True,
            "minimum_context_window": 4096,
        },
    )
    assert updated_policy.status_code == 200
    assert updated_policy.json()["optimization_goal"] == "speed"
    assert client.get("/agent-runs").status_code == 200
    assert client.get(f"/agent-runs/{run_id}").status_code == 200
    assert client.get(f"/agent-runs/{run_id}/result").status_code == 200
    assert client.post(f"/agent-runs/{run_id}/cancel").status_code == 200
    assert client.post(f"/agent-runs/{run_id}/resume").status_code == 200
    assert client.get("/project-events").status_code == 200
    assert client.get(f"/tasks/{task_id}/events").status_code == 200
    assert client.get("/baton-packets").status_code == 200
    assert client.get(f"/tasks/{task_id}/baton-packets").status_code == 200
    assert client.get(f"/tasks/{task_id}/baton-packets/latest").status_code == 200
    assert (
        client.post(
            "/routing/next-action", json={"task_type": "analysis", "complexity": "low"}
        ).status_code
        == 200
    )
    assert client.get(f"/tasks/{task_id}/routing").status_code == 200
    assert client.post("/analyst/digest", json={"task_id": task_id}).status_code == 200
    digest_response = client.get(f"/tasks/{task_id}/digest")
    assert digest_response.status_code == 200
    assert digest_response.json().get("eli5_summary")
    execution_report = client.get(f"/tasks/{task_id}/execution-report")
    assert execution_report.status_code == 200
    assert execution_report.json()["task_id"] == task_id
    assert client.get("/diagnostics").status_code == 200
    assert client.get("/diagnostics/config").status_code == 200
    assert client.get("/diagnostics/routes").status_code == 200
