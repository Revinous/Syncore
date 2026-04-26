from packages.contracts.python.models import RoutingDecision, RoutingRequest
from services.router.policy import RoutingPolicy


class RoutingService:
    def __init__(self, policy: RoutingPolicy | None = None) -> None:
        self._policy = policy or RoutingPolicy()

    def choose_next(self, payload: RoutingRequest) -> RoutingDecision:
        return self._policy.decide(payload)
