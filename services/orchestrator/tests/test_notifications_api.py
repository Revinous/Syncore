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


def test_research_finding_creates_notification_and_ack_flow(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")

    client = TestClient(create_app())

    task = client.post(
        "/tasks",
        json={"title": "Research task", "task_type": "analysis", "complexity": "medium"},
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    finding = client.post(
        "/research/findings",
        json={
            "task_id": task_id,
            "title": "New framework release",
            "summary": "Framework X shipped major security fixes.",
            "details": "Upgrade path should be scheduled this sprint.",
            "impact_level": "high",
            "source": "researcher",
        },
    )
    assert finding.status_code == 201

    notifications = client.get("/notifications?acknowledged=false")
    assert notifications.status_code == 200
    items = notifications.json()["items"]
    assert len(items) >= 1
    assert items[0]["category"] == "research.finding"

    notification_id = items[0]["id"]
    ack = client.post(f"/notifications/{notification_id}/ack")
    assert ack.status_code == 200
    assert ack.json()["notification"]["acknowledged"] is True
