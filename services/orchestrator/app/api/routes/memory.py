from fastapi import APIRouter, Depends, HTTPException
from packages.contracts.python.models import MemoryLookupRequest, MemoryLookupResponse
from services.memory.store import MemoryStore

from app.config import Settings, get_settings
from app.services.context_service import ContextService

router = APIRouter(prefix="/memory", tags=["memory"])


def get_context_service(settings: Settings = Depends(get_settings)) -> ContextService:
    return ContextService(MemoryStore(settings.postgres_dsn))


@router.post("/lookup", response_model=MemoryLookupResponse)
def lookup_memory(
    payload: MemoryLookupRequest,
    service: ContextService = Depends(get_context_service),
) -> MemoryLookupResponse:
    try:
        return service.lookup_memory(task_id=payload.task_id, limit=payload.limit)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
