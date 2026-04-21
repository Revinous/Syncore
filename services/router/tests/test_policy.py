from packages.contracts.python.models import RoutingRequest
from services.router.policy import RoutingPolicy


def test_analysis_routes_to_analyst_with_economy_tier() -> None:
    policy = RoutingPolicy()

    decision = policy.decide(RoutingRequest(task_type="analysis", complexity="low"))

    assert decision.worker_role == "analyst"
    assert decision.model_tier == "economy"


def test_implementation_routes_to_orchestrator_with_premium_tier() -> None:
    policy = RoutingPolicy()

    decision = policy.decide(
        RoutingRequest(task_type="implementation", complexity="high")
    )

    assert decision.worker_role == "orchestrator"
    assert decision.model_tier == "premium"


def test_memory_task_routes_to_memory_worker() -> None:
    policy = RoutingPolicy()

    decision = policy.decide(
        RoutingRequest(task_type="memory_retrieval", complexity="medium")
    )

    assert decision.worker_role == "memory"
    assert decision.model_tier == "balanced"


def test_requires_memory_adds_reasoning_hint() -> None:
    policy = RoutingPolicy()

    decision = policy.decide(
        RoutingRequest(task_type="review", complexity="medium", requires_memory=True)
    )

    assert "memory context is required" in decision.reasoning
