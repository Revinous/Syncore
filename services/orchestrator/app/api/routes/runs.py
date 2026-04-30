import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from packages.contracts.python.models import RunExecutionRequest, RunExecutionResponse
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services.run_execution_service import RunExecutionService
from app.services.run_queue_service import RunQueueService
from app.services.task_service import TaskService
from app.store_factory import build_memory_store

router = APIRouter(prefix="/runs", tags=["runs"])


class ProviderCapabilityResponse(BaseModel):
    provider: str
    supports_streaming: bool
    supports_system_prompt: bool
    supports_temperature: bool
    supports_max_tokens: bool
    model_hint: str


class QueueEnqueueRequest(BaseModel):
    run: RunExecutionRequest
    max_attempts: int = Field(default=3, ge=1, le=10)


class QueueEnqueueResponse(BaseModel):
    job_id: str
    task_id: str
    status: str
    attempt_count: int
    max_attempts: int


class QueueScanItem(BaseModel):
    job_id: str
    task_id: str
    status: str
    run_id: str | None = None
    note: str


class QueueScanResponse(BaseModel):
    processed: int
    results: list[QueueScanItem]


class WorkspaceRunRequest(BaseModel):
    run: RunExecutionRequest
    max_steps: int = Field(default=3, ge=1, le=8)
    policy_profile: str = Field(default="balanced")
    dry_run: bool = False
    require_approval: bool = False


class AutoRunExecutionRequest(BaseModel):
    task_id: UUID
    prompt: str = Field(min_length=1)
    target_agent: str = Field(min_length=1)
    token_budget: int = Field(default=8_000, ge=256, le=200_000)
    provider: str | None = None
    target_model: str | None = None
    idempotency_key: str | None = None
    agent_role: str = Field(default="coder", min_length=1)
    system_prompt: str | None = None
    max_output_tokens: int = Field(default=1_200, ge=64, le=64_000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)


def get_run_execution_service(settings: Settings = Depends(get_settings)) -> RunExecutionService:
    return RunExecutionService.from_settings(settings)


def get_run_queue_service(settings: Settings = Depends(get_settings)) -> RunQueueService:
    return RunQueueService.from_settings(settings)


def get_task_service(settings: Settings = Depends(get_settings)) -> TaskService:
    configured = {"local_echo"}
    hints = {"local_echo": "local_echo"}
    if (settings.openai_api_key or "").strip():
        configured.add("openai")
        hints["openai"] = "gpt-5.4"
    if (settings.anthropic_api_key or "").strip():
        configured.add("anthropic")
        hints["anthropic"] = "claude-3-7-sonnet-latest"
    if (settings.gemini_api_key or "").strip():
        configured.add("gemini")
        hints["gemini"] = "gemini-2.5-pro"
    return TaskService(
        build_memory_store(settings),
        configured_providers=configured,
        provider_model_hints=hints,
    )


