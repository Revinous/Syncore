from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
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


def test_dashboard_summary_native_sqlite(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")

    client = TestClient(create_app())

    workspace = client.post(
        "/workspaces",
        json={
            "name": "Demo",
            "root_path": str(tmp_path),
            "runtime_mode": "native",
            "metadata": {},
        },
    )
    assert workspace.status_code == 201

    task = client.post(
        "/tasks",
        json={"title": "Build dashboard", "task_type": "implementation", "complexity": "medium"},
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    run = client.post(
        "/agent-runs",
        json={"task_id": task_id, "role": "coder", "status": "running"},
    )
    assert run.status_code == 201

    event = client.post(
        "/project-events",
        json={
            "task_id": task_id,
            "event_type": "analysis.started",
            "event_data": {"status": "in_progress"},
        },
    )
    assert event.status_code == 201

    baton = client.post(
        "/baton-packets",
        json={
            "task_id": task_id,
            "from_agent": "planner",
            "to_agent": "coder",
            "summary": "handoff",
            "payload": {
                "objective": "Ship dashboard",
                "completed_work": ["created task"],
                "constraints": ["local-first"],
                "open_questions": ["none"],
                "next_best_action": "Continue coding",
                "relevant_artifacts": ["README.md"],
            },
        },
    )
    assert baton.status_code == 201

    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()

    assert payload["runtime_mode"] == "native"
    assert payload["db_backend"] == "sqlite"
    assert payload["services"]["redis"] == "skipped"
    assert payload["workspace_count"] == 1
    assert payload["open_task_count"] == 1
    assert payload["active_run_count"] == 1
    assert len(payload["recent_events"]) >= 1
    assert len(payload["recent_batons"]) >= 1


def test_dashboard_summary_empty_ok_without_redis(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")

    client = TestClient(create_app())

    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["health"] == "ok"
    assert payload["workspace_count"] == 0
    assert payload["open_task_count"] == 0
    assert payload["active_run_count"] == 0


def test_dashboard_reconciles_stale_runs(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("RUN_STALE_TIMEOUT_SECONDS", "60")

    client = TestClient(create_app())

    task = client.post(
        "/tasks",
        json={"title": "Stale planner", "task_type": "analysis", "complexity": "low"},
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    run = client.post(
        "/agent-runs",
        json={"task_id": task_id, "role": "planner", "status": "running"},
    )
    assert run.status_code == 201
    run_id = run.json()["id"]

    stale_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE agent_runs SET updated_at = ? WHERE id = ?",
            (stale_at, run_id),
        )
        connection.commit()

    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["active_run_count"] == 0

    runs = client.get("/agent-runs")
    assert runs.status_code == 200
    reconciled = next(item for item in runs.json() if item["id"] == run_id)
    assert reconciled["status"] == "blocked"
    assert "Marked stale" in (reconciled["error_message"] or "")
