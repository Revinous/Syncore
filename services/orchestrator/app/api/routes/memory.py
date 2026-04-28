from fastapi import APIRouter, Depends, HTTPException
from packages.contracts.python.models import MemoryLookupRequest, MemoryLookupResponse

from app.config import Settings, get_settings
from app.services.context_service import ContextService
from app.store_factory import build_memory_store

router = APIRouter(prefix="/memory", tags=["memory"])


def get_context_service(settings: Settings = Depends(get_settings)) -> ContextService:
    return ContextService(
        build_memory_store(settings),
        layering_enabled=settings.context_layering_enabled,
        layering_dual_mode=settings.context_layering_dual_mode,
        layering_fallback_threshold_pct=settings.context_layering_fallback_threshold_pct,
        layering_fallback_min_samples=settings.context_layering_fallback_min_samples,
    )


@router.post("/lookup", response_model=MemoryLookupResponse)
def lookup_memory(
    payload: MemoryLookupRequest,
    service: ContextService = Depends(get_context_service),
) -> MemoryLookupResponse:
    try:
        return service.lookup_memory(task_id=payload.task_id, limit=payload.limit)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
