from packages.contracts.python.models import RoutingDecision, RoutingRequest


class RoutingPolicy:
    TASK_TO_ROLE = {
        "analysis": "analyst",
        "review": "analyst",
        "implementation": "orchestrator",
        "integration": "orchestrator",
        "memory_retrieval": "memory",
        "memory_update": "memory",
    }

    COMPLEXITY_TO_TIER = {
        "low": "economy",
        "medium": "balanced",
        "high": "premium",
    }

    def decide(self, request: RoutingRequest) -> RoutingDecision:
        worker_role = self.TASK_TO_ROLE[request.task_type]
        model_tier = self.COMPLEXITY_TO_TIER[request.complexity]

        if request.requires_memory and worker_role != "memory":
            reasoning = (
                f"Selected {worker_role} for {request.task_type}; "
                "memory context is required and should be loaded first."
            )
        else:
            reasoning = (
                f"Selected {worker_role} for {request.task_type} at {model_tier} tier."
            )

        return RoutingDecision(
            worker_role=worker_role,
            model_tier=model_tier,
            reasoning=reasoning,
        )
