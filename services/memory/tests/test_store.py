from datetime import datetime, timezone
from uuid import uuid4

from packages.contracts.python.models import BatonPacketCreate, ProjectEventCreate
from services.memory.store import MemoryStore


class FakeCursor:
    def __init__(self, *, fetchone_result=None, fetchall_result=None) -> None:
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
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


def test_save_baton_packet_inserts_record(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    row = {
        "id": uuid4(),
        "task_id": uuid4(),
        "from_agent": "router",
        "to_agent": "analyst",
        "summary": "handoff",
        "payload": {"key": "value"},
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
            from_agent="router",
            to_agent="analyst",
            summary="handoff",
            payload={"key": "value"},
        )
    )

    assert saved.task_id == row["task_id"]
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
