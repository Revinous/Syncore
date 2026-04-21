from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from .models import BatonPacket, ProjectEvent, Task


def test_task_requires_title() -> None:
    now = datetime.now(timezone.utc)

    try:
        Task(id=uuid4(), title="", status="new", created_at=now, updated_at=now)
    except ValidationError:
        return

    raise AssertionError("Task validation should fail for empty title")


def test_baton_packet_and_event_are_valid() -> None:
    now = datetime.now(timezone.utc)
    task_id = uuid4()

    baton = BatonPacket(
        id=uuid4(),
        task_id=task_id,
        from_agent="router",
        to_agent="analyst",
        summary="handoff",
        payload={"complexity": "low"},
        created_at=now,
    )

    event = ProjectEvent(
        id=uuid4(),
        task_id=task_id,
        event_type="task.created",
        event_data={"title": "Initial task"},
        created_at=now,
    )

    assert baton.to_agent == "analyst"
    assert event.event_type == "task.created"
