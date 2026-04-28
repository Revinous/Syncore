from datetime import datetime
from uuid import UUID

from packages.contracts.python.models import ContextBundle, MemoryLookupResponse
from services.memory import MemoryStoreProtocol

from app.context.assembler import ContextAssembler
from app.context.compression_policy import default_context_policy
from app.context.optimizer import ContextOptimizer, SimpleContextOptimizer
from app.context.pricing import estimate_input_cost_usd
from app.context.schemas import ContextReference, OptimizedContextBundle


class ContextService:
    _layering_profile_cache: dict[str, str] = {}

    def __init__(
        self,
        store: MemoryStoreProtocol,
        assembler: ContextAssembler | None = None,
        optimizer: ContextOptimizer | None = None,
        *,
        layering_enabled: bool = False,
        layering_dual_mode: bool = False,
        layering_fallback_threshold_pct: float = 2.0,
        layering_fallback_min_samples: int = 5,
    ) -> None:
        self._store = store
        self._assembler = assembler or ContextAssembler(store)
        self._optimizer = optimizer or SimpleContextOptimizer(store)
        self._layering_enabled = layering_enabled
        self._layering_dual_mode = layering_dual_mode
        self._layering_fallback_threshold_pct = max(layering_fallback_threshold_pct, 0.1)
        self._layering_fallback_min_samples = max(layering_fallback_min_samples, 1)

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
        task = self._store.get_task(task_id)
        if task is None:
            raise LookupError("Task not found")

        profile_key = (
            f"{task.task_type}|{task.complexity}|{target_model.strip().lower()}|"
            f"{target_agent.strip().lower()}"
        )
        raw_bundle = self._assembler.assemble(
            task_id=task_id,
            target_agent=target_agent,
            target_model=target_model,
            token_budget=token_budget,
        )
        use_layering = self._resolve_layering_mode(profile_key=profile_key)
        policy = default_context_policy(
            token_budget=token_budget,
            layering_enabled=use_layering,
        )
        optimized = self._optimizer.optimize(raw_bundle, policy=policy)

        legacy_tokens: int | None = None
        layered_tokens: int | None = None
        if use_layering and self._layering_dual_mode:
            legacy_policy = default_context_policy(
                token_budget=token_budget,
                layering_enabled=False,
            )
            legacy_bundle = self._optimizer.optimize(raw_bundle, policy=legacy_policy)
            legacy_tokens = legacy_bundle.estimated_token_count
            layered_tokens = optimized.estimated_token_count
            optimized.optimized_context["layering_comparison"] = {
                "legacy_estimated_tokens": legacy_tokens,
                "layered_estimated_tokens": layered_tokens,
                "estimated_token_delta": legacy_tokens - layered_tokens,
            }
            optimized.optimized_context["layering_mode"] = "dual"
        elif use_layering:
            optimized.optimized_context["layering_mode"] = "layered"
        else:
            optimized.optimized_context["layering_mode"] = (
                "legacy_fallback" if self._layering_enabled else "legacy"
            )
        optimized.optimized_context["rollout_profile"] = profile_key
        cost_raw = estimate_input_cost_usd(
            model=target_model, input_tokens=optimized.raw_estimated_token_count
        )
        cost_optimized = estimate_input_cost_usd(
            model=target_model, input_tokens=optimized.estimated_token_count
        )
        cost_saved = None
        if cost_raw is not None and cost_optimized is not None:
            cost_saved = round(cost_raw - cost_optimized, 8)
        row = self._store.save_context_bundle(
            task_id=task_id,
            target_agent=target_agent,
            target_model=target_model,
            token_budget=token_budget,
            raw_estimated_tokens=optimized.raw_estimated_token_count,
            optimized_estimated_tokens=optimized.estimated_token_count,
            token_savings_estimate=optimized.token_savings_estimate,
            token_savings_pct=optimized.token_savings_pct,
            estimated_cost_raw_usd=cost_raw,
            estimated_cost_optimized_usd=cost_optimized,
            estimated_cost_saved_usd=cost_saved,
            optimized_context=optimized.optimized_context,
            included_refs=optimized.included_refs,
        )
        return optimized.model_copy(
            update={
                "bundle_id": self._as_uuid(row["bundle_id"]),
                "created_at": self._as_datetime(row["created_at"]),
                "included_refs": list(row["included_refs"]),
                "estimated_cost_raw_usd": row.get("estimated_cost_raw_usd"),
                "estimated_cost_optimized_usd": row.get("estimated_cost_optimized_usd"),
                "estimated_cost_saved_usd": row.get("estimated_cost_saved_usd"),
            }
        )

    def _resolve_layering_mode(self, *, profile_key: str) -> bool:
        if not self._layering_enabled:
            return False
        cached = self._layering_profile_cache.get(profile_key)
        if cached == "legacy_fallback":
            return False
        if cached == "layered":
            return True

        rows = self._store.list_recent_context_bundles(limit=500)
        deltas: list[float] = []
        for row in rows:
            optimized_context = row.get("optimized_context")
            if not isinstance(optimized_context, dict):
                continue
            if str(optimized_context.get("rollout_profile") or "") != profile_key:
                continue
            comparison = optimized_context.get("layering_comparison")
            if not isinstance(comparison, dict):
                continue
            legacy = comparison.get("legacy_estimated_tokens")
            layered = comparison.get("layered_estimated_tokens")
            if not isinstance(legacy, int) or not isinstance(layered, int) or legacy <= 0:
                continue
            deltas.append(((layered - legacy) / legacy) * 100.0)

        if len(deltas) >= self._layering_fallback_min_samples:
            avg_delta = sum(deltas) / len(deltas)
            if avg_delta > self._layering_fallback_threshold_pct:
                self._layering_profile_cache[profile_key] = "legacy_fallback"
                return False
            self._layering_profile_cache[profile_key] = "layered"
            return True

        return True

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
