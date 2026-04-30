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


def test_context_efficiency_metrics_aggregates_bundles(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")

    client = TestClient(create_app())
    task = client.post(
        "/tasks",
        json={
            "title": "Context efficiency test",
            "task_type": "implementation",
            "complexity": "medium",
        },
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    baton = client.post(
        "/baton-packets",
        json={
            "task_id": task_id,
            "from_agent": "planner",
            "to_agent": "coder",
            "summary": "handoff",
            "payload": {
                "objective": "Build feature",
                "completed_work": ["task created"],
                "constraints": ["MUST keep explicit constraints"],
                "open_questions": [],
                "next_best_action": "Assemble context",
                "relevant_artifacts": [],
            },
        },
    )
    assert baton.status_code == 201

    for _ in range(2):
        assembled = client.post(
            "/context/assemble",
            json={
                "task_id": task_id,
                "target_agent": "coder",
                "target_model": "gpt-4.1-mini",
                "token_budget": 800,
            },
        )
        assert assembled.status_code == 200

    metrics = client.get("/metrics/context-efficiency")
    assert metrics.status_code == 200
    payload = metrics.json()

    assert payload["bundle_count"] >= 2
    assert payload["totals"]["raw_tokens"] >= payload["totals"]["optimized_tokens"]
    assert "by_model" in payload
    assert "gpt-4.1-mini" in payload["by_model"]
    assert len(payload["recent_bundles"]) >= 2


def test_metrics_slo_includes_context_efficiency(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")

    client = TestClient(create_app())
    _ = client.get("/health")
    response = client.get("/metrics/slo")
    assert response.status_code == 200
    payload = response.json()

    assert "context_efficiency" in payload
    section = payload["context_efficiency"]
    assert "checks" in section
    assert "thresholds" in section
    assert "metrics" in section
