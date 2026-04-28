from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from packages.contracts.python.models import (
    AgentRun,
    AgentRunCreate,
    AgentRunUpdate,
    BatonPacket,
    BatonPacketCreate,
    ContextBundle,
    MemoryLookupResponse,
    ProjectEvent,
    ProjectEventCreate,
    Task,
    TaskCreate,
    TaskDetail,
)

from app.api.routes.agent_runs import get_agent_run_service
from app.api.routes.analyst import get_memory_store
from app.api.routes.baton_packets import get_baton_service
from app.api.routes.context import get_context_service as get_context_bundle_service
from app.api.routes.memory import get_context_service as get_memory_lookup_service
from app.api.routes.project_events import get_event_service
from app.api.routes.tasks import get_task_service
from app.context.schemas import ContextReference, ContextSection, OptimizedContextBundle
from app.main import create_app


@dataclass
class WorkflowState:
    tasks: dict[UUID, Task] = field(default_factory=dict)
    runs: dict[UUID, AgentRun] = field(default_factory=dict)
    packets: dict[UUID, BatonPacket] = field(default_factory=dict)
    events: list[ProjectEvent] = field(default_factory=list)
    context_references: dict[str, ContextReference] = field(default_factory=dict)


class FakeTaskService:
    def __init__(self, state: WorkflowState) -> None:
        self.state = state

    def create_task(self, payload: TaskCreate) -> Task:
        now = datetime.now(timezone.utc)
        task = Task(
            id=uuid4(),
            title=payload.title,
            status="new",
            task_type=payload.task_type,
            complexity=payload.complexity,
            created_at=now,
            updated_at=now,
        )
        self.state.tasks[task.id] = task
        return task

    def list_tasks(self, limit: int = 50, workspace_id: UUID | None = None) -> list[Task]:
        tasks = list(self.state.tasks.values())
        if workspace_id is not None:
            tasks = [task for task in tasks if task.workspace_id == workspace_id]
        return tasks[:limit]

    def get_task_detail(self, task_id: UUID) -> TaskDetail | None:
        task = self.state.tasks.get(task_id)
        if task is None:
            return None

        runs = [run for run in self.state.runs.values() if run.task_id == task_id]
        packets = [packet for packet in self.state.packets.values() if packet.task_id == task_id]
        event_count = len([event for event in self.state.events if event.task_id == task_id])
        return TaskDetail(
            task=task,
            agent_runs=runs,
            baton_packets=packets,
            event_count=event_count,
            digest_path=f"/analyst/digest/{task_id}",
        )


