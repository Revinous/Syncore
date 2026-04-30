from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from packages.contracts.python.models import (
    AgentRun,
    AgentRunCreate,
    AgentRunUpdate,
    RunExecutionRequest,
    Task,
)

from app.context.schemas import OptimizedContextBundle
from app.services.run_execution_service import RunExecutionService


class FakeContextService:
    def __init__(self, *, task_id: UUID, included_refs: list[str] | None = None) -> None:
        self._task_id = task_id
        self._included_refs = included_refs or []
        self.called = False

    def assemble_optimized_context(
        self,
        *,
        task_id: UUID,
        target_agent: str,
        target_model: str,
        token_budget: int,
    ) -> OptimizedContextBundle:
        self.called = True
        assert task_id == self._task_id
        return OptimizedContextBundle(
            bundle_id=uuid4(),
            task_id=task_id,
            target_agent=target_agent,
            target_model=target_model,
            token_budget=token_budget,
            estimated_token_count=120,
            optimized_context={
                "rendered_prompt": "## Critical Constraints\nDO NOT remove failing tests.",
                "section_count": 1,
            },
            sections=[],
            included_refs=self._included_refs,
            warnings=["context compressed"],
            created_at=datetime.now(timezone.utc),
        )


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.last_prompt = ""
        self.should_fail = False

    def complete(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ):
        del model, system_prompt, max_output_tokens, temperature
        self.last_prompt = prompt
        if self.should_fail:
            raise RuntimeError("provider boom")
        return type(
            "ProviderResult", (), {"output_text": "model output", "finish_reason": "stop"}
        )()

    def stream(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ):
        del model, system_prompt, max_output_tokens, temperature
        self.last_prompt = prompt
        if self.should_fail:
            raise RuntimeError("provider boom")
        yield "chunk-a"
        yield "chunk-b"


