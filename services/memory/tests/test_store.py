from datetime import datetime, timezone
from uuid import uuid4

from packages.contracts.python.models import (
    AgentRunCreate,
    AgentRunUpdate,
    BatonPacketCreate,
    BatonPayload,
    ProjectEventCreate,
    TaskCreate,
    WorkspaceCreate,
    WorkspaceUpdate,
)
from services.memory.store import MemoryStore


class FakeCursor:
    def __init__(
        self, *, fetchone_result=None, fetchall_result=None, rowcount: int = 1
    ) -> None:
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
        self.rowcount = rowcount
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.statements.append((query, params))

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.fetchall_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.committed = False

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_create_task_persists_record(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    row = {
        "id": uuid4(),
        "title": "Plan prototype",
        "status": "new",
        "task_type": "analysis",
        "complexity": "medium",
        "created_at": now,
        "updated_at": now,
    }
    fake_cursor = FakeCursor(fetchone_result=row)
    fake_connection = FakeConnection(fake_cursor)
    monkeypatch.setattr(
        "services.memory.store.psycopg.connect", lambda *_, **__: fake_connection
    )

    store = MemoryStore("postgresql://unused")
    task = store.create_task(TaskCreate(title="Plan prototype", task_type="analysis"))

    assert task.title == "Plan prototype"
    assert any("INSERT INTO tasks" in sql for sql, _ in fake_cursor.statements)


def test_save_baton_packet_inserts_record(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    row = {
        "id": uuid4(),
        "task_id": uuid4(),
        "from_agent": "planner",
        "to_agent": "coder",
        "summary": "handoff",
        "payload": {
            "objective": "Ship local MVP",
            "completed_work": ["Created task"],
            "constraints": ["No AWS"],
            "open_questions": ["Need UI details"],
            "next_best_action": "Implement API routes",
            "relevant_artifacts": ["README.md"],
        },
        "created_at": now,
    }
    fake_cursor = FakeCursor(fetchone_result=row)
    fake_connection = FakeConnection(fake_cursor)

    monkeypatch.setattr(
        "services.memory.store.psycopg.connect", lambda *_, **__: fake_connection
    )

    store = MemoryStore("postgresql://unused")
    saved = store.save_baton_packet(
        BatonPacketCreate(
            task_id=row["task_id"],
            from_agent="planner",
            to_agent="coder",
            summary="handoff",
            payload=BatonPayload(
                objective="Ship local MVP",
                completed_work=["Created task"],
                constraints=["No AWS"],
                open_questions=["Need UI details"],
                next_best_action="Implement API routes",
                relevant_artifacts=["README.md"],
            ),
        )
    )

    assert saved.task_id == row["task_id"]
    assert saved.payload.objective == "Ship local MVP"
    assert any("INSERT INTO baton_packets" in sql for sql, _ in fake_cursor.statements)
    assert fake_connection.committed is True


def test_list_project_events_returns_models(monkeypatch) -> None:
    task_id = uuid4()
    now = datetime.now(timezone.utc)
    fake_cursor = FakeCursor(
        fetchall_result=[
            {
                "id": uuid4(),
                "task_id": task_id,
                "event_type": "task.created",
                "event_data": {"title": "hello"},
                "created_at": now,
            }
        ]
    )
    fake_connection = FakeConnection(fake_cursor)

    monkeypatch.setattr(
        "services.memory.store.psycopg.connect", lambda *_, **__: fake_connection
    )

    store = MemoryStore("postgresql://unused")
    records = store.list_project_events(task_id, limit=500)

    assert len(records) == 1
    assert records[0].event_type == "task.created"
    assert any("FROM project_events" in sql for sql, _ in fake_cursor.statements)


def test_save_project_event_uses_event_payload(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    task_id = uuid4()
    fake_cursor = FakeCursor(
        fetchone_result={
            "id": uuid4(),
            "task_id": task_id,
            "event_type": "task.updated",
            "event_data": {"status": "in_progress"},
            "created_at": now,
        }
    )
    fake_connection = FakeConnection(fake_cursor)

    monkeypatch.setattr(
        "services.memory.store.psycopg.connect", lambda *_, **__: fake_connection
    )

    store = MemoryStore("postgresql://unused")
    event = store.save_project_event(
        ProjectEventCreate(
            task_id=task_id,
            event_type="task.updated",
            event_data={"status": "in_progress"},
        )
    )

    assert event.event_data["status"] == "in_progress"
    assert any("INSERT INTO project_events" in sql for sql, _ in fake_cursor.statements)


def test_create_and_update_agent_run(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    task_id = uuid4()
    create_row = {
        "id": uuid4(),
        "task_id": task_id,
        "role": "planner",
        "status": "queued",
        "input_summary": "Start plan",
        "output_summary": None,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }

    fake_cursor = FakeCursor(fetchone_result=create_row)
    fake_connection = FakeConnection(fake_cursor)
    monkeypatch.setattr(
        "services.memory.store.psycopg.connect", lambda *_, **__: fake_connection
    )

    store = MemoryStore("postgresql://unused")
    run = store.create_agent_run(
        AgentRunCreate(task_id=task_id, role="planner", input_summary="Start plan")
    )

    assert run.role == "planner"
    assert any("INSERT INTO agent_runs" in sql for sql, _ in fake_cursor.statements)

    update_row = {
        **create_row,
        "status": "completed",
        "output_summary": "Plan complete",
    }
    fake_cursor_update = FakeCursor(fetchone_result=update_row)
    fake_connection_update = FakeConnection(fake_cursor_update)
    monkeypatch.setattr(
        "services.memory.store.psycopg.connect", lambda *_, **__: fake_connection_update
    )

    updated = store.update_agent_run(
        run.id,
        AgentRunUpdate(status="completed", output_summary="Plan complete"),
    )

    assert updated is not None
    assert updated.status == "completed"
    assert any("UPDATE agent_runs" in sql for sql, _ in fake_cursor_update.statements)


def test_workspace_crud_sql_paths(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    workspace_id = uuid4()

    create_cursor = FakeCursor(
        fetchone_result={
            "id": workspace_id,
            "name": "Syncore",
            "root_path": "/tmp/syncore",
            "repo_url": "https://example.com/repo.git",
            "branch": "main",
            "runtime_mode": "native",
            "metadata": {"owner": "dev"},
            "created_at": now,
            "updated_at": now,
        }
    )
    monkeypatch.setattr(
        "services.memory.store.psycopg.connect",
        lambda *_, **__: FakeConnection(create_cursor),
    )
    store = MemoryStore("postgresql://unused")
    created = store.create_workspace(
        WorkspaceCreate(
            name="Syncore",
            root_path="/tmp/syncore",
            repo_url="https://example.com/repo.git",
            branch="main",
            runtime_mode="native",
            metadata={"owner": "dev"},
        )
    )
    assert created.id == workspace_id
    assert any("INSERT INTO workspaces" in sql for sql, _ in create_cursor.statements)

    list_cursor = FakeCursor(
        fetchall_result=[
            {
                "id": workspace_id,
                "name": "Syncore",
                "root_path": "/tmp/syncore",
                "repo_url": "https://example.com/repo.git",
                "branch": "main",
                "runtime_mode": "native",
                "metadata": {"owner": "dev"},
                "created_at": now,
                "updated_at": now,
            }
        ]
    )
    monkeypatch.setattr(
        "services.memory.store.psycopg.connect",
        lambda *_, **__: FakeConnection(list_cursor),
    )
    listed = store.list_workspaces()
    assert len(listed) == 1
    assert any("FROM workspaces" in sql for sql, _ in list_cursor.statements)

    update_cursor = FakeCursor(
        fetchone_result={
            "id": workspace_id,
            "name": "Syncore Updated",
            "root_path": "/tmp/syncore",
            "repo_url": "https://example.com/repo.git",
            "branch": "develop",
            "runtime_mode": "native",
            "metadata": {"owner": "dev"},
            "created_at": now,
            "updated_at": now,
        }
    )
    monkeypatch.setattr(
        "services.memory.store.psycopg.connect",
        lambda *_, **__: FakeConnection(update_cursor),
    )
    updated = store.update_workspace(
        workspace_id,
        WorkspaceUpdate(name="Syncore Updated", branch="develop"),
    )
    assert updated is not None
    assert updated.branch == "develop"
    assert any("UPDATE workspaces" in sql for sql, _ in update_cursor.statements)

    delete_cursor = FakeCursor(rowcount=1)
    monkeypatch.setattr(
        "services.memory.store.psycopg.connect",
        lambda *_, **__: FakeConnection(delete_cursor),
    )
    assert store.delete_workspace(workspace_id) is True
    assert any("DELETE FROM workspaces" in sql for sql, _ in delete_cursor.statements)
