from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from packages.contracts.python.models import ProjectEvent

from app.api.routes.analyst import get_digest_service, get_memory_store
from app.main import create_app


class FakeMemoryStore:
    def __init__(self, events: list[ProjectEvent]) -> None:
        self.events = events

    def list_project_events(self, task_id, limit):
        assert limit > 0
        return [event for event in self.events if event.task_id == task_id][:limit]


class FailingMemoryStore:
    def list_project_events(self, task_id, limit):
        raise RuntimeError("database unavailable")


def test_analyst_digest_endpoint_returns_summary() -> None:
    task_id = uuid4()
    events = [
        ProjectEvent(
            id=uuid4(),
            task_id=task_id,
            event_type="task.created",
            event_data={"title": "Plan phase 3"},
            created_at=datetime.now(timezone.utc),
        ),
        ProjectEvent(
            id=uuid4(),
            task_id=task_id,
            event_type="task.updated",
            event_data={"status": "in_progress"},
            created_at=datetime.now(timezone.utc),
        ),
    ]

    app = create_app()
    app.dependency_overrides[get_memory_store] = lambda: FakeMemoryStore(events)

    client = TestClient(app)
    response = client.get(f"/analyst/digest/{task_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == str(task_id)
    assert payload["total_events"] == 2
    assert payload["headline"]
    assert payload["summary"]
    assert payload["eli5_summary"]

    app.dependency_overrides.clear()


def test_analyst_digest_endpoint_handles_memory_errors() -> None:
    task_id = uuid4()
    app = create_app()
    app.dependency_overrides[get_memory_store] = lambda: FailingMemoryStore()
    app.dependency_overrides[get_digest_service] = get_digest_service

    client = TestClient(app)
    response = client.get(f"/analyst/digest/{task_id}")

    assert response.status_code == 503
    assert "Memory service unavailable" in response.json()["detail"]

    app.dependency_overrides.clear()
