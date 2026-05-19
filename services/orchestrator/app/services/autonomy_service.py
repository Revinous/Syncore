from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from packages.contracts.python.models import (
    BatonPacketCreate,
    BatonPayload,
    ProjectEvent,
    ProjectEventCreate,
    RoutingRequest,
    Task,
    TaskUpdate,
)
from services.analyst.digest import AnalystDigestService
from services.memory import MemoryStoreProtocol

from app.config import Settings
from app.services.autonomy_candidates import CandidateStateService
from app.services.autonomy_failure_handler import AutonomyFailureHandler
from app.services.autonomy_failure_policy import FailurePolicy
from app.services.autonomy_finalizer import TaskFinalizationService
from app.services.autonomy_prompt_service import AutonomyPromptService
from app.services.autonomy_quality_gate import AutonomyQualityGate
from app.services.autonomy_recommendation_service import AutonomyRecommendationService
from app.services.autonomy_runtime_selector import AutonomyRuntimeSelector
from app.services.autonomy_stage_processor import AutonomyStageContext, AutonomyStageProcessor
from app.services.autonomy_subtasks import SubtaskFanoutCoordinator
from app.services.autonomy_task_gate import AutonomyTaskGate
from app.services.autonomy_text_utils import (
    extract_acceptance_checks,
    extract_command_candidates,
    extract_first_match,
    extract_list_items,
    extract_paths,
    parse_plan_lines,
    parse_uuid,
    split_delimited,
    string_list,
)
from app.services.execute_plan_builder import ExecutePlanBuilder
from app.services.local_settings_service import (
    LocalExecutionSettingsService,
    resolve_default_provider_settings,
)
from app.services.routing_service import RoutingService
from app.services.run_execution_service import RunExecutionService
from app.store_factory import build_memory_store

AUTONOMY_STAGES = ("plan", "execute", "review")
AUTONOMY_STRATEGIES = (
    "default",
    "tighten_scope",
    "increase_detail",
    "raise_verification",
    "switch_execution_role",
)
SDLC_CHECKLIST_ITEMS = (
    "requirements",
    "design",
    "implementation",
    "tests",
    "docs",
    "release",
)


@dataclass
class AutonomyResult:
    task_id: UUID
    status: str
    run_id: UUID | None = None
    note: str = ""


