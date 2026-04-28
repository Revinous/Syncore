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


def test_context_layering_flag_keeps_contract_and_dual_comparison(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("CONTEXT_LAYERING_ENABLED", "true")
    monkeypatch.setenv("CONTEXT_LAYERING_DUAL_MODE", "true")

    client = TestClient(create_app())

    task = client.post(
        "/tasks",
        json={
            "title": "Layering rollout",
            "task_type": "implementation",
            "complexity": "medium",
        },
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    event = client.post(
        "/project-events",
        json={
            "task_id": task_id,
            "event_type": "tool.exec",
            "event_data": {
                "stderr": "\\n".join([f"line {i}" for i in range(3000)]),
                "command": "pytest -q",
            },
        },
    )
    assert event.status_code == 201

    assembled = client.post(
        "/context/assemble",
        json={
            "task_id": task_id,
            "target_agent": "coder",
            "target_model": "gpt-4.1-mini",
            "token_budget": 1200,
        },
    )
    assert assembled.status_code == 200
    payload = assembled.json()
    assert "rendered_prompt" in payload["optimized_context"]
    assert payload["optimized_context"]["layering_mode"] == "dual"
    assert "layering_comparison" in payload["optimized_context"]

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM context_reference_layers",
        ).fetchone()
    assert row is not None
    assert int(row[0]) >= 1
