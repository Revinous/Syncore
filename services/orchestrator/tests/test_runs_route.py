from datetime import datetime, timezone
from uuid import uuid4

from fastapi.responses import StreamingResponse
from packages.contracts.python.models import (
    RunExecutionRequest,
    RunExecutionResponse,
    RunStreamEvent,
)

from app.api.routes.runs import (
    QueueEnqueueRequest,
    enqueue_run_job,
    execute_run,
    execute_run_stream,
    list_provider_capabilities,
    scan_run_queue_once,
)
from app.runs.providers import ProviderCapabilities


class FakeRunExecutionService:
    def execute(self, payload: RunExecutionRequest) -> RunExecutionResponse:
        now = datetime.now(timezone.utc)
        return RunExecutionResponse(
            run_id=uuid4(),
            task_id=payload.task_id,
            status="completed",
            provider=payload.provider or "local_echo",
            target_agent=payload.target_agent,
            target_model=payload.target_model,
            output_text="fake execution output",
            estimated_input_tokens=120,
            estimated_output_tokens=30,
            total_estimated_tokens=150,
            optimized_bundle_id=uuid4(),
            included_refs=["ctxref_demo"],
            warnings=[],
            created_at=now,
            completed_at=now,
        )

    def stream_execute(self, payload: RunExecutionRequest):
        del payload
        yield RunStreamEvent(event="started", run_id=uuid4())
        yield RunStreamEvent(event="chunk", content="part-1")
        yield RunStreamEvent(event="completed", estimated_output_tokens=20)

    def list_provider_capabilities(self):
        return [
            ProviderCapabilities(
                provider="local_echo",
                supports_streaming=True,
                supports_system_prompt=True,
                supports_temperature=True,
                supports_max_tokens=True,
                model_hint="local_echo",
            )
        ]


class FakeRunQueueService:
    def enqueue(self, payload: RunExecutionRequest, max_attempts: int = 3):
        return {
            "job_id": "job-1",
            "task_id": str(payload.task_id),
            "status": "queued",
            "attempt_count": 0,
            "max_attempts": max_attempts,
        }

    def scan_once(self, limit: int = 10):
        del limit
        return []


def test_execute_run_route_function_returns_response() -> None:
    request = RunExecutionRequest(
        task_id=uuid4(),
        prompt="Review this patch",
        target_agent="reviewer",
        target_model="gpt-4.1-mini",
        provider="local_echo",
        token_budget=1200,
    )
    response = execute_run(request, service=FakeRunExecutionService())  # type: ignore[arg-type]
    assert response.status == "completed"
    assert response.output_text == "fake execution output"


def test_execute_run_stream_route_returns_streaming_response() -> None:
    request = RunExecutionRequest(
        task_id=uuid4(),
        prompt="Implement context optimizer",
        target_agent="coder",
        target_model="gpt-4.1-mini",
    )
    response = execute_run_stream(request, service=FakeRunExecutionService())  # type: ignore[arg-type]
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"


def test_list_provider_capabilities_route_returns_rows() -> None:
    payload = list_provider_capabilities(service=FakeRunExecutionService())  # type: ignore[arg-type]
    assert len(payload) == 1
    assert payload[0].provider == "local_echo"


def test_enqueue_run_job_route_returns_queue_row() -> None:
    request = RunExecutionRequest(
        task_id=uuid4(),
        prompt="Review this patch",
        target_agent="reviewer",
        target_model="gpt-4.1-mini",
    )
    response = enqueue_run_job(  # type: ignore[arg-type]
        payload=QueueEnqueueRequest(run=request, max_attempts=3),
        service=FakeRunQueueService(),
    )
    assert response.job_id == "job-1"
    assert response.status == "queued"


def test_scan_run_queue_once_route_returns_response() -> None:
    response = scan_run_queue_once(limit=10, service=FakeRunQueueService())  # type: ignore[arg-type]
    assert response.processed == 0