class AutonomyService:
    def __init__(
        self,
        *,
        store: MemoryStoreProtocol,
        run_execution_service: RunExecutionService,
        routing_service: RoutingService,
        digest_service: AnalystDigestService,
        default_provider: str,
        default_model: str,
        default_max_retries: int,
        retry_base_seconds: float,
        max_cycles: int,
        max_total_steps: int,
        review_pass_keyword: str,
        plan_min_chars: int,
        execute_min_chars: int,
        review_min_chars: int,
        workspace_execution_enabled: bool,
        workspace_execution_profile: str,
        workspace_auto_approve_low_risk: bool,
        workspace_max_steps: int,
        execute_plan_enabled: bool,
        failure_taxonomy_v2_enabled: bool,
        low_info_stop_enabled: bool,
        low_info_threshold: int,
        max_provider_switches: int,
    ) -> None:
        self._store = store
        self._run_execution_service = run_execution_service
        self._routing_service = routing_service
        self._digest_service = digest_service
        self._default_provider = default_provider
        self._default_model = default_model
        self._default_max_retries = max(default_max_retries, 0)
        self._retry_base_seconds = max(retry_base_seconds, 0.1)
        self._max_cycles = max(max_cycles, 1)
        self._max_total_steps = max(max_total_steps, 1)
        self._review_pass_keyword = (review_pass_keyword or "PASS").strip()
        self._plan_min_chars = max(plan_min_chars, 20)
        self._execute_min_chars = max(execute_min_chars, 40)
        self._review_min_chars = max(review_min_chars, 20)
        self._workspace_execution_enabled = workspace_execution_enabled
        self._workspace_execution_profile = workspace_execution_profile
        self._workspace_auto_approve_low_risk = workspace_auto_approve_low_risk
        self._workspace_max_steps = max(workspace_max_steps, 1)
        self._execute_plan_enabled = execute_plan_enabled
        self._failure_taxonomy_v2_enabled = failure_taxonomy_v2_enabled
        self._low_info_stop_enabled = low_info_stop_enabled
        self._low_info_threshold = max(low_info_threshold, 2)
        self._max_provider_switches = max(max_provider_switches, 0)
        self._candidate_state = CandidateStateService(
            store=self._store,
            parse_uuid=parse_uuid,
        )
        self._finalizer = TaskFinalizationService(
            store=self._store,
            digest_service=self._digest_service,
        )
        self._subtask_fanout = SubtaskFanoutCoordinator(
            store=self._store,
            default_provider=self._default_provider,
            default_model=self._default_model,
            as_bool=_as_bool,
            parse_positive_int=lambda value: _parse_positive_int(value, default=3, maximum=8),
        )
        self._failure_policy = FailurePolicy(self._store)
        self._recommendations = AutonomyRecommendationService(
            store=self._store,
            candidate_state=self._candidate_state,
            parse_uuid=parse_uuid,
            extract_first_match=extract_first_match,
            extract_paths=extract_paths,
            extract_list_items=extract_list_items,
            string_list=string_list,
        )
        self._quality_gate = AutonomyQualityGate(
            store=self._store,
            review_pass_keyword=self._review_pass_keyword,
            plan_min_chars=self._plan_min_chars,
            execute_min_chars=self._execute_min_chars,
            review_min_chars=self._review_min_chars,
            low_info_threshold=self._low_info_threshold,
            string_list=string_list,
            latest_execute_plan=self._latest_execute_plan,
            selected_candidate_state=self._recommendations.selected_candidate_state,
            latest_event=self._latest_event,
        )
        self._task_gate = AutonomyTaskGate(
            store=self._store,
            latest_event=self._latest_event,
            event_int=_event_int,
            event_bool=_event_bool,
        )
        self._runtime_selector = AutonomyRuntimeSelector(
            store=self._store,
            run_execution_service=self._run_execution_service,
            default_provider=self._default_provider,
            default_model=self._default_model,
            max_provider_switches=self._max_provider_switches,
            parse_positive_int=lambda value, default, maximum: _parse_positive_int(
                value,
                default=default,
                maximum=maximum,
            ),
            latest_event=self._latest_event,
            event_int=_event_int,
            event_bool=_event_bool,
        )
        self._failure_handler = AutonomyFailureHandler(
            store=self._store,
            low_info_threshold=self._low_info_threshold,
            failure_taxonomy_v2_enabled=self._failure_taxonomy_v2_enabled,
            latest_execute_plan=self._latest_execute_plan,
        )
        self._prompt_service = AutonomyPromptService(
            store=self._store,
            review_pass_keyword=self._review_pass_keyword,
            strategy_guidance=self._strategy_guidance,
            latest_execute_plan=self._latest_execute_plan,
            recommendation_service=self._recommendations,
            string_list=string_list,
        )
        self._execute_plan_builder = ExecutePlanBuilder(
            store=self._store,
            recommendation_context=(
                lambda task, prefs: self._recommendations.recommended_improvement_prompt_context(
                    task=task,
                    prefs=prefs,
                )
            ),
            recommendation_state=self._recommendations.recommended_improvement_state,
            extract_paths=extract_paths,
            extract_command_candidates=extract_command_candidates,
            extract_acceptance_checks=extract_acceptance_checks,
            parse_plan_lines=parse_plan_lines,
            strategy_guidance=self._strategy_guidance,
            string_list=string_list,
            parse_uuid=parse_uuid,
        )
        self._stage_processor = AutonomyStageProcessor(
            store=self._store,
            run_execution_service=self._run_execution_service,
            runtime_selector=self._runtime_selector,
            quality_gate=self._quality_gate,
            failure_handler=self._failure_handler,
            task_gate=self._task_gate,
            workspace_execution_enabled=self._workspace_execution_enabled,
            workspace_execution_profile=self._workspace_execution_profile,
            workspace_max_steps=self._workspace_max_steps,
            retry_base_seconds=self._retry_base_seconds,
            review_pass_keyword=self._review_pass_keyword,
            low_info_stop_enabled=self._low_info_stop_enabled,
            parse_positive_int=lambda value, default, maximum: _parse_positive_int(
                value,
                default=default,
                maximum=maximum,
            ),
            parse_uuid=parse_uuid,
            role_for_stage=self._prompt_service.role_for_stage,
            prompt_for_stage=self._prompt_service.prompt_for_stage,
            select_replan_strategy=self._select_replan_strategy,
            save_snapshot=self._save_snapshot,
            record_feedback=self._record_feedback,
            persist_execute_plan=self._persist_execute_plan,
            persist_stage_handoff_artifacts=self._persist_stage_handoff_artifacts,
            spawn_subtasks_once=self._spawn_subtasks_once,
            child_gate_status=self._child_gate_status,
            finalize_task=self._finalize_task,
            record_mutation_intent=self._record_mutation_intent,
            missing_sdlc_topics=_missing_sdlc_topics,
            extract_sdlc_checklist_status=_extract_sdlc_checklist_status,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "AutonomyService":
        store = build_memory_store(settings)
        run_execution_service = RunExecutionService.from_settings(settings)
        available_capabilities = run_execution_service.list_provider_capabilities()
        configured_providers = {item.provider for item in available_capabilities}
        provider_model_hints = {
            item.provider: item.model_hint for item in available_capabilities
        }
        local_settings = LocalExecutionSettingsService().load()
        default_provider, default_model = resolve_default_provider_settings(
            configured_providers=configured_providers,
            provider_model_hints=provider_model_hints,
            fallback_provider=settings.default_llm_provider,
            fallback_model=settings.autonomy_default_model,
            stored_preference=(
                local_settings.default_provider_preference if local_settings else None
            ),
        )
        return cls(
            store=store,
            run_execution_service=run_execution_service,
            routing_service=RoutingService(),
            digest_service=AnalystDigestService(),
            default_provider=default_provider,
            default_model=default_model,
            default_max_retries=settings.autonomy_max_retries,
            retry_base_seconds=settings.autonomy_retry_base_seconds,
            max_cycles=settings.autonomy_max_cycles,
            max_total_steps=settings.autonomy_max_total_steps,
            review_pass_keyword=settings.autonomy_review_pass_keyword,
            plan_min_chars=settings.autonomy_plan_min_chars,
            execute_min_chars=settings.autonomy_execute_min_chars,
            review_min_chars=settings.autonomy_review_min_chars,
            workspace_execution_enabled=settings.autonomy_workspace_execution_enabled,
            workspace_execution_profile=settings.autonomy_workspace_execution_profile,
            workspace_auto_approve_low_risk=settings.autonomy_workspace_auto_approve_low_risk,
            workspace_max_steps=settings.autonomy_workspace_max_steps,
            execute_plan_enabled=settings.autonomy_execute_plan_enabled,
            failure_taxonomy_v2_enabled=settings.autonomy_failure_taxonomy_v2,
            low_info_stop_enabled=settings.autonomy_low_info_stop_enabled,
            low_info_threshold=settings.autonomy_low_info_threshold,
            max_provider_switches=settings.autonomy_max_provider_switches,
        )

    def process_pending_tasks_once(self, limit: int = 50) -> list[AutonomyResult]:
        results: list[AutonomyResult] = []
        for task in self._store.list_tasks(limit=limit):
            if task.status not in {"new", "in_progress"}:
                continue
            results.append(self.process_task(task.id))
        return results

    def process_task(self, task_id: UUID) -> AutonomyResult:
        task = self._store.get_task(task_id)
        if task is None:
            return AutonomyResult(task_id=task_id, status="missing", note="Task not found.")
        if task.status == "completed":
            return AutonomyResult(task_id=task_id, status="skipped", note="Task already completed.")
        if task.status == "blocked":
            return AutonomyResult(task_id=task_id, status="blocked", note="Task is blocked.")

        events = self._store.list_project_events(task_id=task_id, limit=500)
        prefs = self._load_preferences(events)
        autonomy_mode, autonomy_note = self._runtime_selector.resolve_autonomy_mode(
            task=task,
            prefs=prefs,
        )
        if autonomy_note:
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task_id,
                    event_type="autonomy.mode.adjusted",
                    event_data={"mode": autonomy_mode, "reason": autonomy_note[:250]},
                )
            )
        requires_approval = _as_bool(prefs.get("requires_approval"))
        if (
            self._workspace_auto_approve_low_risk
            and task.workspace_id is not None
            and task.complexity == "low"
        ):
            requires_approval = False
        if autonomy_mode == "guided":
            requires_approval = True
        if autonomy_mode == "unattended":
            requires_approval = False

        child_gate = self._child_gate_status(task=task, events=events)
        if child_gate["mode"] == "awaiting_children":
            return AutonomyResult(
                task_id=task_id,
                status="in_progress",
                note=str(child_gate.get("note") or "Waiting for child tasks."),
            )
        if child_gate["mode"] == "children_failed":
            self._store.update_task(task_id, TaskUpdate(status="blocked"))
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task_id,
                    event_type="autonomy.failed",
                    event_data={"error": str(child_gate.get("note") or "Child tasks failed.")},
                )
            )
            return AutonomyResult(
                task_id=task_id,
                status="failed",
                note=str(child_gate.get("note") or "Child tasks failed."),
            )
        if child_gate["mode"] == "children_completed":
            self._finalize_task(task_id)
            return AutonomyResult(
                task_id=task_id,
                status="completed",
                note=str(child_gate.get("note") or "Child tasks completed successfully."),
            )
        enforce_sdlc = self._should_enforce_sdlc(task=task, prefs=prefs)
        now_epoch = datetime.now(timezone.utc).timestamp()
        total_steps = self._task_gate.total_step_events(events)
        if total_steps >= self._max_total_steps:
            self._store.update_task(task_id, TaskUpdate(status="blocked"))
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task_id,
                    event_type="autonomy.failed",
                    event_data={"error": "Max autonomy step budget reached."},
                )
            )
            return AutonomyResult(
                task_id=task_id,
                status="failed",
                note="Blocked by max autonomy step budget.",
            )

        task = self._store.update_task(task_id, TaskUpdate(status="in_progress")) or task
        execute_role, cycle = self._bootstrap_if_needed(task=task, events=events)
        events = self._store.list_project_events(task_id=task_id, limit=500)

        next_stage = self._task_gate.next_stage(events, cycle=cycle, stages=AUTONOMY_STAGES)
        if next_stage is None:
            self._finalize_task(task_id)
            latest = self._latest_stage_completion(events)
            return AutonomyResult(
                task_id=task_id,
                status="completed",
                run_id=latest,
                note="All autonomy stages completed.",
            )

        approval_gate = self._task_gate.approval_gate_state(
            events=events,
            stage=next_stage,
            requires_approval=requires_approval,
        )
        if approval_gate == "awaiting":
            self._task_gate.ensure_approval_requested(task_id=task_id, events=events)
            return AutonomyResult(
                task_id=task_id,
                status="awaiting_approval",
                note="Waiting for explicit approval before execute stage.",
            )
        if approval_gate == "rejected":
            self._store.update_task(task_id, TaskUpdate(status="blocked"))
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task_id,
                    event_type="autonomy.failed",
                    event_data={
                        "stage": next_stage,
                        "error": "Rejected by operator approval gate.",
                    },
                )
            )
            return AutonomyResult(
                task_id=task_id,
                status="failed",
                note="Approval rejected. Task has been blocked.",
            )

        retry_gate = self._task_gate.scheduled_retry_epoch(events, stage=next_stage, cycle=cycle)
        if retry_gate is not None and now_epoch < retry_gate:
            seconds_left = max(int(retry_gate - now_epoch), 0)
            return AutonomyResult(
                task_id=task_id,
                status="waiting_retry",
                note=f"Waiting {seconds_left}s before retrying stage '{next_stage}'.",
            )

        sibling_recommendation_gate = self._implementation_recommendation_gate(
            task=task,
            prefs=prefs,
            stage=next_stage,
        )
        if sibling_recommendation_gate is not None:
            return sibling_recommendation_gate

        execute_plan_gate = self._execute_plan_gate(
            task=task,
            prefs=prefs,
            stage=next_stage,
            cycle=cycle,
            max_cycles=self._max_cycles,
        )
        if execute_plan_gate is not None:
            return execute_plan_gate

        if self._task_gate.stage_inflight(events, next_stage, cycle=cycle):
            return AutonomyResult(
                task_id=task_id,
                status="in_progress",
                note=f"Stage '{next_stage}' is already running.",
            )

        max_retries = self._resolve_max_retries(prefs)
        context = AutonomyStageContext(
            task=task,
            prefs=prefs,
            stage=next_stage,
            cycle=cycle,
            execute_role=execute_role,
            autonomy_mode=autonomy_mode,
            requires_approval=requires_approval,
            enforce_sdlc=enforce_sdlc,
            max_cycles=self._max_cycles,
            max_retries=max_retries,
        )
        try:
            stage_result = self._stage_processor.process(
                context=context,
                events=events,
            )
        except (LookupError, OSError, RuntimeError, ValueError) as error:
            stage_result = self._stage_processor.handle_failure(
                context=context,
                events=events,
                error=error,
            )
        return AutonomyResult(
            task_id=task_id,
            status=str(stage_result.get("status") or "failed"),
            run_id=stage_result.get("run_id"),
            note=str(stage_result.get("note") or ""),
        )

    def set_approval(
        self,
        *,
        task_id: UUID,
        approved: bool,
        reason: str | None = None,
    ) -> AutonomyResult:
        task = self._store.get_task(task_id)
        if task is None:
            return AutonomyResult(task_id=task_id, status="missing", note="Task not found.")

        reason_text = (reason or "").strip()
        event_data: dict[str, str | int | float | bool | None] = {"approved": approved}
        if reason_text:
            event_data["reason"] = reason_text[:250]

        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="autonomy.approval",
                event_data=event_data,
            )
        )
        if approved:
            return AutonomyResult(
                task_id=task_id,
                status="approved",
                note="Task approved for autonomy execution.",
            )

        self._store.update_task(task_id, TaskUpdate(status="blocked"))
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="autonomy.failed",
                event_data={"error": "Rejected by operator approval gate."},
            )
        )
        return AutonomyResult(
            task_id=task_id,
            status="rejected",
            note="Task rejected and blocked.",
        )

    def _bootstrap_if_needed(self, *, task: Task, events: list[ProjectEvent]) -> tuple[str, int]:
        started_event = self._latest_event(events, "autonomy.started")
        if started_event is not None:
            execute_role = str(started_event.event_data.get("execute_role") or "coder")
            return _normalize_agent_role(execute_role), self._current_cycle(events)

        routing_decision = self._routing_service.choose_next(
            payload=RoutingRequest(
                task_type=task.task_type,
                complexity=task.complexity,
                requires_memory=self._store.count_project_events(task.id) > 0,
            )
        )
        execute_role = _normalize_agent_role(routing_decision.worker_role)
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="routing.decision",
                event_data={
                    "worker_role": routing_decision.worker_role,
                    "model_tier": routing_decision.model_tier,
                    "reasoning": routing_decision.reasoning[:250],
                    "source": "autonomy",
                },
            )
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.started",
                event_data={"execute_role": execute_role},
            )
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.cycle.started",
                event_data={"cycle": 1, "mode": "initial"},
            )
        )
        self._persist_autonomy_baton(task=task, routing_worker=execute_role)
        return execute_role, 1

    def _load_preferences(self, events: list[ProjectEvent]) -> dict[str, str]:
        merged: dict[str, str] = {}
        for event in events:
            if event.event_type != "task.preferences":
                continue
            for key, value in event.event_data.items():
                if isinstance(value, str):
                    merged[key] = value
                elif isinstance(value, (int, float, bool)):
                    merged[key] = str(value)
        return merged

    def _resolve_provider(
        self,
        *,
        stage: str,
        task: Task,
        prefs: dict[str, str],
        previous_provider: str | None = None,
    ) -> str | None:
        return self._runtime_selector.resolve_provider(
            stage=stage,
            task=task,
            prefs=prefs,
            previous_provider=previous_provider,
        )

    def _resolve_max_retries(
self, prefs: dict[str, str]) -> int:
        raw = prefs.get("autonomy_max_retries")
        if raw is None:
            return self._default_max_retries
        try:
            parsed = int(raw)
        except ValueError:
            return self._default_max_retries
        return max(parsed, 0)

    def _current_cycle(self, events: list[ProjectEvent]) -> int:
        return self._task_gate.current_cycle(events)

    def _should_enforce_sdlc(self, *, task: Task, prefs: dict[str, str]) -> bool:
        if _as_bool(prefs.get("sdlc_enforce")):
            return True
        if task.workspace_id is None:
            return False
        workspace = self._store.get_workspace(task.workspace_id)
        if workspace is None:
            return False
        return workspace.name.strip().lower() == "syncore"

    def _spawn_subtasks_once(self, *, task: Task, prefs: dict[str, str]) -> None:
        self._subtask_fanout.spawn_once(task=task, prefs=prefs)

    def _select_replan_strategy(
        self,
        *,
        events: list[ProjectEvent],
        stage: str,
        cycle: int,
        execute_role: str,
    ) -> str:
        return self._failure_policy.select_replan_strategy(
            events=events,
            stage=stage,
            cycle=cycle,
            execute_role=execute_role,
        )

    def _strategy_guidance(self, strategy: str) -> str:
        return self._failure_policy.strategy_guidance(strategy)

    # Compatibility wrappers kept for tests and narrow internal seams while the
    # orchestration services are being decomposed.
    def _role_for_stage(self, *, stage: str, execute_role: str, strategy: str) -> str:
        return self._prompt_service.role_for_stage(
            stage=stage,
            execute_role=execute_role,
            strategy=strategy,
        )

    def _prompt_for_stage(
        self,
        *,
        stage: str,
        task: Task,
        prefs: dict[str, str],
        cycle: int,
        strategy: str,
        enforce_sdlc: bool,
    ) -> str:
        return self._prompt_service.prompt_for_stage(
            stage=stage,
            task=task,
            prefs=prefs,
            cycle=cycle,
            strategy=strategy,
            enforce_sdlc=enforce_sdlc,
        )

    def _selected_candidate_prompt_context(self, *, task: Task, prefs: dict[str, str]) -> str:
        return self._recommendations.selected_candidate_prompt_context(task=task, prefs=prefs)

    def _recommended_improvement_prompt_context(
        self,
        *,
        task: Task,
        prefs: dict[str, str],
    ) -> str:
        return self._recommendations.recommended_improvement_prompt_context(
            task=task,
            prefs=prefs,
        )

    def _selected_candidate_state(self, parent_id: UUID) -> dict[str, object]:
        return self._recommendations.selected_candidate_state(parent_id)

    def _recommended_improvement_state(self, parent_id: UUID) -> dict[str, object]:
        return self._recommendations.recommended_improvement_state(parent_id)

    def _extract_recommended_improvement(self, output_text: str) -> dict[str, object]:
        return self._recommendations.extract_recommended_improvement(output_text)

    def _build_candidate_artifact(
        self,
        *,
        task: Task,
        recommendation: dict[str, object],
    ) -> dict[str, object]:
        return self._recommendations.build_candidate_artifact(
            task=task,
            recommendation=recommendation,
        )

    def _recommendation_needs_workspace_fallback(
        self,
        recommendation: dict[str, object],
    ) -> bool:
        return self._recommendations.recommendation_needs_workspace_fallback(recommendation)

    def _fallback_recommended_improvement(
        self,
        task: Task,
        recommendation: dict[str, object],
    ) -> dict[str, object]:
        return self._recommendations.fallback_recommended_improvement(
            task,
            recommendation,
        )

    def _workspace_analysis_prompt_context(self, task: Task) -> str:
        return self._recommendations.workspace_analysis_prompt_context(task)

    def _record_feedback(self, *, task_id: UUID, stage: str, strategy: str, outcome: str) -> None:
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="autonomy.feedback",
                event_data={
                    "stage": stage,
                    "strategy": strategy,
                    "outcome": outcome,
                },
            )
        )

    def _persist_execute_plan(
        self,
        *,
        task: Task,
        prefs: dict[str, str],
        output_text: str,
        cycle: int,
        strategy: str,
    ) -> None:
        if not self._execute_plan_enabled:
            return
        events = self._store.list_project_events(task_id=task.id, limit=300)
        existing = self._latest_event(events, "autonomy.execute_plan.created")
        if existing is not None and (_event_int(existing.event_data.get("cycle")) or 1) == cycle:
            return
        plan = self._build_execute_plan(
            task=task,
            prefs=prefs,
            output_text=output_text,
            cycle=cycle,
            strategy=strategy,
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.execute_plan.created",
                event_data={
                    "cycle": cycle,
                    "strategy": strategy,
                    "objective": plan["objective"][:250],
                    "actions": " | ".join(plan["proposed_actions"][:6])[:250],
                    "target_files": ", ".join(plan["target_files"][:12])[:250],
                    "verification_commands": ", ".join(plan["verification_commands"][:8])[:250],
                    "acceptance_checks": " | ".join(plan["acceptance_checks"][:8])[:250],
                    "fallback_strategy": plan["fallback_strategy"][:250],
                    "risk_level": plan["risk_level"],
                    "signature": plan["signature"][:250],
                    "action_count": len(plan["proposed_actions"]),
                },
            )
        )

    def _build_execute_plan(
        self,
        *,
        task: Task,
        prefs: dict[str, str],
        output_text: str,
        cycle: int,
        strategy: str,
    ) -> dict[str, object]:
        del cycle
        return self._execute_plan_builder.build(
            task=task,
            prefs=prefs,
            output_text=output_text,
            strategy=strategy,
        )

    def _latest_execute_plan(self, task_id: UUID) -> dict[str, object] | None:
        events = self._store.list_project_events(task_id=task_id, limit=300)
        event = self._latest_event(events, "autonomy.execute_plan.created")
        if event is None:
            return None
        return {
            "cycle": _event_int(event.event_data.get("cycle")) or 1,
            "objective": str(event.event_data.get("objective") or "").strip(),
            "actions": split_delimited(
                str(event.event_data.get("actions") or ""),
                delimiter="|",
            ),
            "target_files": split_delimited(str(event.event_data.get("target_files") or "")),
            "verification_commands": split_delimited(
                str(event.event_data.get("verification_commands") or "")
            ),
            "acceptance_checks": split_delimited(
                str(event.event_data.get("acceptance_checks") or ""),
                delimiter="|",
            ),
            "fallback_strategy": str(event.event_data.get("fallback_strategy") or "").strip(),
            "risk_level": str(event.event_data.get("risk_level") or "medium").strip().lower(),
            "signature": str(event.event_data.get("signature") or "").strip(),
        }

    def _execute_plan_gate(
        self,
        *,
        task: Task,
        prefs: dict[str, str],
        stage: str,
        cycle: int,
        max_cycles: int,
    ) -> AutonomyResult | None:
        if stage != "execute" or not self._execute_plan_enabled:
            return None
        plan = self._latest_execute_plan(task.id)
        if plan is not None and self._execute_plan_is_concrete(plan):
            return None
        if cycle >= max_cycles:
            self._store.update_task(task.id, TaskUpdate(status="blocked"))
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task.id,
                    event_type="autonomy.implementation.blocked.missing_plan",
                    event_data={"cycle": cycle},
                )
            )
            return AutonomyResult(
                task_id=task.id,
                status="failed",
                note="Execute stage blocked because no concrete execute plan was available.",
            )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.execute_plan.missing",
                event_data={
                    "cycle": cycle,
                    "parent_task_id": prefs.get("parent_task_id", ""),
                },
            )
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.cycle.started",
                event_data={"cycle": cycle + 1, "mode": "replan", "reason": "missing_execute_plan"},
            )
        )
        return AutonomyResult(
            task_id=task.id,
            status="replanning",
            note=(
                f"Execute stage deferred until a concrete plan exists; moved to cycle {cycle + 1}."
            ),
        )

    def _execute_plan_is_concrete(self, plan: dict[str, object]) -> bool:
        verification_commands = string_list(plan.get("verification_commands"))
        target_files = string_list(plan.get("target_files"))
        actions = string_list(plan.get("actions"))
        objective = str(plan.get("objective") or "").strip()
        return bool(objective and (verification_commands or target_files or actions))

    def _record_mutation_intent(self, *, task: Task, prefs: dict[str, str]) -> None:
        plan = self._latest_execute_plan(task.id) or {}
        candidate_state = self._recommendations.selected_candidate_state(
            parse_uuid(prefs.get("parent_task_id")) or task.id
        )
        target_files = string_list(plan.get("target_files"))
        verification_commands = string_list(plan.get("verification_commands"))
        candidate_id = ""
        if candidate_state.get("status") == "ready":
            event = candidate_state.get("event")
            if isinstance(event, ProjectEvent):
                candidate_id = str(event.event_data.get("candidate_id") or "")
                if not target_files:
                    target_files = string_list(event.event_data.get("target_files"))
                if not verification_commands:
                    verification = str(event.event_data.get("verification_command") or "").strip()
                    if verification:
                        verification_commands = [verification]
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.mutation_intent.declared",
                event_data={
                    "candidate_id": candidate_id[:120],
                    "target_files": ", ".join(target_files[:10])[:250],
                    "verification_commands": ", ".join(verification_commands[:6])[:250],
                },
            )
        )

    def _save_snapshot(
        self,
        *,
        task_id: UUID,
        cycle: int,
        stage: str,
        state: str,
        strategy: str,
        quality_score: int,
        details: dict[str, object],
    ) -> None:
        self._store.save_autonomy_snapshot(
            task_id=task_id,
            cycle=cycle,
            stage=stage,
            state=state,
            strategy=strategy,
            quality_score=quality_score,
            details=details,
        )

    def _persist_autonomy_baton(self, *, task: Task, routing_worker: str) -> None:
        self._store.save_baton_packet(
            BatonPacketCreate(
                task_id=task.id,
                from_agent="planner",
                to_agent=_normalize_agent_role(routing_worker),
                summary=f"Autonomy kickoff for task: {task.title}",
                payload=BatonPayload(
                    objective=task.title,
                    completed_work=["Task accepted by autonomy loop"],
                    constraints=["Honor task constraints and active context policies"],
                    open_questions=[],
                    next_best_action="Execute the task and report completion details",
                    relevant_artifacts=[],
                ),
            )
        )

    def _persist_stage_handoff_artifacts(
        self,
        *,
        task: Task,
        prefs: dict[str, str],
        stage: str,
        output_text: str,
    ) -> None:
        if stage != "execute":
            return
        parent_id = parse_uuid(prefs.get("parent_task_id"))
        if parent_id is None:
            return
        if task.task_type != "analysis":
            return
        recommendation = self._recommendations.extract_recommended_improvement(output_text)
        if self._recommendations.recommendation_needs_workspace_fallback(recommendation):
            recommendation = self._recommendations.fallback_recommended_improvement(
                task,
                recommendation,
            )
        if not recommendation["summary"] and not recommendation["action"]:
            return
        candidate = self._recommendations.build_candidate_artifact(
            task=task,
            recommendation=recommendation,
        )
        existing = self._latest_event(
            self._store.list_project_events(task_id=task.id, limit=200),
            "autonomy.recommended_improvement",
        )
        if existing is not None:
            return
        summary = recommendation["summary"] or f"Recommended improvement for {task.title}"
        action = recommendation["action"] or "Implement the recommended improvement."
        target_files = recommendation["target_files"]
        risks = recommendation["risks"]
        verification = recommendation["verification"]
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.recommended_improvement",
                event_data={
                    "parent_task_id": str(parent_id),
                    "summary": summary[:250],
                    "action": action[:250],
                    "target_files": ", ".join(target_files[:10])[:250],
                    "verification_command": verification[:250],
                    "risks": "; ".join(risks[:6])[:250],
                },
            )
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.candidate.ranked",
                event_data={
                    "parent_task_id": str(parent_id),
                    "candidate_id": str(candidate["candidate_id"]),
                    "rank": 1,
                    "candidate_type": str(candidate["candidate_type"])[:80],
                    "summary": summary[:250],
                    "target_files": ", ".join(target_files[:10])[:250],
                    "verification_command": verification[:250],
                    "confidence": int(candidate["confidence"]),
                    "impact": int(candidate["impact"]),
                    "effort": int(candidate["effort"]),
                    "risk_level": str(candidate["risk_level"])[:80],
                    "evidence_kind": str(candidate["evidence_kind"])[:120],
                },
            )
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.candidate.selected",
                event_data={
                    "parent_task_id": str(parent_id),
                    "candidate_id": str(candidate["candidate_id"]),
                    "candidate_type": str(candidate["candidate_type"])[:80],
                    "summary": summary[:250],
                    "action": action[:250],
                    "target_files": ", ".join(target_files[:10])[:250],
                    "verification_command": verification[:250],
                    "confidence": int(candidate["confidence"]),
                    "impact": int(candidate["impact"]),
                    "effort": int(candidate["effort"]),
                    "risk_level": str(candidate["risk_level"])[:80],
                    "evidence_kind": str(candidate["evidence_kind"])[:120],
                },
            )
        )
        self._store.save_baton_packet(
            BatonPacketCreate(
                task_id=task.id,
                from_agent="analyst",
                to_agent="coder",
                summary=summary[:250],
                payload=BatonPayload(
                    objective=f"Implement recommended improvement for parent task {parent_id}",
                    completed_work=[summary[:250], *(f"Touch {path}" for path in target_files[:8])],
                    constraints=risks[:8],
                    open_questions=[],
                    next_best_action=action[:250],
                    relevant_artifacts=target_files[:12],
                ),
            )
        )

    def _implementation_recommendation_gate(
        self,
        *,
        task: Task,
        prefs: dict[str, str],
        stage: str,
    ) -> AutonomyResult | None:
        if stage != "execute" or task.task_type != "implementation":
            return None
        parent_id = parse_uuid(prefs.get("parent_task_id"))
        if parent_id is None:
            return None
        sibling_state = self._recommendations.recommended_improvement_state(parent_id)
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.implementation.bound",
                event_data={
                    "stage": stage,
                    "parent_task_id": str(parent_id),
                    "recommendation_status": str(sibling_state.get("status") or ""),
                },
            )
        )
        if sibling_state["status"] == "blocked":
            self._store.update_task(task.id, TaskUpdate(status="blocked"))
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task.id,
                    event_type="autonomy.failed",
                    event_data={"error": str(sibling_state["note"])[:250]},
                )
            )
            return AutonomyResult(
                task_id=task.id,
                status="failed",
                note=str(sibling_state["note"]),
            )
        if sibling_state["status"] == "waiting":
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task.id,
                    event_type="autonomy.implementation.blocked.missing_recommendation",
                    event_data={"parent_task_id": str(parent_id)},
                )
            )
            return AutonomyResult(
                task_id=task.id,
                status="in_progress",
                note=str(sibling_state["note"]),
            )
        return None

    def _finalize_task(self, task_id: UUID) -> None:
        self._finalizer.finalize_task(task_id)

    def _latest_stage_completion(self, events: list[ProjectEvent]) -> UUID | None:
        for event in reversed(events):
            if event.event_type != "autonomy.stage.completed":
                continue
            raw = str(event.event_data.get("run_id") or "").strip()
            if not raw:
                continue
            try:
                return UUID(raw)
            except ValueError:
                return None
        return None

    def _latest_event(self, events: list[ProjectEvent], event_type: str) -> ProjectEvent | None:
        for event in reversed(events):
            if event.event_type == event_type:
                return event
        return None

    def _child_gate_status(self, *, task: Task, events: list[ProjectEvent]) -> dict[str, str]:
        return self._finalizer.child_gate_status(task=task, events=events)


