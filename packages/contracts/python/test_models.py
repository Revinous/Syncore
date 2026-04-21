from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from .models import (
    BatonPacket,
    BatonPacketCreate,
    ProjectEvent,
    ProjectEventCreate,
    RoutingRequest,
    Task,
    TaskCreate,
)


def test_task_requires_title() -> None:
    now = datetime.now(timezone.utc)

    try:
        Task(
            id=uuid4(),
            title="",
            status="new",
            task_type="analysis",
            complexity="medium",
            created_at=now,
            updated_at=now,
        )
    except ValidationError:
        return

    raise AssertionError("Task validation should fail for empty title")


def test_task_create_requires_valid_type() -> None:
    try:
        TaskCreate(title="Plan release", task_type="invalid", complexity="low")
    except ValidationError:
        return

    raise AssertionError("TaskCreate validation should fail for unknown task_type")


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


def test_create_payload_schemas_have_defaults() -> None:
    task_id = uuid4()
    baton = BatonPacketCreate(
        task_id=task_id, from_agent="orchestrator", summary="next"
    )
    event = ProjectEventCreate(task_id=task_id, event_type="task.updated")

    assert baton.payload == {}
    assert event.event_data == {}


def test_routing_request_validates_complexity() -> None:
    request = RoutingRequest(
        task_type="analysis", complexity="high", requires_memory=True
    )

    assert request.complexity == "high"
    assert request.requires_memory is True
