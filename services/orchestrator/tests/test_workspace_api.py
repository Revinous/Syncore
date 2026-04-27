from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

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


def test_workspace_crud_scan_and_files(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "README.md").write_text("# Demo", encoding="utf-8")
    (workspace_root / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (workspace_root / "package.json").write_text(
        json.dumps({"dependencies": {"next": "16.2.4"}, "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (workspace_root / ".env").write_text("SECRET=1", encoding="utf-8")

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")

    client = TestClient(create_app())

    create_response = client.post(
        "/workspaces",
        json={
            "name": "Demo Workspace",
            "root_path": str(workspace_root),
            "repo_url": None,
            "branch": "main",
            "runtime_mode": "native",
            "metadata": {"owner": "local"},
        },
    )
    assert create_response.status_code == 201
    workspace = create_response.json()
    workspace_id = workspace["id"]

    list_response = client.get("/workspaces")
    assert list_response.status_code == 200
    assert any(item["id"] == workspace_id for item in list_response.json())

    get_response = client.get(f"/workspaces/{workspace_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Demo Workspace"

    patch_response = client.patch(
        f"/workspaces/{workspace_id}",
        json={"branch": "develop", "metadata": {"owner": "updated"}},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["branch"] == "develop"

    scan_response = client.post(f"/workspaces/{workspace_id}/scan")
    assert scan_response.status_code == 200
    scan = scan_response.json()["scan"]
    assert "nextjs" in scan["frameworks"]
    assert "requirements.txt" in scan["important_files"]

    files_response = client.get(f"/workspaces/{workspace_id}/files")
    assert files_response.status_code == 200
    files_payload = files_response.json()
    assert "README.md" in files_payload["files"]
    assert ".env" not in files_payload["files"]

    traversal_response = client.get(f"/workspaces/{workspace_id}/files?path=../")
    assert traversal_response.status_code == 403

    delete_response = client.delete(f"/workspaces/{workspace_id}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/workspaces/{workspace_id}")
    assert missing_response.status_code == 404


def test_workspace_routes_return_404_for_missing_workspace(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")

    client = TestClient(create_app())
    missing_id = str(uuid4())

    response = client.post(f"/workspaces/{missing_id}/scan")
    assert response.status_code == 404