def _normalize_agent_role(candidate: str) -> str:
    normalized = candidate.strip().lower()
    if normalized in {"planner", "coder", "reviewer", "analyst", "memory"}:
        return normalized
    if normalized == "orchestrator":
        return "coder"
    return "coder"


def _default_prompt(task: Task, *, strategy: str, guidance: str) -> str:
    return (
        "You are the autonomous implementation worker.\n"
        f"Task title: {task.title}\n"
        f"Task type: {task.task_type}\n"
        f"Complexity: {task.complexity}\n"
        f"Strategy: {strategy}\n"
        f"Guidance: {guidance}\n"
        "Deliver a concrete implementation plan, executable artifacts, and verification notes."
    )


def _as_bool(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _event_bool(value: str | int | float | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return _as_bool(value)
    return False


def _event_int(value: str | int | float | bool | None) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _parse_positive_int(value: str | None, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value.strip())
    except ValueError:
        return default
    if parsed < 1:
        return default
    return min(parsed, maximum)


def _latency_floor(value: str) -> int:
    mapping = {
        "fast": 4,
        "medium": 3,
        "slow": 1,
    }
    return mapping.get(value.strip().lower(), 1)


def _cost_ceiling(value: str) -> int:
    mapping = {
        "low": 2,
        "medium": 3,
        "high": 5,
    }
    return mapping.get(value.strip().lower(), 5)


def _missing_sdlc_topics(text: str) -> list[str]:
    lowered = text.lower()
    missing: list[str] = []
    for item in SDLC_CHECKLIST_ITEMS:
        token = "test" if item == "tests" else item
        if token not in lowered:
            missing.append(item)
    return missing


def _extract_sdlc_checklist_status(text: str) -> dict[str, bool]:
    status = {item: False for item in SDLC_CHECKLIST_ITEMS}
    lowered = (text or "").lower()
    for item in SDLC_CHECKLIST_ITEMS:
        pattern = rf"\[\s*[xX]\s*\]\s*{re.escape(item)}\b"
        if re.search(pattern, lowered):
            status[item] = True
    return status
