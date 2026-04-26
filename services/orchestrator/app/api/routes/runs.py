import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from packages.contracts.python.models import RunExecutionRequest, RunExecutionResponse

from app.config import Settings, get_settings
from app.services.run_execution_service import RunExecutionService

router = APIRouter(prefix="/runs", tags=["runs"])


def get_run_execution_service(settings: Settings = Depends(get_settings)) -> RunExecutionService:
    return RunExecutionService.from_settings(settings)


@router.post("/execute", response_model=RunExecutionResponse)
def execute_run(
    payload: RunExecutionRequest,
    service: RunExecutionService = Depends(get_run_execution_service),
) -> RunExecutionResponse:
    try:
        return service.execute(payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/execute/stream")
def execute_run_stream(
    payload: RunExecutionRequest,
    service: RunExecutionService = Depends(get_run_execution_service),
) -> StreamingResponse:
    def event_stream():
        try:
            for event in service.stream_execute(payload):
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
