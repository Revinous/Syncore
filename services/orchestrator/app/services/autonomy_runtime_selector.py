from __future__ import annotations

from packages.contracts.python.models import ProjectEventCreate, Task
from services.memory import MemoryStoreProtocol


class AutonomyRuntimeSelector:
    def __init__(
        self,
        *,
        store: MemoryStoreProtocol,
        run_execution_service,
        default_provider: str,
        default_model: str,
        max_provider_switches: int,
        parse_positive_int,
        latest_event,
        event_int,
        event_bool,
    ) -> None:
        self._store = store
        self._run_execution_service = run_execution_service
        self._default_provider = default_provider
        self._default_model = default_model
        self._max_provider_switches = max_provider_switches
        self._parse_positive_int = parse_positive_int
        self._latest_event = latest_event
        self._event_int = event_int
        self._event_bool = event_bool
    def resolve_provider(
        self,
        *,
        stage: str,
        task: Task,
        prefs: dict[str, str],
        previous_provider: str | None = None,
    ) -> str | None:
        capability_rows = self._run_execution_service.list_provider_capabilities()
        if not capability_rows:
            return None
        available = [item.provider for item in capability_rows]
        policy = self.model_policy(prefs)
        explicit_stage = str(prefs.get(f"preferred_provider_{stage}") or "").strip().lower()
        explicit_default = str(prefs.get("preferred_provider") or "").strip().lower()
        if not policy["allow_cross_provider_switching"] and previous_provider in available:
            return previous_provider
        preferred = (
            explicit_stage
            if explicit_stage and explicit_stage in available
            else explicit_default if explicit_default and explicit_default in available else ""
        )
        if preferred:
            return self.failure_aware_provider_choice(
                task=task,
                preferred=preferred,
                available=available,
            )
        if (
            self._default_provider
            and self._default_provider not in available
            and not explicit_stage
            and not explicit_default
        ):
            return self._default_provider
        if self._default_provider == "local_echo" and "local_echo" in available:
            return "local_echo"
        ordered = self.stage_provider_order(
            stage=stage,
            available=available,
            prefs=prefs,
        )
        recent_failures = self.recent_provider_failures(task.id)
        scored: list[tuple[float, str]] = []
        for item in capability_rows:
            if item.provider not in ordered:
                continue
            score = self.provider_score(
                stage=stage,
                task=task,
                provider=item.provider,
                capability=item,
                policy=policy,
                prefs=prefs,
                previous_provider=previous_provider,
                explicit_stage=explicit_stage,
                explicit_default=explicit_default,
                recent_failures=recent_failures,
            )
            scored.append((score, item.provider))
        scored.sort(key=lambda entry: entry[0], reverse=True)
        if not scored:
            return ordered[0] if ordered else None
        return scored[0][1]
    def resolve_model(
        self,
        *,
        stage: str,
        task: Task,
        provider: str | None,
        prefs: dict[str, str],
    ) -> str:
        preferred_model = (
            prefs.get(f"preferred_model_{stage}")
            or prefs.get("preferred_model")
            or self.workspace_learning_value(task=task, key="last_successful_model")
            or ""
        ).strip()
        if preferred_model:
            return preferred_model
        if provider == "local_echo" or self._default_provider == "local_echo":
            return "local_echo"
        capability_map = {
            item.provider: item.model_hint
            for item in self._run_execution_service.list_provider_capabilities()
        }
        hinted = str(capability_map.get(provider or "") or "").strip()
        if stage == "review" and provider == "anthropic" and hinted:
            return hinted
        if stage == "plan" and hinted:
            return hinted
        if stage == "execute" and task.complexity == "high" and hinted:
            return hinted
        return hinted or self._default_model
    def model_policy(self, prefs: dict[str, str]) -> dict[str, object]:
        return {
            "optimization_goal": str(prefs.get("model_optimization_goal") or "balanced")
            .strip()
            .lower(),
            "allow_cross_provider_switching": str(
                prefs.get("allow_cross_provider_switching") or "true"
            )
            .strip()
            .lower()
            != "false",
            "maintain_context_continuity": str(prefs.get("maintain_context_continuity") or "true")
            .strip()
            .lower()
            != "false",
            "minimum_context_window": self._parse_positive_int(
                prefs.get("minimum_context_window"),
                default=0,
                maximum=2_000_000,
            ),
            "max_latency_tier": str(prefs.get("max_latency_tier") or "").strip().lower(),
            "max_cost_tier": str(prefs.get("max_cost_tier") or "").strip().lower(),
            "prefer_reviewer_provider": str(prefs.get("prefer_reviewer_provider") or "true")
            .strip()
            .lower()
            != "false",
        }
    def resolve_autonomy_mode(self, *, task: Task, prefs: dict[str, str]) -> tuple[str, str]:
        preferred = str(prefs.get("autonomy_mode") or "").strip().lower()
        requested = preferred or ""
        if task.workspace_id is None:
            return (requested or "supervised"), ""
        workspace = self._store.get_workspace(task.workspace_id)
        if workspace is None:
            return (requested or "supervised"), ""
        readiness = dict(workspace.metadata.get("workspace_readiness") or {})
        recommended = str(readiness.get("recommended_autonomy_mode") or "").strip().lower()
        score = int(readiness.get("score") or 0)
        if not requested:
            return (recommended or "supervised"), ""
        if requested == "unattended" and score < 85:
            fallback = recommended or "supervised"
            return (
                fallback,
                (
                    "Requested unattended mode was downgraded because workspace readiness "
                    f"score is {score}."
                ),
            )
        return requested, ""
    def workspace_learning_value(self, *, task: Task, key: str) -> str:
        workspace = self._store.get_workspace(task.workspace_id) if task.workspace_id else None
        if workspace is None:
            return ""
        value = dict(workspace.metadata.get("learning") or {}).get(key)
        return str(value).strip() if value is not None else ""
    def failure_aware_provider_choice(
        self,
        *,
        task: Task,
        preferred: str,
        available: list[str] | None = None,
    ) -> str:
        if available is None:
            capabilities = self._run_execution_service.list_provider_capabilities()
            available = [item.provider for item in capabilities]
        if preferred not in available:
            return available[0] if available else preferred
        recent_failures = self.recent_provider_failures(task.id)
        if recent_failures.get(preferred, 0) < 2:
            return preferred
        for provider in available:
            if provider == preferred:
                continue
            if recent_failures.get(provider, 0) == 0:
                return provider
        return preferred
    def recent_provider_failures(self, task_id) -> dict[str, int]:
        failures: dict[str, int] = {}
        for event in reversed(self._store.list_project_events(task_id=task_id, limit=100)[-30:]):
            if event.event_type not in {
                "run.failed",
                "workspace.execution.preflight.failed",
                "workspace.execution.verification.failed",
            }:
                continue
            category = str(event.event_data.get("failure_category") or "")
            if event.event_type == "run.failed" or category == "provider_failure":
                provider = str(event.event_data.get("provider") or "").strip().lower()
                if provider:
                    failures[provider] = failures.get(provider, 0) + 1
        return failures
    def provider_score(
        self,
        *,
        stage: str,
        task: Task,
        provider: str,
        capability,
        policy: dict[str, object],
        prefs: dict[str, str],
        previous_provider: str | None,
        explicit_stage: str,
        explicit_default: str,
        recent_failures: dict[str, int],
    ) -> float:
        del prefs
        score = 0.0
        optimization_goal = str(policy["optimization_goal"] or "balanced")
        minimum_context_window_raw = policy["minimum_context_window"]
        if isinstance(minimum_context_window_raw, bool):
            minimum_context_window = int(minimum_context_window_raw)
        elif isinstance(minimum_context_window_raw, (int, float)):
            minimum_context_window = int(minimum_context_window_raw)
        elif isinstance(minimum_context_window_raw, str):
            try:
                minimum_context_window = int(minimum_context_window_raw)
            except ValueError:
                minimum_context_window = 0
        else:
            minimum_context_window = 0
        max_latency_tier = str(policy["max_latency_tier"] or "")
        max_cost_tier = str(policy["max_cost_tier"] or "")
        if capability.max_context_tokens < minimum_context_window:
            return -10_000.0
        latency_floor = {"slow": 1, "balanced": 2, "fast": 3}.get(max_latency_tier, 0)
        cost_ceiling = {"low": 2, "medium": 3, "high": 5}.get(max_cost_tier, 5)
        if max_latency_tier and capability.speed_tier < latency_floor:
            return -5_000.0
        if max_cost_tier and capability.cost_tier > cost_ceiling:
            return -5_000.0
        if explicit_stage and provider == explicit_stage:
            score += 200
        elif explicit_default and provider == explicit_default:
            score += 120
        if (
            previous_provider
            and provider == previous_provider
            and bool(policy["maintain_context_continuity"])
        ):
            score += 40
        if (
            previous_provider
            and provider != previous_provider
            and not bool(policy["allow_cross_provider_switching"])
        ):
            score -= 200
        if provider == self.workspace_learning_value(task=task, key="last_successful_provider"):
            score += 24
        complexity = str(getattr(task, "complexity", "") or "").strip().lower()
        task_type = str(getattr(task, "task_type", "") or "").strip().lower()
        score += capability.quality_tier * 6 if complexity == "high" else 0
        score += capability.speed_tier * 4 if complexity == "low" else 0
        if task_type in {"research", "analysis"}:
            score += capability.max_context_tokens / 100_000
        if (
            stage == "review"
            and bool(policy["prefer_reviewer_provider"])
            and provider == "anthropic"
        ):
            score += 35
        if optimization_goal == "quality":
            score += capability.quality_tier * 14
        elif optimization_goal == "speed":
            score += capability.speed_tier * 14
        elif optimization_goal == "cost":
            score += (6 - capability.cost_tier) * 14
        elif optimization_goal == "context":
            score += capability.max_context_tokens / 10_000
        else:
            score += capability.quality_tier * 6
            score += capability.speed_tier * 4
            score += (6 - capability.cost_tier) * 3
            score += min(capability.max_context_tokens, 256_000) / 64_000
        stage_affinity = {
            "plan": {"openai": 12, "gemini": 8, "anthropic": 6},
            "execute": {"openai": 14, "anthropic": 8, "gemini": 6},
            "review": {"anthropic": 16, "openai": 8, "gemini": 6},
        }
        score += stage_affinity.get(stage, {}).get(provider, 0)
        score -= recent_failures.get(provider, 0) * 40
        return score
    def stage_provider_order(
        self,
        *,
        stage: str,
        available: list[str],
        prefs: dict[str, str] | None = None,
    ) -> list[str]:
        default_provider = (self._default_provider or "").strip().lower()
        prefs = prefs or {}
        preferred = {
            "plan": ["openai", "anthropic", "gemini", "local_echo"],
            "execute": ["openai", "anthropic", "gemini", "local_echo"],
            "review": ["anthropic", "openai", "gemini", "local_echo"],
        }.get(stage, ["openai", "anthropic", "gemini", "local_echo"])
        fallback_override = [
            item.strip().lower()
            for item in str(prefs.get("provider_fallback_order") or "").split(",")
            if item.strip()
        ]
        if fallback_override:
            preferred = fallback_override + [
                provider for provider in preferred if provider not in fallback_override
            ]
        if default_provider and default_provider in available:
            preferred = [default_provider] + [
                provider for provider in preferred if provider != default_provider
            ]
        ordered = [provider for provider in preferred if provider in available]
        for provider in available:
            if provider not in ordered:
                ordered.append(provider)
        return ordered
    def latest_run_provider_model(self, task_id) -> tuple[str | None, str | None]:
        for event in reversed(self._store.list_project_events(task_id=task_id, limit=100)):
            if event.event_type not in {"run.completed", "model.switch.completed"}:
                continue
            provider = (
                str(event.event_data.get("provider") or event.event_data.get("to_provider") or "")
                .strip()
                .lower()
            )
            model = str(
                event.event_data.get("target_model") or event.event_data.get("to_model") or ""
            ).strip()
            if provider and model:
                return provider, model
        return None, None
    def record_model_switch_if_needed(
        self,
        *,
        task_id,
        previous_provider: str | None,
        previous_model: str | None,
        next_provider: str,
        next_model: str,
        stage_role: str,
        continuity_enabled: bool,
        context_bundle_id: str,
    ) -> None:
        if previous_provider == next_provider and previous_model == next_model:
            return
        continuity_status = "preserved" if continuity_enabled else "best_effort"
        if previous_provider and previous_provider != next_provider:
            continuity_status = (
                "cross_provider_preserved" if continuity_enabled else "cross_provider_best_effort"
            )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="model.switch.completed",
                event_data={
                    "from_provider": previous_provider or "",
                    "from_model": previous_model or "",
                    "to_provider": next_provider,
                    "to_model": next_model,
                    "target_agent": stage_role,
                    "context_bundle_id": context_bundle_id,
                    "continuity_status": continuity_status,
                },
            )
        )
    def is_local_echo_mode(self, *, provider: str | None, model: str | None) -> bool:
        return (
            (provider or "").strip().lower() == "local_echo"
            or (model or "").strip().lower() == "local_echo"
        )
    def resolve_provider_switch_budget(self, prefs: dict[str, str]) -> int:
        raw = prefs.get("autonomy_max_provider_switches")
        if raw is None:
            return self._max_provider_switches
        try:
            return max(int(raw), 0)
        except ValueError:
            return self._max_provider_switches
