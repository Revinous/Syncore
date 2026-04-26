from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from packages.contracts.python.models import BatonPacketCreate, BatonPayload, ProjectEventCreate, TaskCreate
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
    task = store.create_task(TaskCreate(title="SQLite flow", task_type="implementation"))

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
        optimized_context={"rendered_prompt": "context"},
        included_refs=[str(ref["ref_id"])],
    )
    assert bundle["task_id"] == str(task.id)
    latest = store.get_latest_context_bundle(task.id)
    assert latest is not None
    assert latest["included_refs"] == [str(ref["ref_id"])]