class FakeAgentRunService:
    def __init__(self, state: WorkflowState) -> None:
        self.state = state

    def create_run(self, payload: AgentRunCreate) -> AgentRun:
        if payload.task_id not in self.state.tasks:
            raise LookupError("Task not found")

        now = datetime.now(timezone.utc)
        run = AgentRun(
            id=uuid4(),
            task_id=payload.task_id,
            role=payload.role,
            status=payload.status,
            input_summary=payload.input_summary,
            output_summary=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self.state.runs[run.id] = run
        return run

    def update_run(self, run_id: UUID, payload: AgentRunUpdate) -> AgentRun | None:
        existing = self.state.runs.get(run_id)
        if existing is None:
            return None

        status = payload.status or existing.status
        output_summary = payload.output_summary or existing.output_summary
        error_message = payload.error_message or existing.error_message
        updated = AgentRun(
            id=existing.id,
            task_id=existing.task_id,
            role=existing.role,
            status=status,
            input_summary=existing.input_summary,
            output_summary=output_summary,
            error_message=error_message,
            created_at=existing.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.state.runs[run_id] = updated
        return updated


class FakeBatonService:
    def __init__(self, state: WorkflowState) -> None:
        self.state = state

    def create_packet(self, payload: BatonPacketCreate) -> BatonPacket:
        if payload.task_id not in self.state.tasks:
            raise LookupError("Task not found")

        packet = BatonPacket(
            id=uuid4(),
            task_id=payload.task_id,
            from_agent=payload.from_agent,
            to_agent=payload.to_agent,
            summary=payload.summary,
            payload=payload.payload,
            created_at=datetime.now(timezone.utc),
        )
        self.state.packets[packet.id] = packet
        return packet

    def get_packet(self, packet_id: UUID) -> BatonPacket | None:
        return self.state.packets.get(packet_id)

    def list_packets_for_task(self, task_id: UUID, limit: int = 50) -> list[BatonPacket]:
        if task_id not in self.state.tasks:
            raise LookupError("Task not found")
        packets = [packet for packet in self.state.packets.values() if packet.task_id == task_id]
        return packets[:limit]


class FakeEventService:
    def __init__(self, state: WorkflowState) -> None:
        self.state = state

    def create_event(self, payload: ProjectEventCreate) -> ProjectEvent:
        if payload.task_id not in self.state.tasks:
            raise LookupError("Task not found")

        event = ProjectEvent(
            id=uuid4(),
            task_id=payload.task_id,
            event_type=payload.event_type,
            event_data=payload.event_data,
            created_at=datetime.now(timezone.utc),
        )
        self.state.events.append(event)
        return event

    def list_events(self, task_id: UUID, limit: int = 100) -> list[ProjectEvent]:
        return [event for event in self.state.events if event.task_id == task_id][:limit]


class FakeMemoryStore:
    def __init__(self, state: WorkflowState) -> None:
        self.state = state

    def list_project_events(self, task_id: UUID, limit: int = 50) -> list[ProjectEvent]:
        return [event for event in self.state.events if event.task_id == task_id][:limit]


class FakeContextService:
    def __init__(self, state: WorkflowState) -> None:
        self.state = state

    def lookup_memory(self, task_id: UUID, limit: int = 20) -> MemoryLookupResponse:
        task = self.state.tasks.get(task_id)
        if task is None:
            raise LookupError("Task not found")
        events = [event for event in self.state.events if event.task_id == task_id][:limit]
        packets = [packet for packet in self.state.packets.values() if packet.task_id == task_id]
        latest = packets[-1] if packets else None
        return MemoryLookupResponse(
            task_id=task_id,
            latest_baton_packet=latest,
            recent_events=events,
            event_count=len(events),
        )

    def assemble_context(self, task_id: UUID, event_limit: int = 20) -> ContextBundle:
        task = self.state.tasks.get(task_id)
        if task is None:
            raise LookupError("Task not found")
        events = [event for event in self.state.events if event.task_id == task_id][:event_limit]
        packets = [packet for packet in self.state.packets.values() if packet.task_id == task_id]
        latest = packets[-1] if packets else None
        return ContextBundle(
            task=task,
            latest_baton_packet=latest,
            recent_events=events,
            objective=latest.payload.objective if latest else None,
            completed_work=latest.payload.completed_work if latest else [],
            constraints=latest.payload.constraints if latest else [],
            open_issues=latest.payload.open_questions if latest else [],
            next_best_action=latest.payload.next_best_action if latest else None,
            relevant_artifacts=latest.payload.relevant_artifacts if latest else [],
        )

    def assemble_optimized_context(
        self,
        *,
        task_id: UUID,
        target_agent: str,
        target_model: str,
        token_budget: int,
    ) -> OptimizedContextBundle:
        task = self.state.tasks.get(task_id)
        if task is None:
            raise LookupError("Task not found")

        packets = [packet for packet in self.state.packets.values() if packet.task_id == task_id]
        latest = packets[-1] if packets else None
        summary = latest.payload.next_best_action if latest else "No baton payload available"
        section = ContextSection(
            section_id=f"optimized-{task_id}",
            title="Optimized Context",
            section_type="summary",
            content=summary,
            source="fake-context-service",
            priority=80,
        )
        return OptimizedContextBundle(
            task_id=task_id,
            target_agent=target_agent,
            target_model=target_model,
            token_budget=token_budget,
            estimated_token_count=max(1, len(summary) // 4),
            optimized_context={"rendered_prompt": summary},
            sections=[section],
            included_refs=[],
        )

    def retrieve_context_reference(self, ref_id: str) -> ContextReference:
        reference = self.state.context_references.get(ref_id)
        if reference is None:
            raise LookupError("Context reference not found")
        return reference


def build_client() -> TestClient:
    state = WorkflowState()
    app = create_app()
    app.dependency_overrides[get_task_service] = lambda: FakeTaskService(state)
    app.dependency_overrides[get_agent_run_service] = lambda: FakeAgentRunService(state)
    app.dependency_overrides[get_baton_service] = lambda: FakeBatonService(state)
    app.dependency_overrides[get_event_service] = lambda: FakeEventService(state)
    app.dependency_overrides[get_memory_store] = lambda: FakeMemoryStore(state)
    app.dependency_overrides[get_memory_lookup_service] = lambda: FakeContextService(state)
    app.dependency_overrides[get_context_bundle_service] = lambda: FakeContextService(state)
    return TestClient(app)


def test_api_happy_path_task_create_and_fetch() -> None:
    client = build_client()

    create_response = client.post(
        "/tasks",
        json={"title": "Validate local prototype", "task_type": "analysis", "complexity": "medium"},
    )
    assert create_response.status_code == 201

    task_id = create_response.json()["id"]
    detail_response = client.get(f"/tasks/{task_id}")
    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["task"]["title"] == "Validate local prototype"
    assert payload["event_count"] == 0


def test_api_failure_paths_missing_task_and_invalid_baton() -> None:
    client = build_client()
    missing_id = str(uuid4())

    missing_task_response = client.get(f"/tasks/{missing_id}")
    assert missing_task_response.status_code == 404

    invalid_baton_response = client.post(
        "/baton-packets",
        json={
            "task_id": str(uuid4()),
            "from_agent": "planner",
            "summary": "handoff",
            "payload": {"objective": "Missing next action"},
        },
    )
    assert invalid_baton_response.status_code == 422


def test_digest_request_with_no_events_returns_empty_summary() -> None:
    client = build_client()
    task_response = client.post(
        "/tasks",
        json={"title": "Digest no events", "task_type": "analysis", "complexity": "low"},
    )
    task_id = task_response.json()["id"]

    digest_response = client.get(f"/analyst/digest/{task_id}")
    assert digest_response.status_code == 200
    digest = digest_response.json()
    assert digest["total_events"] == 0
    assert "No project activity" in digest["headline"]


def test_memory_lookup_and_context_assemble() -> None:
    client = build_client()
    task_response = client.post(
        "/tasks",
        json={"title": "Context task", "task_type": "analysis", "complexity": "medium"},
    )
    task_id = task_response.json()["id"]

    client.post(
        "/baton-packets",
        json={
            "task_id": task_id,
            "from_agent": "planner",
            "to_agent": "coder",
            "summary": "context handoff",
            "payload": {
                "objective": "Ship demo",
                "completed_work": ["Created task"],
                "constraints": ["local only"],
                "open_questions": ["none"],
                "next_best_action": "Continue coding",
                "relevant_artifacts": ["README.md"],
            },
        },
    )
    client.post(
        "/project-events",
        json={
            "task_id": task_id,
            "event_type": "analysis.started",
            "event_data": {"status": "in_progress"},
        },
    )

    lookup_response = client.post("/memory/lookup", json={"task_id": task_id, "limit": 10})
    assert lookup_response.status_code == 200
    lookup = lookup_response.json()
    assert lookup["task_id"] == task_id
    assert lookup["latest_baton_packet"] is not None

    context_response = client.get(f"/context/{task_id}")
    assert context_response.status_code == 200
    context_payload = context_response.json()
    assert context_payload["task"]["id"] == task_id
    assert context_payload["objective"] == "Ship demo"


def test_end_to_end_demo_workflow() -> None:
    client = build_client()

    task = client.post(
        "/tasks",
        json={"title": "Ship local MVP", "task_type": "implementation", "complexity": "high"},
    ).json()
    task_id = task["id"]

    run_one = client.post(
        "/agent-runs",
        json={
            "task_id": task_id,
            "role": "planner",
            "status": "running",
            "input_summary": "Start planning",
        },
    )
    assert run_one.status_code == 201

    event_one = client.post(
        "/project-events",
        json={
            "task_id": task_id,
            "event_type": "analysis.started",
            "event_data": {"status": "in_progress"},
        },
    )
    assert event_one.status_code == 201

    packet = client.post(
        "/baton-packets",
        json={
            "task_id": task_id,
            "from_agent": "planner",
            "to_agent": "coder",
            "summary": "handoff to coder",
            "payload": {
                "objective": "Build local loop",
                "completed_work": ["Plan drafted"],
                "constraints": ["No AWS"],
                "open_questions": ["Need reviewer signoff"],
                "next_best_action": "Implement task API",
                "relevant_artifacts": ["README.md"],
            },
        },
    )
    assert packet.status_code == 201

    packet_lookup = client.get(f"/baton-packets/{task_id}")
    assert packet_lookup.status_code == 200
    assert len(packet_lookup.json()) == 1

    run_two = client.post(
        "/agent-runs",
        json={
            "task_id": task_id,
            "role": "coder",
            "status": "running",
            "input_summary": "Implement routes",
        },
    )
    assert run_two.status_code == 201

    update_two = client.patch(
        f"/agent-runs/{run_two.json()['id']}",
        json={"status": "completed", "output_summary": "Routes implemented"},
    )
    assert update_two.status_code == 200

    client.post(
        "/project-events",
        json={
            "task_id": task_id,
            "event_type": "implementation.completed",
            "event_data": {"status": "completed"},
        },
    )

    route_response = client.post(
        "/routing/decide",
        json={"task_type": "review", "complexity": "medium", "requires_memory": True},
    )
    assert route_response.status_code == 200
    assert route_response.json()["worker_role"] == "analyst"

    detail = client.get(f"/tasks/{task_id}")
    assert detail.status_code == 200
    assert len(detail.json()["agent_runs"]) == 2
    assert len(detail.json()["baton_packets"]) == 1

    context = client.get(f"/context/{task_id}")
    assert context.status_code == 200
    assert context.json()["next_best_action"] == "Implement task API"

    digest = client.get(f"/analyst/digest/{task_id}")
    assert digest.status_code == 200
    assert digest.json()["total_events"] >= 2


def test_api_smoke_task_event_baton_context_and_digest() -> None:
    client = build_client()

    task_response = client.post(
        "/tasks",
        json={"title": "Smoke test task", "task_type": "implementation", "complexity": "medium"},
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    event_response = client.post(
        "/project-events",
        json={
            "task_id": task_id,
            "event_type": "analysis.started",
            "event_data": {"status": "in_progress"},
        },
    )
    assert event_response.status_code == 201

    baton_response = client.post(
        "/baton-packets",
        json={
            "task_id": task_id,
            "from_agent": "planner",
            "to_agent": "coder",
            "summary": "handoff",
            "payload": {
                "objective": "Ship smoke-test path",
                "completed_work": ["Created task", "Logged event"],
                "constraints": ["Keep local deterministic flow"],
                "open_questions": ["None"],
                "next_best_action": "Call /context/assemble",
                "relevant_artifacts": ["README.md"],
            },
        },
    )
    assert baton_response.status_code == 201

    context_response = client.post(
        "/context/assemble",
        json={
            "task_id": task_id,
            "target_agent": "coder",
            "target_model": "gpt-4.1-mini",
            "token_budget": 1600,
        },
    )
    assert context_response.status_code == 200
    context_payload = context_response.json()
    assert context_payload["task_id"] == task_id
    assert context_payload["estimated_token_count"] <= 1600

    digest_response = client.get(f"/analyst/digest/{task_id}")
    assert digest_response.status_code == 200
    assert digest_response.json()["total_events"] >= 1
