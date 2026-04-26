from datetime import datetime, timezone
from uuid import uuid4

from fastapi.responses import StreamingResponse
from packages.contracts.python.models import (
    RunExecutionRequest,
    RunExecutionResponse,
    RunStreamEvent,
)

from app.api.routes.runs import execute_run, execute_run_stream


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
