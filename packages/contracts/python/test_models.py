from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from .models import (
    AgentRunCreate,
    BatonPacket,
    BatonPacketCreate,
    BatonPayload,
    ExecutiveDigest,
    ProjectEvent,
    ProjectEventCreate,
    RunExecutionRequest,
    RunExecutionResponse,
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
        from_agent="planner",
        to_agent="coder",
        summary="handoff",
        payload=BatonPayload(
            objective="Deliver local MVP",
            completed_work=["Created task"],
            constraints=["No AWS"],
            open_questions=["Need route list"],
            next_best_action="Implement /tasks route",
            relevant_artifacts=["README.md"],
        ),
        created_at=now,
    )

    event = ProjectEvent(
        id=uuid4(),
        task_id=task_id,
        event_type="task.created",
        event_data={"title": "Initial task"},
        created_at=now,
    )

    assert baton.to_agent == "coder"
    assert event.event_type == "task.created"


def test_create_payload_schemas_have_defaults() -> None:
    task_id = uuid4()
    baton = BatonPacketCreate(
        task_id=task_id,
        from_agent="planner",
        summary="next",
        payload=BatonPayload(
            objective="Validate flow",
            next_best_action="Create agent run",
        ),
    )
    event = ProjectEventCreate(task_id=task_id, event_type="task.updated")

    assert baton.payload.completed_work == []
    assert event.event_data == {}


def test_routing_request_validates_complexity() -> None:
    request = RoutingRequest(
        task_type="analysis", complexity="high", requires_memory=True
    )

    assert request.complexity == "high"
    assert request.requires_memory is True


def test_executive_digest_requires_headline() -> None:
    try:
        ExecutiveDigest(
            task_id=uuid4(),
            generated_at=datetime.now(timezone.utc),
            headline="",
            summary="summary",
            highlights=[],
            event_breakdown={},
            risk_level="low",
            total_events=0,
        )
    except ValidationError:
        return

    raise AssertionError("ExecutiveDigest validation should fail for empty headline")


def test_agent_run_requires_known_role() -> None:
    try:
        AgentRunCreate(task_id=uuid4(), role="unknown", input_summary="start")
    except ValidationError:
        return

    raise AssertionError("AgentRunCreate validation should fail for unknown role")


def test_run_execution_request_requires_prompt() -> None:
    try:
        RunExecutionRequest(
            task_id=uuid4(),
            prompt="",
            target_agent="coder",
            target_model="gpt-4o-mini",
        )
    except ValidationError:
        return

    raise AssertionError("RunExecutionRequest should fail for empty prompt")


def test_run_execution_response_valid() -> None:
    now = datetime.now(timezone.utc)
    response = RunExecutionResponse(
        run_id=uuid4(),
        task_id=uuid4(),
        status="completed",
        provider="local_echo",
        target_agent="coder",
        target_model="gpt-4o-mini",
        output_text="done",
        estimated_input_tokens=100,
        estimated_output_tokens=20,
        total_estimated_tokens=120,
        included_refs=[],
        warnings=[],
        created_at=now,
        completed_at=now,
    )

    assert response.status == "completed"
