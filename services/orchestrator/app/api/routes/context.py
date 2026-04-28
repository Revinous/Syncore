from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from packages.contracts.python.models import ContextBundle

from app.config import Settings, get_settings
from app.context.schemas import (
    ContextAssembleOptimizedRequest,
    ContextReference,
    OptimizedContextBundle,
)
from app.services.context_service import ContextService
from app.store_factory import build_memory_store

router = APIRouter(prefix="/context", tags=["context"])


def get_context_service(settings: Settings = Depends(get_settings)) -> ContextService:
    return ContextService(
        build_memory_store(settings),
        layering_enabled=settings.context_layering_enabled,
        layering_dual_mode=settings.context_layering_dual_mode,
    )


@router.get("/{task_id}", response_model=ContextBundle)
def get_context_bundle(
    task_id: UUID,
    event_limit: int = Query(default=20, ge=1, le=200),
    service: ContextService = Depends(get_context_service),
) -> ContextBundle:
    try:
        return service.assemble_context(task_id=task_id, event_limit=event_limit)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/assemble", response_model=OptimizedContextBundle)
def assemble_context_bundle(
    payload: ContextAssembleOptimizedRequest,
    service: ContextService = Depends(get_context_service),
) -> OptimizedContextBundle:
    try:
        return service.assemble_optimized_context(
            task_id=payload.task_id,
            target_agent=payload.target_agent,
            target_model=payload.target_model,
            token_budget=payload.token_budget,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/references/{ref_id}", response_model=ContextReference)
def get_context_reference(
    ref_id: str,
    service: ContextService = Depends(get_context_service),
) -> ContextReference:
    try:
        return service.retrieve_context_reference(ref_id=ref_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
