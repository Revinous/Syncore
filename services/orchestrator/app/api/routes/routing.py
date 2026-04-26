from fastapi import APIRouter, Depends
from packages.contracts.python.models import RoutingDecision, RoutingRequest

from app.services.routing_service import RoutingService

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
