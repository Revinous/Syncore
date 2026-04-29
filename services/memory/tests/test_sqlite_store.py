from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from packages.contracts.python.models import (
    BatonPacketCreate,
    BatonPayload,
    ProjectEventCreate,
    TaskCreate,
)
from packages.contracts.python.models import WorkspaceCreate, WorkspaceUpdate
from services.memory.sqlite_store import SQLiteMemoryStore


def _init_sqlite(db_path: Path) -> None:
    schema = Path("scripts/init_sqlite.sql").read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as connection:
        connection.executescript(schema)
        connection.commit()


def test_sqlite_store_task_event_and_baton_roundtrip(tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    store = SQLiteMemoryStore(str(db_path))
    task = store.create_task(
        TaskCreate(title="SQLite flow", task_type="implementation")
    )

    event = store.save_project_event(
        ProjectEventCreate(
            task_id=task.id,
            event_type="analysis.started",
            event_data={"status": "in_progress"},
        )
    )
    assert event.task_id == task.id

    packet = store.save_baton_packet(
        BatonPacketCreate(
            task_id=task.id,
            from_agent="planner",
            to_agent="coder",
            summary="handoff",
            payload=BatonPayload(
                objective="Ship native mode",
                completed_work=["Task created"],
                constraints=["Keep deterministic local path"],
                open_questions=["None"],
                next_best_action="Implement sqlite path",
                relevant_artifacts=["scripts/init_sqlite.sql"],
            ),
        )
    )
    assert packet.task_id == task.id
    assert store.get_latest_baton_packet(task.id) is not None
    assert store.count_project_events(task.id) == 1


def test_sqlite_store_context_refs_and_bundles(tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    store = SQLiteMemoryStore(str(db_path))
    task = store.create_task(TaskCreate(title="Context refs", task_type="analysis"))

    ref = store.upsert_context_reference(
        ref_id=f"ctxref_{uuid4().hex[:8]}",
        task_id=task.id,
        content_type="log_output",
        original_content="very large log content",
        summary="large log",
        retrieval_hint="use GET /context/references/{ref_id}",
    )
    assert ref["task_id"] == str(task.id)
    assert store.get_context_reference(str(ref["ref_id"])) is not None

    bundle = store.save_context_bundle(
        task_id=task.id,
        target_agent="coder",
        target_model="gpt-4.1-mini",
        token_budget=1600,
        raw_estimated_tokens=500,
        optimized_estimated_tokens=300,
        token_savings_estimate=200,
        token_savings_pct=40.0,
        estimated_cost_raw_usd=0.001,
        estimated_cost_optimized_usd=0.0006,
        estimated_cost_saved_usd=0.0004,
        optimized_context={"rendered_prompt": "context"},
        included_refs=[str(ref["ref_id"])],
    )
    assert bundle["task_id"] == str(task.id)
    latest = store.get_latest_context_bundle(task.id)
    assert latest is not None
    assert latest["included_refs"] == [str(ref["ref_id"])]
    recent = store.list_recent_context_bundles(limit=10)
    assert len(recent) >= 1


def test_sqlite_store_workspace_crud_roundtrip(tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    store = SQLiteMemoryStore(str(db_path))
    created = store.create_workspace(
        WorkspaceCreate(
            name="Syncore",
            root_path=str(tmp_path),
            repo_url="https://example.com/repo.git",
            branch="main",
            runtime_mode="native",
            metadata={"owner": "local-dev"},
        )
    )
    assert created.name == "Syncore"
    assert created.metadata["owner"] == "local-dev"

    listed = store.list_workspaces(limit=10)
    assert len(listed) == 1
    assert listed[0].id == created.id

    updated = store.update_workspace(
        created.id,
        WorkspaceUpdate(branch="develop", metadata={"owner": "updated"}),
    )
    assert updated is not None
    assert updated.branch == "develop"
    assert updated.metadata["owner"] == "updated"

    fetched = store.get_workspace(created.id)
    assert fetched is not None
    assert fetched.branch == "develop"

    deleted = store.delete_workspace(created.id)
    assert deleted is True
    assert store.get_workspace(created.id) is None


def test_sqlite_store_tasks_can_link_workspace(tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    store = SQLiteMemoryStore(str(db_path))
    workspace = store.create_workspace(
        WorkspaceCreate(
            name="Linked workspace",
            root_path=str(tmp_path),
            runtime_mode="native",
        )
    )
    task = store.create_task(
        TaskCreate(
            title="Task with workspace",
            task_type="analysis",
            workspace_id=workspace.id,
        )
    )
    assert task.workspace_id == workspace.id

    filtered = store.list_tasks(workspace_id=workspace.id)
    assert len(filtered) == 1
    assert filtered[0].id == task.id


def test_sqlite_store_auto_adds_context_bundle_columns_for_legacy_db(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE tasks (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'new',
              task_type TEXT NOT NULL DEFAULT 'analysis',
              complexity TEXT NOT NULL DEFAULT 'medium',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE context_bundles (
              bundle_id TEXT PRIMARY KEY,
              task_id TEXT NOT NULL,
              target_agent TEXT NOT NULL,
              target_model TEXT NOT NULL,
              token_budget INTEGER NOT NULL,
              optimized_context TEXT NOT NULL,
              included_refs TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL
            );
            """
        )
        connection.commit()

    store = SQLiteMemoryStore(str(db_path))
    task = store.create_task(TaskCreate(title="Legacy schema task", task_type="analysis"))

    bundle = store.save_context_bundle(
        task_id=task.id,
        target_agent="coder",
        target_model="local_echo",
        token_budget=2048,
        raw_estimated_tokens=700,
        optimized_estimated_tokens=500,
        token_savings_estimate=200,
        token_savings_pct=28.57,
        estimated_cost_raw_usd=0.002,
        estimated_cost_optimized_usd=0.0014,
        estimated_cost_saved_usd=0.0006,
        optimized_context={"rendered_prompt": "legacy"},
        included_refs=[],
    )
    assert bundle["task_id"] == str(task.id)
