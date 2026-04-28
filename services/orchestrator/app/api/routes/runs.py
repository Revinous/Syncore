import json

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from packages.contracts.python.models import RunExecutionRequest, RunExecutionResponse
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.services.run_execution_service import RunExecutionService

router = APIRouter(prefix="/runs", tags=["runs"])


class ProviderCapabilityResponse(BaseModel):
    provider: str
    supports_streaming: bool
    supports_system_prompt: bool
    supports_temperature: bool
    supports_max_tokens: bool
    model_hint: str


def get_run_execution_service(settings: Settings = Depends(get_settings)) -> RunExecutionService:
    return RunExecutionService.from_settings(settings)


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
