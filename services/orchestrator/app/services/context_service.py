from datetime import datetime
from uuid import UUID

from packages.contracts.python.models import ContextBundle, MemoryLookupResponse
from services.memory import MemoryStoreProtocol

from app.context.assembler import ContextAssembler
from app.context.compression_policy import default_context_policy
from app.context.optimizer import ContextOptimizer, SimpleContextOptimizer
from app.context.schemas import ContextReference, OptimizedContextBundle


class ContextService:
    def __init__(
        self,
        store: MemoryStoreProtocol,
        assembler: ContextAssembler | None = None,
        optimizer: ContextOptimizer | None = None,
    ) -> None:
        self._store = store
        self._assembler = assembler or ContextAssembler(store)
        self._optimizer = optimizer or SimpleContextOptimizer(store)

    def lookup_memory(self, task_id: UUID, limit: int = 20) -> MemoryLookupResponse:
        task = self._store.get_task(task_id)
        if task is None:
            raise LookupError("Task not found")

        events = self._store.list_project_events(task_id=task_id, limit=limit)
        latest_packet = self._store.get_latest_baton_packet(task_id=task_id)

        return MemoryLookupResponse(
            task_id=task_id,
            latest_baton_packet=latest_packet,
            recent_events=events,
            event_count=len(events),
        )

    def assemble_context(self, task_id: UUID, event_limit: int = 20) -> ContextBundle:
        task = self._store.get_task(task_id)
        if task is None:
            raise LookupError("Task not found")

        events = self._store.list_project_events(task_id=task_id, limit=event_limit)
        latest_packet = self._store.get_latest_baton_packet(task_id=task_id)

        objective: str | None = None
        completed_work: list[str] = []
        constraints: list[str] = []
        open_issues: list[str] = []
        next_best_action: str | None = None
        relevant_artifacts: list[str] = []

        if latest_packet is not None:
            objective = latest_packet.payload.objective
            completed_work = latest_packet.payload.completed_work
            constraints = latest_packet.payload.constraints
            open_issues = latest_packet.payload.open_questions
            next_best_action = latest_packet.payload.next_best_action
            relevant_artifacts = latest_packet.payload.relevant_artifacts

        return ContextBundle(
            task=task,
            latest_baton_packet=latest_packet,
            recent_events=events,
            objective=objective,
            completed_work=completed_work,
            constraints=constraints,
            open_issues=open_issues,
            next_best_action=next_best_action,
            relevant_artifacts=relevant_artifacts,
        )

    def assemble_optimized_context(
        self,
        *,
        task_id: UUID,
        target_agent: str,
        target_model: str,
        token_budget: int,
    ) -> OptimizedContextBundle:
        raw_bundle = self._assembler.assemble(
            task_id=task_id,
            target_agent=target_agent,
            target_model=target_model,
            token_budget=token_budget,
        )
        policy = default_context_policy(token_budget=token_budget)
        optimized = self._optimizer.optimize(raw_bundle, policy=policy)
        row = self._store.save_context_bundle(
            task_id=task_id,
            target_agent=target_agent,
            target_model=target_model,
            token_budget=token_budget,
            optimized_context=optimized.optimized_context,
            included_refs=optimized.included_refs,
        )
        return optimized.model_copy(
            update={
                "bundle_id": self._as_uuid(row["bundle_id"]),
                "created_at": self._as_datetime(row["created_at"]),
                "included_refs": list(row["included_refs"]),
            }
        )

    def retrieve_context_reference(self, ref_id: str) -> ContextReference:
        return self._optimizer.retrieve(ref_id)

    def _as_uuid(self, value: object) -> UUID:
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            return UUID(value)
        raise ValueError(f"Unsupported bundle_id type: {type(value)}")

    def _as_datetime(self, value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        raise ValueError(f"Unsupported datetime type: {type(value)}")