@router.post("/execute", response_model=RunExecutionResponse)
def execute_run(
    payload: RunExecutionRequest,
    x_idempotency_key: str | None = Header(default=None),
    service: RunExecutionService = Depends(get_run_execution_service),
) -> RunExecutionResponse:
    try:
        effective_payload = payload
        if x_idempotency_key and not payload.idempotency_key:
            effective_payload = payload.model_copy(update={"idempotency_key": x_idempotency_key})
        return service.execute(effective_payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/execute-auto", response_model=RunExecutionResponse)
def execute_run_auto(
    payload: AutoRunExecutionRequest,
    x_idempotency_key: str | None = Header(default=None),
    run_service: RunExecutionService = Depends(get_run_execution_service),
    task_service: TaskService = Depends(get_task_service),
) -> RunExecutionResponse:
    try:
        preferred_provider, preferred_model = task_service.resolve_task_model_preference(
            payload.task_id
        )
        provider = (payload.provider or "").strip() or preferred_provider
        model = (payload.target_model or "").strip() or preferred_model
        resolved = RunExecutionRequest(
            task_id=payload.task_id,
            prompt=payload.prompt,
            target_agent=payload.target_agent,
            target_model=model,
            provider=provider,
            idempotency_key=payload.idempotency_key,
            agent_role=payload.agent_role,
            token_budget=payload.token_budget,
            system_prompt=payload.system_prompt,
            max_output_tokens=payload.max_output_tokens,
            temperature=payload.temperature,
            timeout_seconds=payload.timeout_seconds,
        )
        if x_idempotency_key and not resolved.idempotency_key:
            resolved = resolved.model_copy(update={"idempotency_key": x_idempotency_key})
        return run_service.execute(resolved)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/execute-workspace")
def execute_workspace_run(
    payload: WorkspaceRunRequest,
    x_idempotency_key: str | None = Header(default=None),
    service: RunExecutionService = Depends(get_run_execution_service),
):
    try:
        effective_payload = payload.run
        if x_idempotency_key and not payload.run.idempotency_key:
            effective_payload = payload.run.model_copy(
                update={"idempotency_key": x_idempotency_key}
            )
        return service.execute_workspace_loop(
            effective_payload,
            max_steps=payload.max_steps,
            policy_profile=payload.policy_profile,
            dry_run=payload.dry_run,
            require_approval=payload.require_approval,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/execute/stream")
def execute_run_stream(
    payload: RunExecutionRequest,
    x_idempotency_key: str | None = Header(default=None),
    service: RunExecutionService = Depends(get_run_execution_service),
) -> StreamingResponse:
    effective_payload = payload
    if x_idempotency_key and not payload.idempotency_key:
        effective_payload = payload.model_copy(update={"idempotency_key": x_idempotency_key})

    def event_stream():
        try:
            for event in service.stream_execute(effective_payload):
                event_name = event.event
                event_json = json.dumps(event.model_dump(mode="json"))
                yield f"event: {event_name}\ndata: {event_json}\n\n"
        except LookupError as error:
            payload_data = {"event": "error", "error": str(error)}
            yield f"event: error\ndata: {json.dumps(payload_data)}\n\n"
        except ValueError as error:
            payload_data = {"event": "error", "error": str(error)}
            yield f"event: error\ndata: {json.dumps(payload_data)}\n\n"
        except RuntimeError as error:
            payload_data = {"event": "error", "error": str(error)}
            yield f"event: error\ndata: {json.dumps(payload_data)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/providers", response_model=list[ProviderCapabilityResponse])
def list_provider_capabilities(
    service: RunExecutionService = Depends(get_run_execution_service),
) -> list[ProviderCapabilityResponse]:
    return [
        ProviderCapabilityResponse(**item.__dict__)
        for item in service.list_provider_capabilities()
    ]


@router.post("/queue/enqueue", response_model=QueueEnqueueResponse)
def enqueue_run_job(
    payload: QueueEnqueueRequest,
    service: RunQueueService = Depends(get_run_queue_service),
) -> QueueEnqueueResponse:
    row = service.enqueue(payload.run, max_attempts=payload.max_attempts)
    return QueueEnqueueResponse(
        job_id=str(row["job_id"]),
        task_id=str(row["task_id"]),
        status=str(row["status"]),
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
    )


@router.post("/queue/scan-once", response_model=QueueScanResponse)
def scan_run_queue_once(
    limit: int = Query(default=10, ge=1, le=100),
    service: RunQueueService = Depends(get_run_queue_service),
) -> QueueScanResponse:
    results = service.scan_once(limit=limit)
    return QueueScanResponse(
        processed=len(results),
        results=[
            QueueScanItem(
                job_id=result.job_id,
                task_id=str(result.task_id),
                status=result.status,
                run_id=str(result.run_id) if result.run_id else None,
                note=result.note,
            )
            for result in results
        ],
    )