@dataclass
class FakeStore:
    task_id: UUID
    runs: dict[UUID, AgentRun] = field(default_factory=dict)
    events: list[dict[str, str | int | float | bool | None]] = field(default_factory=list)
    context_refs: dict[str, dict[str, object]] = field(default_factory=dict)

    def create_agent_run(self, run: AgentRunCreate) -> AgentRun:
        now = datetime.now(timezone.utc)
        created = AgentRun(
            id=uuid4(),
            task_id=run.task_id,
            role=run.role,
            status=run.status,
            input_summary=run.input_summary,
            output_summary=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self.runs[created.id] = created
        return created

    def update_agent_run(self, run_id: UUID, update: AgentRunUpdate) -> AgentRun | None:
        existing = self.runs.get(run_id)
        if existing is None:
            return None
        updated = AgentRun(
            id=existing.id,
            task_id=existing.task_id,
            role=existing.role,
            status=update.status or existing.status,
            input_summary=existing.input_summary,
            output_summary=update.output_summary
            if update.output_summary is not None
            else existing.output_summary,
            error_message=update.error_message
            if update.error_message is not None
            else existing.error_message,
            created_at=existing.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.runs[run_id] = updated
        return updated

    def save_project_event(self, event) -> None:
        self.events.append(
            {
                "task_id": str(event.task_id),
                "event_type": event.event_type,
                **event.event_data,
            }
        )

    def upsert_context_reference(
        self,
        *,
        ref_id: str,
        task_id: UUID,
        content_type: str,
        original_content: str,
        summary: str,
        retrieval_hint: str,
    ) -> dict[str, object]:
        record: dict[str, object] = {
            "ref_id": ref_id,
            "task_id": task_id,
            "content_type": content_type,
            "original_content": original_content,
            "summary": summary,
            "retrieval_hint": retrieval_hint,
            "created_at": datetime.now(timezone.utc),
        }
        self.context_refs[ref_id] = record
        return record

    def get_context_reference(self, ref_id: str):
        return self.context_refs.get(ref_id)

    def get_task(self, task_id: UUID):
        now = datetime.now(timezone.utc)
        if task_id != self.task_id:
            return None
        return Task(
            id=task_id,
            title="fake task",
            status="in_progress",
            task_type="implementation",
            complexity="medium",
            workspace_id=None,
            created_at=now,
            updated_at=now,
        )

    def list_tasks(self, limit: int = 50, workspace_id=None):
        del workspace_id
        task = self.get_task(self.task_id)
        return [task] if task is not None else []

    def list_agent_runs(self, task_id: UUID | None = None, limit: int = 50):
        del limit
        rows = list(self.runs.values())
        if task_id is not None:
            rows = [row for row in rows if row.task_id == task_id]
        return rows


def _request(task_id: UUID) -> RunExecutionRequest:
    return RunExecutionRequest(
        task_id=task_id,
        prompt="Implement run endpoint with context compression",
        target_agent="coder",
        target_model="gpt-4.1-mini",
        provider="fake",
        token_budget=1600,
    )


def _service(task_id: UUID) -> tuple[RunExecutionService, FakeStore, FakeProvider]:
    store = FakeStore(task_id=task_id)
    provider = FakeProvider()
    context_service = FakeContextService(task_id=task_id)
    service = RunExecutionService(
        store=store,  # type: ignore[arg-type]
        context_service=context_service,  # type: ignore[arg-type]
        providers={"fake": provider},
        default_provider="fake",
        failover_enabled=True,
        fallback_order=["fake"],
        default_timeout_seconds=30,
        max_concurrent_runs_per_task=1,
        max_concurrent_runs_per_workspace=4,
    )
    return service, store, provider


def test_execute_uses_context_and_marks_run_completed() -> None:
    task_id = uuid4()
    store = FakeStore(task_id=task_id)
    provider = FakeProvider()
    context_service = FakeContextService(task_id=task_id, included_refs=["ctxref_abc123"])
    service = RunExecutionService(
        store=store,  # type: ignore[arg-type]
        context_service=context_service,  # type: ignore[arg-type]
        providers={"fake": provider},
        default_provider="fake",
        failover_enabled=True,
        fallback_order=["fake"],
        default_timeout_seconds=30,
        max_concurrent_runs_per_task=1,
        max_concurrent_runs_per_workspace=4,
    )

    payload = _request(task_id).model_copy(update={"provider": None})
    result = service.execute(payload)

    assert context_service.called is True
    assert "## Optimized Context" in provider.last_prompt
    assert "DO NOT remove failing tests." in provider.last_prompt
    assert result.status == "completed"
    assert result.included_refs == ["ctxref_abc123"]
    assert result.total_estimated_tokens >= result.estimated_input_tokens
    assert any(event["event_type"] == "run.started" for event in store.events)
    assert any(event["event_type"] == "run.completed" for event in store.events)
    assert any(event["event_type"] == "run.output.stored" for event in store.events)
    assert len(store.context_refs) >= 3


def test_execute_marks_failed_on_provider_error() -> None:
    task_id = uuid4()
    store = FakeStore(task_id=task_id)
    provider = FakeProvider()
    provider.should_fail = True
    context_service = FakeContextService(task_id=task_id)
    service = RunExecutionService(
        store=store,  # type: ignore[arg-type]
        context_service=context_service,  # type: ignore[arg-type]
        providers={"fake": provider},
        default_provider="fake",
        failover_enabled=True,
        fallback_order=["fake"],
        default_timeout_seconds=30,
        max_concurrent_runs_per_task=1,
        max_concurrent_runs_per_workspace=4,
    )

    with pytest.raises(RuntimeError):
        service.execute(_request(task_id))

    assert any(run.status == "failed" for run in store.runs.values())
    assert any(event["event_type"] == "run.failed" for event in store.events)


def test_stream_execute_emits_started_chunks_and_completed() -> None:
    task_id = uuid4()
    store = FakeStore(task_id=task_id)
    provider = FakeProvider()
    context_service = FakeContextService(task_id=task_id)
    service = RunExecutionService(
        store=store,  # type: ignore[arg-type]
        context_service=context_service,  # type: ignore[arg-type]
        providers={"fake": provider},
        default_provider="fake",
        failover_enabled=True,
        fallback_order=["fake"],
        default_timeout_seconds=30,
        max_concurrent_runs_per_task=1,
        max_concurrent_runs_per_workspace=4,
    )

    events = list(service.stream_execute(_request(task_id)))
    assert events[0].event == "started"
    assert any(event.event == "chunk" for event in events)
    assert events[-1].event == "completed"
    assert any(run.status == "completed" for run in store.runs.values())


def test_execute_failover_uses_secondary_provider() -> None:
    task_id = uuid4()
    store = FakeStore(task_id=task_id)
    primary = FakeProvider()
    primary.should_fail = True
    secondary = FakeProvider()
    context_service = FakeContextService(task_id=task_id)
    service = RunExecutionService(
        store=store,  # type: ignore[arg-type]
        context_service=context_service,  # type: ignore[arg-type]
        providers={"primary": primary, "secondary": secondary},
        default_provider="primary",
        failover_enabled=True,
        fallback_order=["secondary"],
        default_timeout_seconds=30,
        max_concurrent_runs_per_task=1,
        max_concurrent_runs_per_workspace=4,
    )

    result = service.execute(_request(task_id).model_copy(update={"provider": None}))
    assert result.status == "completed"
    assert result.provider == "secondary"


def test_execute_explicit_provider_disables_failover() -> None:
    task_id = uuid4()
    store = FakeStore(task_id=task_id)
    primary = FakeProvider()
    primary.should_fail = True
    secondary = FakeProvider()
    context_service = FakeContextService(task_id=task_id)
    service = RunExecutionService(
        store=store,  # type: ignore[arg-type]
        context_service=context_service,  # type: ignore[arg-type]
        providers={"primary": primary, "secondary": secondary},
        default_provider="primary",
        failover_enabled=True,
        fallback_order=["secondary"],
        default_timeout_seconds=30,
        max_concurrent_runs_per_task=1,
        max_concurrent_runs_per_workspace=4,
    )

    payload = _request(task_id).model_copy(update={"provider": "primary"})
    with pytest.raises(RuntimeError):
        service.execute(payload)


def test_workspace_policy_profile_blocks_disallowed_command(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path
    blocked = service._safe_run_workspace_command(  # type: ignore[attr-defined]
        root,
        "npm run build",
        policy=RunExecutionService.WORKSPACE_POLICY_PROFILES["strict"],
    )
    allowed = service._safe_run_workspace_command(  # type: ignore[attr-defined]
        root,
        "pytest -q",
        policy=RunExecutionService.WORKSPACE_POLICY_PROFILES["strict"],
    )

    assert blocked["status"] == "blocked"
    assert "not allowed" in str(blocked["output"]).lower()
    assert allowed["status"] in {"ok", "failed"}


def test_workspace_path_traversal_is_blocked(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()

    with pytest.raises(PermissionError):
        service._resolve_workspace_path(root, "../outside.txt")  # type: ignore[attr-defined]


def test_workspace_patch_requires_before_text(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    target = root / "main.py"
    target.write_text("print('hello')\n", encoding="utf-8")

    with pytest.raises(ValueError):
        service._safe_patch_with_diff(  # type: ignore[attr-defined]
            task_id=task_id,
            root=root,
            relative_path="main.py",
            before_text="missing_text",
            after_text="print('updated')",
        )


def test_workspace_preflight_fails_for_unconfigured_provider(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    result = service._workspace_preflight(  # type: ignore[attr-defined]
        root=root,
        provider_hint="openai",
    )
    assert result["status"] == "failed"
    assert "not configured" in result["reason"]


def test_workspace_verifier_rejects_empty_execution() -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    result = service._verify_workspace_execution(  # type: ignore[attr-defined]
        changed_files=[],
        command_results=[],
    )
    assert result["status"] == "failed"
