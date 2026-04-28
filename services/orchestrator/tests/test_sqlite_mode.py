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


def test_sqlite_mode_supports_core_workflow(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")

    client = TestClient(create_app())

    health = client.get("/health/services")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    workspace = client.post(
        "/workspaces",
        json={
            "name": "SQLite workspace",
            "root_path": str(tmp_path),
            "runtime_mode": "native",
        },
    )
    assert workspace.status_code == 201
    workspace_id = workspace.json()["id"]

    task = client.post(
        "/tasks",
        json={
            "title": "SQLite native workflow",
            "task_type": "implementation",
            "complexity": "low",
            "workspace_id": workspace_id,
        },
    )
    assert task.status_code == 201
    task_id = task.json()["id"]
    assert task.json()["workspace_id"] == workspace_id

    task_list = client.get(f"/tasks?workspace_id={workspace_id}")
    assert task_list.status_code == 200
    assert len(task_list.json()) >= 1
    assert task_list.json()[0]["workspace_id"] == workspace_id

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
            "summary": "sqlite handoff",
            "payload": {
                "objective": "Run without docker",
                "completed_work": ["Task created"],
                "constraints": ["No postgres required"],
                "open_questions": ["None"],
                "next_best_action": "Assemble context",
                "relevant_artifacts": ["scripts/init_sqlite.sql"],
            },
        },
    )
    assert baton.status_code == 201

    assembled = client.post(
        "/context/assemble",
        json={
            "task_id": task_id,
            "target_agent": "coder",
            "target_model": "gpt-4.1-mini",
            "token_budget": 1400,
        },
    )
    assert assembled.status_code == 200
    assert assembled.json()["estimated_token_count"] <= 1400

    digest = client.get(f"/analyst/digest/{task_id}")
    assert digest.status_code == 200
    assert digest.json()["total_events"] >= 1

    get_settings.cache_clear()
