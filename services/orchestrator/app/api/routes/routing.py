from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from packages.contracts.python.models import RoutingDecision, RoutingRequest

from app.config import Settings, get_settings
from app.services.routing_service import RoutingService
from app.store_factory import build_memory_store

router = APIRouter(prefix="/routing", tags=["routing"])


def get_routing_service() -> RoutingService:
    return RoutingService()


@router.post("/decide", response_model=RoutingDecision)
def decide_next(
    payload: RoutingRequest,
    service: RoutingService = Depends(get_routing_service),
) -> RoutingDecision:
    return service.choose_next(payload)


@router.post("/next", response_model=RoutingDecision)
def choose_next(
    payload: RoutingRequest,
    service: RoutingService = Depends(get_routing_service),
) -> RoutingDecision:
    return service.choose_next(payload)


@router.post("/next-action", response_model=RoutingDecision)
def choose_next_action(
    payload: RoutingRequest,
    service: RoutingService = Depends(get_routing_service),
) -> RoutingDecision:
    return service.choose_next(payload)


@router.get("/task/{task_id}", response_model=RoutingDecision)
def get_task_routing(
    task_id: UUID,
    settings: Settings = Depends(get_settings),
    service: RoutingService = Depends(get_routing_service),
) -> RoutingDecision:
    store = build_memory_store(settings)
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    payload = RoutingRequest(
        task_type=task.task_type,
        complexity=task.complexity,
        requires_memory=store.count_project_events(task_id) > 0,
    )
    return service.choose_next(payload)
