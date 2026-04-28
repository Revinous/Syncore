from __future__ import annotations

import sqlite3
import time
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


def test_autonomy_scan_once_executes_new_task(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    client = TestClient(create_app())
    task = client.post(
        "/tasks",
        json={
            "title": "Build an auth flow with signup and login",
            "task_type": "implementation",
            "complexity": "medium",
        },
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    for _ in range(4):
        scan = client.post("/autonomy/scan-once")
        assert scan.status_code == 200
        assert scan.json()["processed"] >= 1
        detail = client.get(f"/tasks/{task_id}")
        assert detail.status_code == 200
        if detail.json()["task"]["status"] == "completed":
            break

    detail = client.get(f"/tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["task"]["status"] == "completed"
    assert len(detail.json()["agent_runs"]) >= 3

    events = client.get(f"/tasks/{task_id}/events")
    assert events.status_code == 200
    event_types = {event["event_type"] for event in events.json()}
    assert "autonomy.stage.completed" in event_types
    assert "routing.decision" in event_types
    assert "autonomy.completed" in event_types
    assert "analyst.digest.generated" in event_types


def test_autonomy_background_loop_processes_new_task(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_POLL_INTERVAL_SECONDS", "0.2")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Create API endpoint for invoices",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        deadline = time.time() + 4.0
        final_status = "new"
        while time.time() < deadline:
            detail = client.get(f"/tasks/{task_id}")
            final_status = detail.json()["task"]["status"]
            if final_status == "completed":
                break
            time.sleep(0.2)

        assert final_status == "completed"


def test_autonomy_retries_and_blocks_after_budget(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "missing_provider")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_MAX_RETRIES", "1")
    monkeypatch.setenv("AUTONOMY_RETRY_BASE_SECONDS", "0.1")
    monkeypatch.setenv("PROVIDER_FAILOVER_ENABLED", "false")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Task that will fail provider resolution",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        first = client.post(f"/autonomy/tasks/{task_id}/run")
        assert first.status_code == 200
        assert first.json()["status"] == "retry_scheduled"

        second = client.post(f"/autonomy/tasks/{task_id}/run")
        assert second.status_code == 200
        assert second.json()["status"] in {"waiting_retry", "failed"}

        if second.json()["status"] != "failed":
            time.sleep(0.15)
            third = client.post(f"/autonomy/tasks/{task_id}/run")
            assert third.status_code == 200
            assert third.json()["status"] == "failed"

        detail = client.get(f"/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["task"]["status"] == "blocked"


def test_autonomy_requires_approval_and_resumes_after_approve(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Approval gated task",
                "task_type": "implementation",
                "complexity": "medium",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        pref = client.post(
            "/project-events",
            json={
                "task_id": task_id,
                "event_type": "task.preferences",
                "event_data": {"requires_approval": "true"},
            },
        )
        assert pref.status_code == 201

        first = client.post(f"/autonomy/tasks/{task_id}/run")
        assert first.status_code == 200
        assert first.json()["status"] in {"in_progress", "completed"}

        second = client.post(f"/autonomy/tasks/{task_id}/run")
        assert second.status_code == 200
        assert second.json()["status"] == "awaiting_approval"

        approve = client.post(
            f"/autonomy/tasks/{task_id}/approve",
            json={"reason": "looks good"},
        )
        assert approve.status_code == 200
        assert approve.json()["status"] == "approved"

        for _ in range(4):
            run = client.post(f"/autonomy/tasks/{task_id}/run")
            assert run.status_code == 200
            detail = client.get(f"/tasks/{task_id}")
            assert detail.status_code == 200
            if detail.json()["task"]["status"] == "completed":
                break

        final_detail = client.get(f"/tasks/{task_id}")
        assert final_detail.status_code == 200
        assert final_detail.json()["task"]["status"] == "completed"


def test_autonomy_reject_blocks_task(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Approval rejected task",
                "task_type": "implementation",
                "complexity": "medium",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        pref = client.post(
            "/project-events",
            json={
                "task_id": task_id,
                "event_type": "task.preferences",
                "event_data": {"requires_approval": "true"},
            },
        )
        assert pref.status_code == 201

        _ = client.post(f"/autonomy/tasks/{task_id}/run")
        awaiting = client.post(f"/autonomy/tasks/{task_id}/run")
        assert awaiting.status_code == 200
        assert awaiting.json()["status"] == "awaiting_approval"

        reject = client.post(
            f"/autonomy/tasks/{task_id}/reject",
            json={"reason": "not safe"},
        )
        assert reject.status_code == 200
        assert reject.json()["status"] == "rejected"

        detail = client.get(f"/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["task"]["status"] == "blocked"


def test_autonomy_review_gate_completes_with_keyword_instruction(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_REVIEW_PASS_KEYWORD", "SYNCORE_REVIEW_OK")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
            "title": "Task with review pass keyword",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        for _ in range(8):
            run = client.post(f"/autonomy/tasks/{task_id}/run")
            assert run.status_code == 200
            if run.json()["status"] == "completed":
                break

        detail = client.get(f"/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["task"]["status"] == "completed"


def test_autonomy_blocks_when_total_step_budget_reached(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_MAX_TOTAL_STEPS", "1")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Task blocked by max steps",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        seed = client.post(
            "/project-events",
            json={
                "task_id": task_id,
                "event_type": "autonomy.stage.completed",
                "event_data": {"stage": "plan", "cycle": 1},
            },
        )
        assert seed.status_code == 201

        run = client.post(f"/autonomy/tasks/{task_id}/run")
        assert run.status_code == 200
        assert run.json()["status"] == "failed"

        detail = client.get(f"/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["task"]["status"] == "blocked"


def test_autonomy_quality_gate_can_trigger_replan(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_PLAN_MIN_CHARS", "10000")
    monkeypatch.setenv("AUTONOMY_MAX_CYCLES", "2")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Task that should replan from quality gate",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        first = client.post(f"/autonomy/tasks/{task_id}/run")
        assert first.status_code == 200
        assert first.json()["status"] == "replanning"

        events = client.get(f"/tasks/{task_id}/events")
        assert events.status_code == 200
        assert any(e["event_type"] == "autonomy.quality.failed" for e in events.json())
