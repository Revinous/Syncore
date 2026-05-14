import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from packages.contracts.python.models import RunExecutionRequest, RunExecutionResponse

from app.api.routes.run_models import (
    AutoRunExecutionRequest,
    ProviderCapabilityResponse,
    QueueEnqueueRequest,
    QueueEnqueueResponse,
    QueueScanItem,
    QueueScanResponse,
    WorkspaceRunRequest,
)
from app.config import Settings, get_settings
from app.services.run_execution_service import RunExecutionService
from app.services.run_queue_service import RunQueueService
from app.services.run_route_services import (
    build_run_execution_service,
    build_run_queue_service,
    build_task_service,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/runs", tags=["runs"])


def get_run_execution_service(settings: Settings = Depends(get_settings)) -> RunExecutionService:
    return build_run_execution_service(settings)


def get_run_queue_service(settings: Settings = Depends(get_settings)) -> RunQueueService:
    return build_run_queue_service(settings)


def get_task_service(settings: Settings = Depends(get_settings)) -> TaskService:
    return build_task_service(settings)


def _handle_execute_errors(error: Exception) -> HTTPException:
    if isinstance(error, LookupError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ValueError):
        return HTTPException(status_code=400, detail=str(error))
    if isinstance(error, RuntimeError):
        return HTTPException(status_code=502, detail=str(error))
    return HTTPException(status_code=500, detail=str(error))


def _with_idempotency(
    payload: RunExecutionRequest, header_value: str | None
) -> RunExecutionRequest:
    if header_value and not payload.idempotency_key:
        return payload.model_copy(update={"idempotency_key": header_value})
    return payload


@router.post("/execute", response_model=RunExecutionResponse)
def execute_run(
    payload: RunExecutionRequest,
    x_idempotency_key: str | None = Header(default=None),
    service: RunExecutionService = Depends(get_run_execution_service),
) -> RunExecutionResponse:
    try:
        return service.execute(_with_idempotency(payload, x_idempotency_key))
    except (LookupError, ValueError, RuntimeError) as error:
        raise _handle_execute_errors(error) from error


@router.post("/execute-auto", response_model=RunExecutionResponse)
def execute_run_auto(
    payload: AutoRunExecutionRequest,
    x_idempotency_key: str | None = Header(default=None),
    run_service: RunExecutionService = Depends(get_run_execution_service),
    task_service: TaskService = Depends(get_task_service),
) -> RunExecutionResponse:
    try:
        preferred_provider, preferred_model = task_service.resolve_task_model_preference(
            payload.task_id,
            stage=payload.stage,
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
        return run_service.execute(_with_idempotency(resolved, x_idempotency_key))
    except (LookupError, ValueError, RuntimeError) as error:
        raise _handle_execute_errors(error) from error


@router.post("/execute-workspace")
def execute_workspace_run(
    payload: WorkspaceRunRequest,
    x_idempotency_key: str | None = Header(default=None),
    service: RunExecutionService = Depends(get_run_execution_service),
):
    try:
        return service.execute_workspace_loop(
            _with_idempotency(payload.run, x_idempotency_key),
            max_steps=payload.max_steps,
            policy_profile=payload.policy_profile,
            dry_run=payload.dry_run,
            require_approval=payload.require_approval,
        )
    except (LookupError, ValueError, RuntimeError) as error:
        raise _handle_execute_errors(error) from error


@router.post("/execute/stream")
def execute_run_stream(
    payload: RunExecutionRequest,
    x_idempotency_key: str | None = Header(default=None),
    service: RunExecutionService = Depends(get_run_execution_service),
) -> StreamingResponse:
    effective_payload = _with_idempotency(payload, x_idempotency_key)

    def event_stream():
        try:
            for event in service.stream_execute(effective_payload):
                event_name = event.event
                event_json = json.dumps(event.model_dump(mode="json"))
                yield f"event: {event_name}\ndata: {event_json}\n\n"
        except (LookupError, ValueError, RuntimeError) as error:
            payload_data = {"event": "error", "error": str(error)}
            yield f"event: error\ndata: {json.dumps(payload_data)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/providers", response_model=list[ProviderCapabilityResponse])
def list_provider_capabilities(
    service: RunExecutionService = Depends(get_run_execution_service),
) -> list[ProviderCapabilityResponse]:
    return [
        ProviderCapabilityResponse(**item.__dict__) for item in service.list_provider_capabilities()
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
