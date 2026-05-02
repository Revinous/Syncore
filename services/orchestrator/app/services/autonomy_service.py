from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from textwrap import shorten
from types import SimpleNamespace
from uuid import UUID

from packages.contracts.python.models import (
    BatonPacketCreate,
    BatonPayload,
    ProjectEvent,
    ProjectEventCreate,
    RoutingRequest,
    RunExecutionRequest,
    Task,
    TaskCreate,
    TaskUpdate,
)
from services.analyst.digest import AnalystDigestService
from services.memory import MemoryStoreProtocol

from app.config import Settings
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

    @classmethod
    def from_settings(cls, settings: Settings) -> "AutonomyService":
        store = build_memory_store(settings)
        return cls(
            store=store,
            run_execution_service=RunExecutionService.from_settings(settings),
            routing_service=RoutingService(),
            digest_service=AnalystDigestService(),
            default_provider=settings.default_llm_provider,
            default_model=settings.autonomy_default_model,
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
        autonomy_mode, autonomy_note = self._resolve_autonomy_mode(task=task, prefs=prefs)
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
        total_steps = self._total_step_events(events)
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

        next_stage = self._next_stage(events, cycle=cycle)
        if next_stage is None:
            self._finalize_task(task_id)
            latest = self._latest_stage_completion(events)
            return AutonomyResult(
                task_id=task_id,
                status="completed",
                run_id=latest,
                note="All autonomy stages completed.",
            )

        approval_gate = self._approval_gate_state(
            events=events,
            stage=next_stage,
            requires_approval=requires_approval,
        )
        if approval_gate == "awaiting":
            self._ensure_approval_requested(task_id=task_id, events=events)
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

        retry_gate = self._scheduled_retry_epoch(events, stage=next_stage, cycle=cycle)
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

        if self._stage_inflight(events=events, stage=next_stage, cycle=cycle):
            return AutonomyResult(
                task_id=task_id,
                status="in_progress",
                note=f"Stage '{next_stage}' is already running.",
            )

        strategy = self._select_replan_strategy(
            events=events,
            stage=next_stage,
            cycle=cycle,
            execute_role=execute_role,
        )
        previous_provider, previous_model = self._latest_run_provider_model(task.id)
        provider = self._resolve_provider(
            stage=next_stage,
            task=task,
            prefs=prefs,
            previous_provider=previous_provider,
        )
        model = self._resolve_model(stage=next_stage, task=task, provider=provider, prefs=prefs)
        max_retries = self._resolve_max_retries(prefs)
        prompt = self._prompt_for_stage(
            stage=next_stage,
            task=task,
            prefs=prefs,
            cycle=cycle,
            strategy=strategy,
            enforce_sdlc=enforce_sdlc,
        )
        stage_role = self._role_for_stage(
            stage=next_stage,
            execute_role=execute_role,
            strategy=strategy,
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="autonomy.stage.started",
                event_data={
                    "stage": next_stage,
                    "cycle": cycle,
                    "strategy": strategy,
                },
            )
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="autonomy.strategy.selected",
                event_data={
                    "stage": next_stage,
                    "cycle": cycle,
                    "strategy": strategy,
                },
            )
        )
        self._save_snapshot(
            task_id=task_id,
            cycle=cycle,
            stage=next_stage,
            state="started",
            strategy=strategy,
            quality_score=0,
            details={
                "role": stage_role,
                "provider": provider or "",
                "model": model,
                "previous_provider": previous_provider or "",
                "previous_model": previous_model or "",
            },
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="model.routing.selected",
                event_data={
                    "stage": next_stage,
                    "provider": provider or "",
                    "target_model": model,
                    "previous_provider": previous_provider or "",
                    "previous_model": previous_model or "",
                    "continuity_mode": prefs.get("maintain_context_continuity") or "true",
                    "optimization_goal": prefs.get("model_optimization_goal") or "balanced",
                },
            )
        )

        request = RunExecutionRequest(
            task_id=task_id,
            prompt=prompt,
            target_agent=stage_role,
            target_model=model,
            provider=provider,
            agent_role=stage_role,
            token_budget=8_000,
            max_output_tokens=1_200,
            temperature=0.2,
        )

        try:
            if (
                next_stage == "execute"
                and task.workspace_id is not None
                and self._workspace_execution_enabled
                and (
                    prefs.get("workspace_execution_enabled") is None
                    or _as_bool(prefs.get("workspace_execution_enabled"))
                )
            ):
                self._store.save_project_event(
                    ProjectEventCreate(
                        task_id=task_id,
                        event_type="autonomy.execution.mode",
                        event_data={
                            "mode": "workspace",
                            "profile": str(
                                prefs.get("workspace_policy_profile")
                                or self._workspace_execution_profile
                            ),
                            "autonomy_mode": autonomy_mode,
                        },
                    )
                )
                workspace_result = self._run_execution_service.execute_workspace_loop(
                    request,
                    max_steps=_parse_positive_int(
                        prefs.get("workspace_max_steps"),
                        default=self._workspace_max_steps,
                        maximum=8,
                    ),
                    policy_profile=str(
                        prefs.get("workspace_policy_profile") or self._workspace_execution_profile
                    ),
                    require_approval=requires_approval,
                    dry_run=autonomy_mode == "observe",
                )
                run = SimpleNamespace(
                    run_id=None,
                    provider=str(workspace_result.get("provider") or (provider or "")),
                    target_model=str(workspace_result.get("target_model") or model),
                    output_text=str(workspace_result.get("digest") or workspace_result),
                )
            else:
                run = self._run_execution_service.execute(request)
            self._record_model_switch_if_needed(
                task_id=task_id,
                previous_provider=previous_provider,
                previous_model=previous_model,
                next_provider=run.provider,
                next_model=run.target_model,
                stage_role=stage_role,
                continuity_enabled=(prefs.get("maintain_context_continuity") or "true").lower()
                != "false",
                context_bundle_id=str(getattr(run, "optimized_bundle_id", "") or ""),
            )
            quality = self._stage_quality_gate(
                stage=next_stage,
                output_text=run.output_text,
                strategy=strategy,
                enforce_sdlc=enforce_sdlc,
            )
            local_echo_mode = self._is_local_echo_mode(
                provider=run.provider,
                model=run.target_model,
            )
            if (
                local_echo_mode
                and next_stage in {"execute", "review"}
                and not bool(quality["passed"])
            ):
                quality = {
                    "passed": True,
                    "score": max(int(quality.get("score") or 0), 75),
                    "reasons": ["local_echo_relaxed_gate"],
                }
            checklist_status = _extract_sdlc_checklist_status(run.output_text)
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task_id,
                    event_type="autonomy.stage.completed",
                    event_data={
                        "stage": next_stage,
                        "cycle": cycle,
                        "run_id": str(run.run_id),
                        "provider": run.provider,
                        "target_model": run.target_model,
                        "strategy": strategy,
                    },
                )
            )
            self._save_snapshot(
                task_id=task_id,
                cycle=cycle,
                stage=next_stage,
                state="completed",
                strategy=strategy,
                quality_score=quality["score"],
                details={
                    "quality_passed": quality["passed"],
                    "quality_reasons": "; ".join(quality["reasons"]),
                    "run_id": str(run.run_id),
                    "sdlc_enforced": enforce_sdlc,
                    "sdlc_checked_count": sum(1 for v in checklist_status.values() if v),
                },
            )
            if not bool(quality["passed"]):
                quality_reason = "; ".join(quality["reasons"])
                if cycle >= self._max_cycles:
                    self._store.update_task(task_id, TaskUpdate(status="blocked"))
                    self._store.save_project_event(
                        ProjectEventCreate(
                            task_id=task_id,
                            event_type="autonomy.failed",
                            event_data={
                                "stage": next_stage,
                                "cycle": cycle,
                                "error": quality_reason,
                            },
                        )
                    )
                    return AutonomyResult(
                        task_id=task_id,
                        status="failed",
                        run_id=run.run_id,
                        note=f"Quality gate failed at '{next_stage}' and max cycles reached.",
                    )
                next_cycle = cycle + 1
                self._store.save_project_event(
                    ProjectEventCreate(
                        task_id=task_id,
                        event_type="autonomy.quality.failed",
                        event_data={
                            "stage": next_stage,
                            "cycle": cycle,
                            "reason": quality_reason[:250],
                            "next_cycle": next_cycle,
                            "strategy": strategy,
                            "quality_score": int(quality["score"]),
                        },
                    )
                )
                self._record_feedback(
                    task_id=task_id,
                    stage=next_stage,
                    strategy=strategy,
                    outcome="quality_failed",
                )
                self._store.save_project_event(
                    ProjectEventCreate(
                        task_id=task_id,
                        event_type="autonomy.cycle.started",
                        event_data={"cycle": next_cycle, "mode": "replan"},
                    )
                )
                return AutonomyResult(
                    task_id=task_id,
                    status="replanning",
                    run_id=run.run_id,
                    note=f"Quality gate failed at '{next_stage}'; moved to cycle {next_cycle}.",
                )

            if next_stage == "review":
                review_failed = (
                    self._review_pass_keyword
                    and self._review_pass_keyword.upper() not in run.output_text.upper()
                )
                if local_echo_mode:
                    review_failed = False
                if review_failed:
                    if cycle >= self._max_cycles:
                        self._store.update_task(task_id, TaskUpdate(status="blocked"))
                        self._store.save_project_event(
                            ProjectEventCreate(
                                task_id=task_id,
                                event_type="autonomy.failed",
                                event_data={
                                    "stage": "review",
                                    "cycle": cycle,
                                    "error": (
                                        "Review did not satisfy pass gate; "
                                        "max cycles reached."
                                    ),
                                },
                            )
                        )
                        return AutonomyResult(
                            task_id=task_id,
                            status="failed",
                            run_id=run.run_id,
                            note="Review gate failed and max cycles reached.",
                        )
                    next_cycle = cycle + 1
                    self._store.save_project_event(
                        ProjectEventCreate(
                            task_id=task_id,
                            event_type="autonomy.review.failed",
                            event_data={
                                "cycle": cycle,
                                "required_keyword": self._review_pass_keyword,
                                "next_cycle": next_cycle,
                            },
                        )
                    )
                    self._store.save_project_event(
                        ProjectEventCreate(
                            task_id=task_id,
                            event_type="autonomy.cycle.started",
                            event_data={"cycle": next_cycle, "mode": "replan"},
                        )
                    )
                    return AutonomyResult(
                        task_id=task_id,
                        status="replanning",
                        run_id=run.run_id,
                        note=f"Review gate failed; moved to cycle {next_cycle}.",
                    )
                self._record_feedback(
                    task_id=task_id,
                    stage=next_stage,
                    strategy=strategy,
                    outcome="success",
                )
                self._finalize_task(task_id)
                return AutonomyResult(
                    task_id=task_id,
                    status="completed",
                    run_id=run.run_id,
                    note="Autonomy review passed and task finalized.",
                )

            self._record_feedback(
                task_id=task_id,
                stage=next_stage,
                strategy=strategy,
                outcome="success",
            )
            self._persist_stage_handoff_artifacts(
                task=task,
                prefs=prefs,
                stage=next_stage,
                output_text=run.output_text,
            )
            if next_stage == "plan":
                self._spawn_subtasks_once(task=task, prefs=prefs)
                post_spawn_events = self._store.list_project_events(task_id=task.id, limit=500)
                post_spawn_gate = self._child_gate_status(task=task, events=post_spawn_events)
                if post_spawn_gate["mode"] == "awaiting_children":
                    return AutonomyResult(
                        task_id=task_id,
                        status="in_progress",
                        run_id=run.run_id,
                        note=str(
                            post_spawn_gate.get("note")
                            or "Plan complete; child tasks spawned and running."
                        ),
                    )
            return AutonomyResult(
                task_id=task_id,
                status="in_progress",
                run_id=run.run_id,
                note=f"Stage '{next_stage}' completed.",
            )
        except Exception as error:
            attempt = self._failed_attempts(events, stage=next_stage, cycle=cycle) + 1
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task_id,
                    event_type="autonomy.stage.failed",
                    event_data={
                        "stage": next_stage,
                        "cycle": cycle,
                        "attempt": attempt,
                        "error": str(error)[:250],
                        "strategy": strategy,
                    },
                )
            )
            self._save_snapshot(
                task_id=task_id,
                cycle=cycle,
                stage=next_stage,
                state="failed",
                strategy=strategy,
                quality_score=0,
                details={"attempt": attempt, "error": str(error)[:250]},
            )

            if attempt <= max_retries:
                delay_seconds = self._retry_base_seconds * (2 ** (attempt - 1))
                retry_at = now_epoch + delay_seconds
                self._store.save_project_event(
                    ProjectEventCreate(
                        task_id=task_id,
                        event_type="autonomy.retry.scheduled",
                        event_data={
                            "stage": next_stage,
                            "cycle": cycle,
                            "attempt": attempt,
                            "retry_at_epoch": retry_at,
                        },
                    )
                )
                return AutonomyResult(
                    task_id=task_id,
                    status="retry_scheduled",
                    note=(
                        f"Stage '{next_stage}' failed (attempt {attempt}/{max_retries}); "
                        f"retry scheduled in {round(delay_seconds, 2)}s."
                    ),
                )
            self._record_feedback(
                task_id=task_id,
                stage=next_stage,
                strategy=strategy,
                outcome="failed",
            )

            self._store.update_task(task_id, TaskUpdate(status="blocked"))
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task_id,
                    event_type="autonomy.failed",
                    event_data={
                        "stage": next_stage,
                        "cycle": cycle,
                        "attempt": attempt,
                        "error": str(error)[:250],
                    },
                )
            )
            return AutonomyResult(
                task_id=task_id,
                status="failed",
                note=f"Stage '{next_stage}' exceeded retry budget and blocked the task.",
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
        for event in reversed(events):
            if event.event_type != "task.preferences":
                continue
            merged: dict[str, str] = {}
            for key, value in event.event_data.items():
                if isinstance(value, str):
                    merged[key] = value
                elif isinstance(value, (int, float, bool)):
                    merged[key] = str(value)
            return merged
        return {}

    def _next_stage(self, events: list[ProjectEvent], *, cycle: int) -> str | None:
        completed: set[str] = set()
        for event in events:
            if event.event_type != "autonomy.stage.completed":
                continue
            event_cycle = _event_int(event.event_data.get("cycle")) or 1
            if event_cycle != cycle:
                continue
            stage = str(event.event_data.get("stage") or "").strip().lower()
            if stage in AUTONOMY_STAGES:
                completed.add(stage)
        for stage in AUTONOMY_STAGES:
            if stage not in completed:
                return stage
        return None

    def _scheduled_retry_epoch(
        self,
        events: list[ProjectEvent],
        stage: str,
        *,
        cycle: int,
    ) -> float | None:
        for event in reversed(events):
            if event.event_type != "autonomy.retry.scheduled":
                continue
            if str(event.event_data.get("stage") or "").strip().lower() != stage:
                continue
            event_cycle = _event_int(event.event_data.get("cycle")) or 1
            if event_cycle != cycle:
                continue
            retry_epoch = event.event_data.get("retry_at_epoch")
            if isinstance(retry_epoch, (int, float)):
                return float(retry_epoch)
            if isinstance(retry_epoch, str):
                try:
                    return float(retry_epoch)
                except ValueError:
                    return None
        return None

    def _stage_inflight(self, events: list[ProjectEvent], stage: str, *, cycle: int) -> bool:
        started_at: datetime | None = None
        terminal_at: datetime | None = None
        for event in events:
            event_cycle = _event_int(event.event_data.get("cycle")) or 1
            if event_cycle != cycle:
                continue
            event_stage = str(event.event_data.get("stage") or "").strip().lower()
            if event_stage != stage:
                continue
            if event.event_type == "autonomy.stage.started":
                started_at = event.created_at
            elif event.event_type in {"autonomy.stage.completed", "autonomy.stage.failed"}:
                terminal_at = event.created_at
        return started_at is not None and (terminal_at is None or terminal_at < started_at)

    def _failed_attempts(self, events: list[ProjectEvent], stage: str, *, cycle: int) -> int:
        count = 0
        for event in events:
            if event.event_type != "autonomy.stage.failed":
                continue
            event_cycle = _event_int(event.event_data.get("cycle")) or 1
            if event_cycle != cycle:
                continue
            if str(event.event_data.get("stage") or "").strip().lower() == stage:
                count += 1
        return count

    def _resolve_provider(
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
        policy = self._model_policy(prefs)
        explicit_stage = str(prefs.get(f"preferred_provider_{stage}") or "").strip().lower()
        explicit_default = str(prefs.get("preferred_provider") or "").strip().lower()
        if not policy["allow_cross_provider_switching"] and previous_provider in available:
            return previous_provider
        if explicit_stage and explicit_stage in available:
            return self._failure_aware_provider_choice(
                task=task,
                preferred=explicit_stage,
                available=available,
            )
        if explicit_default and explicit_default in available:
            return self._failure_aware_provider_choice(
                task=task,
                preferred=explicit_default,
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

        ordered = self._stage_provider_order(
            stage=stage,
            available=available,
            prefs=prefs,
        )
        recent_failures = self._recent_provider_failures(task.id)
        scored: list[tuple[float, str]] = []
        for item in capability_rows:
            if item.provider not in ordered:
                continue
            score = self._provider_score(
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

    def _resolve_model(
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
            or self._workspace_learning_value(task=task, key="last_successful_model")
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

    def _model_policy(self, prefs: dict[str, str]) -> dict[str, object]:
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
            "maintain_context_continuity": str(
                prefs.get("maintain_context_continuity") or "true"
            )
            .strip()
            .lower()
            != "false",
            "minimum_context_window": _parse_positive_int(
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

    def _resolve_autonomy_mode(self, *, task: Task, prefs: dict[str, str]) -> tuple[str, str]:
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

    def _workspace_learning_value(self, *, task: Task, key: str) -> str:
        if task.workspace_id is None:
            return ""
        workspace = self._store.get_workspace(task.workspace_id)
        if workspace is None:
            return ""
        learning = dict(workspace.metadata.get("learning") or {})
        value = learning.get(key)
        return str(value).strip() if value is not None else ""

    def _failure_aware_provider_choice(
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
        recent_failures = self._recent_provider_failures(task.id)
        if recent_failures.get(preferred, 0) < 2:
            return preferred
        for provider in available:
            if provider == preferred:
                continue
            if recent_failures.get(provider, 0) == 0:
                return provider
        return preferred

    def _recent_provider_failures(self, task_id: UUID) -> dict[str, int]:
        failures: dict[str, int] = {}
        events = self._store.list_project_events(task_id=task_id, limit=100)
        for event in reversed(events[-30:]):
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

    def _provider_score(
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
        score = 0.0
        optimization_goal = str(policy["optimization_goal"] or "balanced")
        minimum_context_window = int(policy["minimum_context_window"] or 0)
        max_latency_tier = str(policy["max_latency_tier"] or "")
        max_cost_tier = str(policy["max_cost_tier"] or "")
        if capability.max_context_tokens < minimum_context_window:
            return -10_000.0
        if max_latency_tier and capability.speed_tier < _latency_floor(max_latency_tier):
            return -5_000.0
        if max_cost_tier and capability.cost_tier > _cost_ceiling(max_cost_tier):
            return -5_000.0

        if explicit_stage and provider == explicit_stage:
            score += 200
        elif explicit_default and provider == explicit_default:
            score += 120

        if previous_provider and provider == previous_provider and bool(
            policy["maintain_context_continuity"]
        ):
            score += 40
        if previous_provider and provider != previous_provider and not bool(
            policy["allow_cross_provider_switching"]
        ):
            score -= 200
        if provider == self._workspace_learning_value(task=task, key="last_successful_provider"):
            score += 24
        complexity = str(getattr(task, "complexity", "") or "").strip().lower()
        task_type = str(getattr(task, "task_type", "") or "").strip().lower()
        if complexity == "high":
            score += capability.quality_tier * 6
        elif complexity == "low":
            score += capability.speed_tier * 4
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

    def _stage_provider_order(
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

    def _latest_run_provider_model(self, task_id: UUID) -> tuple[str | None, str | None]:
        events = self._store.list_project_events(task_id=task_id, limit=100)
        for event in reversed(events):
            if event.event_type not in {"run.completed", "model.switch.completed"}:
                continue
            provider = str(
                event.event_data.get("provider") or event.event_data.get("to_provider") or ""
            ).strip().lower()
            model = str(
                event.event_data.get("target_model") or event.event_data.get("to_model") or ""
            ).strip()
            if provider and model:
                return provider, model
        return None, None

    def _record_model_switch_if_needed(
        self,
        *,
        task_id: UUID,
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

    def _is_local_echo_mode(self, *, provider: str | None, model: str | None) -> bool:
        provider_norm = (provider or "").strip().lower()
        model_norm = (model or "").strip().lower()
        return provider_norm == "local_echo" or model_norm == "local_echo"

    def _resolve_max_retries(self, prefs: dict[str, str]) -> int:
        raw = prefs.get("autonomy_max_retries")
        if raw is None:
            return self._default_max_retries
        try:
            parsed = int(raw)
        except ValueError:
            return self._default_max_retries
        return max(parsed, 0)

    def _current_cycle(self, events: list[ProjectEvent]) -> int:
        for event in reversed(events):
            if event.event_type != "autonomy.cycle.started":
                continue
            cycle = _event_int(event.event_data.get("cycle"))
            if cycle is not None and cycle >= 1:
                return cycle
        return 1

    def _total_step_events(self, events: list[ProjectEvent]) -> int:
        tracked = {"autonomy.stage.completed", "autonomy.stage.failed"}
        return sum(1 for event in events if event.event_type in tracked)

    def _approval_gate_state(
        self,
        *,
        events: list[ProjectEvent],
        stage: str,
        requires_approval: bool,
    ) -> str:
        if not requires_approval:
            return "not_required"
        if stage != "execute":
            return "not_required"

        approval = self._latest_event(events, "autonomy.approval")
        if approval is None:
            return "awaiting"
        approved = _event_bool(approval.event_data.get("approved"))
        return "approved" if approved else "rejected"

    def _ensure_approval_requested(self, *, task_id: UUID, events: list[ProjectEvent]) -> None:
        if self._latest_event(events, "autonomy.approval.requested") is not None:
            return
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="autonomy.approval.requested",
                event_data={"stage": "execute"},
            )
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
        guidance = self._strategy_guidance(strategy)
        sdlc_instruction = ""
        if enforce_sdlc:
            sdlc_instruction = (
                "\nSDLC enforcement is ON. Use this exact checklist and mark status explicitly:\n"
                "- [ ] requirements\n"
                "- [ ] design\n"
                "- [ ] implementation\n"
                "- [ ] tests\n"
                "- [ ] docs\n"
                "- [ ] release\n"
                "Use [x] only when done with concrete evidence."
            )
        if stage == "plan":
            mode = "Replan" if cycle > 1 else "Plan"
            return (
                f"You are Syncore planner ({mode}).\n"
                f"Task title: {task.title}\n"
                f"Task type: {task.task_type}\n"
                f"Complexity: {task.complexity}\n"
                f"Strategy: {strategy}.\n"
                f"Guidance: {guidance}\n"
                f"{sdlc_instruction}\n"
                "Produce a short implementation plan with clear first action, "
                "risks, and checkpoints."
            )
        if stage == "execute":
            preferred = prefs.get("execution_prompt", "").strip()
            recommendation_context = self._recommended_improvement_prompt_context(
                task=task,
                prefs=prefs,
            )
            analysis_context = self._workspace_analysis_prompt_context(task)
            if preferred:
                suffix_parts = []
                if analysis_context:
                    suffix_parts.append(analysis_context)
                if recommendation_context:
                    suffix_parts.append(recommendation_context)
                suffix_parts.append(f"Strategy: {strategy}. Guidance: {guidance}")
                return f"{preferred}\n\n" + "\n\n".join(suffix_parts)
            if recommendation_context:
                return (
                    "You are the Syncore implementation worker.\n"
                    f"Task title: {task.title}\n"
                    f"Task type: {task.task_type}\n"
                    f"Complexity: {task.complexity}\n"
                    f"{recommendation_context}\n\n"
                    f"Strategy: {strategy}. Guidance: {guidance}\n"
                    "Apply the recommended improvement directly. Make the smallest safe change, "
                    "then verify it with the recommended command or the repo runbook."
                )
            if analysis_context:
                return (
                    "You are the Syncore repository analyst.\n"
                    f"Task title: {task.title}\n"
                    f"Task type: {task.task_type}\n"
                    f"Complexity: {task.complexity}\n"
                    f"{analysis_context}\n\n"
                    f"Strategy: {strategy}. Guidance: {guidance}\n"
                    "Choose exactly one safe, high-confidence improvement. "
                    "Return: candidate improvement, required implementation, target files, "
                    "risks, and verification command."
                )
            return _default_prompt(task, strategy=strategy, guidance=guidance)
        return (
            "You are Syncore reviewer.\n"
            f"Review task outcome for: {task.title}\n"
            f"Strategy used: {strategy}. Guidance: {guidance}\n"
            f"{sdlc_instruction}\n"
            f"If acceptable, include exact token: {self._review_pass_keyword}\n"
            "Return pass/fail with key risks, coverage notes, and next verification step."
        )

    def _role_for_stage(self, *, stage: str, execute_role: str, strategy: str) -> str:
        if stage == "plan":
            return "planner"
        if stage == "execute":
            if strategy == "switch_execution_role":
                return "analyst" if execute_role == "coder" else "coder"
            return _normalize_agent_role(execute_role)
        return "reviewer"

    def _stage_quality_gate(
        self,
        *,
        stage: str,
        output_text: str,
        strategy: str,
        enforce_sdlc: bool,
    ) -> dict[str, object]:
        text = (output_text or "").strip()
        minimum = self._execute_min_chars
        if stage == "plan":
            minimum = self._plan_min_chars
        elif stage == "review":
            minimum = self._review_min_chars

        reasons: list[str] = []
        score = 100
        if len(text) < minimum:
            reasons.append(f"Too short ({len(text)} < {minimum}).")
            score -= 45
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if stage == "plan":
            has_step_shape = any(
                line.startswith(("-", "*")) or line[:2].isdigit()
                for line in lines
            )
            if not has_step_shape:
                reasons.append("Plan missing explicit step list.")
                score -= 20
            if "risk" not in text.lower():
                reasons.append("Plan missing risk notes.")
                score -= 10
            if enforce_sdlc:
                missing = _missing_sdlc_topics(text)
                if missing:
                    reasons.append(
                        f"Plan missing SDLC coverage for: {', '.join(missing)}."
                    )
                    score -= min(10 + (len(missing) * 5), 35)
        if stage == "execute":
            has_actionable = (
                ("```" in text)
                or ("$ " in text)
                or ("def " in text)
                or ("class " in text)
            )
            if not has_actionable:
                reasons.append("Execute output missing concrete code/command artifacts.")
                score -= 25
            if enforce_sdlc and "test" not in text.lower() and "verify" not in text.lower():
                reasons.append("Execute output missing test/verification evidence.")
                score -= 20
        if stage == "review":
            lowered = text.lower()
            if "pass" not in lowered and "fail" not in lowered:
                reasons.append("Review missing explicit pass/fail.")
                score -= 20
            if "risk" not in lowered:
                reasons.append("Review missing risk analysis.")
                score -= 10
            if self._review_pass_keyword and self._review_pass_keyword.upper() not in text.upper():
                reasons.append(f"Missing review pass keyword '{self._review_pass_keyword}'.")
                score -= 40
            if enforce_sdlc:
                checklist_status = _extract_sdlc_checklist_status(text)
                missing_checks = [
                    item for item in SDLC_CHECKLIST_ITEMS if not checklist_status.get(item, False)
                ]
                if missing_checks:
                    reasons.append(
                        f"Review checklist incomplete: {', '.join(missing_checks)}."
                    )
                    score -= min(12 + (len(missing_checks) * 4), 45)
        if strategy == "raise_verification":
            if "test" not in text.lower() and "verify" not in text.lower():
                reasons.append("Verification-focused strategy requires tests/verification notes.")
                score -= 15

        score = max(score, 0)
        return {"passed": score >= 70, "score": score, "reasons": reasons}

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
        if not _as_bool(prefs.get("auto_spawn")):
            return
        existing_events = self._store.list_project_events(task_id=task.id, limit=500)
        if self._latest_event(existing_events, "autonomy.subtasks.spawned") is not None:
            return

        count = _parse_positive_int(prefs.get("auto_spawn_count"), default=3, maximum=8)
        templates = [
            (
                "Requirements and design pass",
                "analysis",
                "false",
                (
                    "Inspect the repository and identify one safe, high-confidence improvement. "
                    "Do not modify files. Summarize the candidate change, target files, risks, and "
                    "the verification command the implementation pass should run."
                ),
            ),
            (
                "Implementation pass",
                "implementation",
                prefs.get("workspace_execution_enabled", "true"),
                prefs.get("execution_prompt", ""),
            ),
            (
                "Verification and release pass",
                "review",
                "false",
                (
                    "Review the selected improvement and its verification evidence. "
                    "Do not modify files. State whether the change is safe to ship, "
                    "what risks remain, and what final check "
                    "or note should be recorded."
                ),
            ),
            (
                "Documentation and polish pass",
                "integration",
                "false",
                (
                    "Review whether any docs or operator notes should be updated for the chosen "
                    "improvement. Do not modify files unless explicitly required by the task."
                ),
            ),
        ]
        selected = templates[:count]
        spawned_ids: list[str] = []
        for title_suffix, task_type, workspace_enabled, child_execution_prompt in selected:
            child = self._store.create_task(
                TaskCreate(
                    title=f"{task.title} :: {title_suffix}",
                    task_type=task_type,  # type: ignore[arg-type]
                    complexity=task.complexity,
                    workspace_id=task.workspace_id,
                )
            )
            child_event_data: dict[str, str] = dict(prefs)
            child_event_data.update(
                {
                    "parent_task_id": str(task.id),
                    "preferred_agent_role": prefs.get("preferred_agent_role", "coder"),
                    "preferred_provider": prefs.get("preferred_provider", self._default_provider),
                    "preferred_model": prefs.get("preferred_model", self._default_model),
                    "execution_prompt": child_execution_prompt,
                    "requires_approval": prefs.get("requires_approval", "false"),
                    "sdlc_enforce": prefs.get("sdlc_enforce", "false"),
                    "workspace_execution_enabled": workspace_enabled,
                    "auto_spawn": "false",
                }
            )
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=child.id,
                    event_type="task.preferences",
                    event_data=child_event_data,
                )
            )
            spawned_ids.append(str(child.id))

        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.subtasks.spawned",
                event_data={
                    "count": len(spawned_ids),
                    "child_task_ids": ",".join(spawned_ids),
                },
            )
        )

    def _select_replan_strategy(
        self,
        *,
        events: list[ProjectEvent],
        stage: str,
        cycle: int,
        execute_role: str,
    ) -> str:
        if cycle <= 1:
            return "default"
        recent_fail = self._latest_event(events, "autonomy.quality.failed")
        reason = str((recent_fail.event_data.get("reason") if recent_fail else "") or "").lower()
        candidates = [
            "tighten_scope",
            "increase_detail",
            "raise_verification",
            "switch_execution_role",
        ]
        if "short" in reason:
            candidates = [
                "increase_detail",
                "tighten_scope",
                "raise_verification",
                "switch_execution_role",
            ]
        elif "risk" in reason or stage == "review":
            candidates = [
                "raise_verification",
                "increase_detail",
                "tighten_scope",
                "switch_execution_role",
            ]
        elif execute_role == "coder":
            candidates = [
                "switch_execution_role",
                "increase_detail",
                "tighten_scope",
                "raise_verification",
            ]
        return self._best_strategy_from_feedback(candidates)

    def _best_strategy_from_feedback(self, candidates: list[str]) -> str:
        feedback = self._store.list_project_events(task_id=None, limit=500)
        scores: dict[str, int] = {name: 0 for name in AUTONOMY_STRATEGIES}
        for event in feedback:
            if event.event_type != "autonomy.feedback":
                continue
            strategy = str(event.event_data.get("strategy") or "").strip()
            outcome = str(event.event_data.get("outcome") or "").strip()
            if strategy not in scores:
                continue
            if outcome == "success":
                scores[strategy] += 3
            elif outcome == "quality_failed":
                scores[strategy] -= 2
            elif outcome == "failed":
                scores[strategy] -= 3
        best = max(candidates, key=lambda item: scores.get(item, 0))
        return best if best in AUTONOMY_STRATEGIES else "default"

    def _strategy_guidance(self, strategy: str) -> str:
        if strategy == "tighten_scope":
            return "Break work into smaller validated increments and avoid broad refactors."
        if strategy == "increase_detail":
            return "Increase implementation detail and include explicit step-by-step artifacts."
        if strategy == "raise_verification":
            return "Prioritize tests, checks, and explicit verification evidence."
        if strategy == "switch_execution_role":
            return "Shift execution perspective to reduce repeated blind spots."
        return "Deliver concise, actionable, and verifiable output."

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
        parent_id = self._parse_uuid(prefs.get("parent_task_id"))
        if parent_id is None:
            return
        if task.task_type != "analysis":
            return
        recommendation = self._extract_recommended_improvement(output_text)
        if self._recommendation_needs_workspace_fallback(recommendation):
            recommendation = self._fallback_recommended_improvement(task, recommendation)
        if not recommendation["summary"] and not recommendation["action"]:
            return
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
        parent_id = self._parse_uuid(prefs.get("parent_task_id"))
        if parent_id is None:
            return None
        sibling_state = self._recommended_improvement_state(parent_id)
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
            return AutonomyResult(
                task_id=task.id,
                status="in_progress",
                note=str(sibling_state["note"]),
            )
        return None

    def _recommended_improvement_prompt_context(
        self,
        *,
        task: Task,
        prefs: dict[str, str],
    ) -> str:
        if task.task_type != "implementation":
            return ""
        parent_id = self._parse_uuid(prefs.get("parent_task_id"))
        if parent_id is None:
            return ""
        sibling_state = self._recommended_improvement_state(parent_id)
        if sibling_state["status"] != "ready":
            return ""
        event = sibling_state["event"]
        summary = str(event.event_data.get("summary") or "").strip()
        action = str(event.event_data.get("action") or "").strip()
        target_files = str(event.event_data.get("target_files") or "").strip()
        verification = str(event.event_data.get("verification_command") or "").strip()
        risks = str(event.event_data.get("risks") or "").strip()
        context_lines = ["Recommended improvement baton from analysis child:"]
        if summary:
            context_lines.append(f"- Candidate improvement: {summary}")
        if action:
            context_lines.append(f"- Required implementation: {action}")
        if target_files:
            context_lines.append(f"- Suggested files: {target_files}")
        if verification:
            context_lines.append(f"- Verification command: {verification}")
        if risks:
            context_lines.append(f"- Risks/constraints: {risks}")
        context_lines.append(
            "- Do not re-scope the task. "
            "Act on this recommendation unless the repo state proves it invalid."
        )
        return "\n".join(context_lines)

    def _recommended_improvement_state(self, parent_id: UUID) -> dict[str, object]:
        child_ids = self._spawned_child_ids(parent_id)
        analysis_children: list[Task] = []
        for child_id in child_ids:
            child = self._store.get_task(child_id)
            if child is None or child.task_type != "analysis":
                continue
            analysis_children.append(child)
            child_events = self._store.list_project_events(task_id=child.id, limit=200)
            recommendation = self._latest_event(child_events, "autonomy.recommended_improvement")
            if recommendation is not None:
                return {"status": "ready", "event": recommendation, "task": child}
        if not analysis_children:
            return {"status": "ready", "note": "No analysis sibling present."}
        blocked = [child for child in analysis_children if child.status == "blocked"]
        if blocked:
            return {
                "status": "blocked",
                "note": "Analysis child blocked before producing a recommended improvement baton.",
            }
        pending = [child for child in analysis_children if child.status != "completed"]
        if pending:
            return {
                "status": "waiting",
                "note": "Waiting for analysis child to produce a recommended improvement baton.",
            }
        for child in analysis_children:
            baton = self._store.get_latest_baton_packet(child.id)
            if baton is not None:
                summary = baton.summary.strip()
                action = baton.payload.next_best_action.strip()
                target_files = ", ".join(baton.payload.relevant_artifacts[:10])
                event = ProjectEvent(
                    id=UUID(int=0),
                    task_id=child.id,
                    event_type="autonomy.recommended_improvement",
                    event_data={
                        "summary": summary[:250],
                        "action": action[:250],
                        "target_files": target_files[:250],
                        "verification_command": "",
                        "risks": "; ".join(baton.payload.constraints[:6])[:250],
                    },
                    created_at=datetime.now(timezone.utc),
                )
                return {"status": "ready", "event": event, "task": child}
        return {
            "status": "blocked",
            "note": "Analysis child completed without a concrete recommended improvement baton.",
        }

    def _spawned_child_ids(self, parent_id: UUID) -> list[UUID]:
        events = self._store.list_project_events(task_id=parent_id, limit=500)
        spawned = self._latest_event(events, "autonomy.subtasks.spawned")
        if spawned is None:
            return []
        raw_ids = str(spawned.event_data.get("child_task_ids") or "").strip()
        ids: list[UUID] = []
        for raw in (item.strip() for item in raw_ids.split(",") if item.strip()):
            parsed = self._parse_uuid(raw)
            if parsed is not None:
                ids.append(parsed)
        return ids

    def _extract_recommended_improvement(self, output_text: str) -> dict[str, object]:
        text = (output_text or "").strip()
        summary = self._extract_first_match(
            text,
            [
                r"(?im)^(?:candidate improvement|recommended improvement|improvement)\s*:\s*(.+)$",
                r"(?im)^(?:summary|change summary)\s*:\s*(.+)$",
            ],
        )
        action = self._extract_first_match(
            text,
            [
                r"(?im)^(?:next best action|required implementation|implementation)\s*:\s*(.+)$",
                r"(?im)^(?:action|do this)\s*:\s*(.+)$",
            ],
        )
        verification = self._extract_first_match(
            text,
            [
                r"(?im)^(?:verification command|verify(?: with)?|test command)\s*:\s*(.+)$",
            ],
        )
        target_files = self._extract_paths(text)
        risks = self._extract_list_items(
            text,
            headers=("risk", "risks", "constraints"),
        )
        if not summary:
            summary = shorten(" ".join(text.split()), width=220, placeholder=" ...")
        if not action:
            action = summary
        return {
            "summary": summary.strip(),
            "action": action.strip(),
            "verification": verification.strip(),
            "target_files": target_files,
            "risks": risks,
        }

    def _recommendation_needs_workspace_fallback(
        self, recommendation: dict[str, object]
    ) -> bool:
        text = " ".join(
            [
                str(recommendation.get("summary") or ""),
                str(recommendation.get("action") or ""),
            ]
        ).lower()
        generic_markers = (
            "don't yet have repository contents",
            "do not have repository contents",
            "please provide",
            "need more context",
            "artifact/context reference",
        )
        return any(marker in text for marker in generic_markers)

    def _fallback_recommended_improvement(
        self,
        task: Task,
        recommendation: dict[str, object],
    ) -> dict[str, object]:
        if task.workspace_id is None:
            return recommendation
        workspace = self._store.get_workspace(task.workspace_id)
        if workspace is None:
            return recommendation
        metadata = dict(workspace.metadata or {})
        runbook = dict(metadata.get("workspace_runbook") or {})
        root = Path(workspace.root_path).resolve()
        verification = (
            self._string_list(runbook.get("test_commands"))[:1]
            or self._string_list(runbook.get("runbook_commands"))[:1]
        )
        verify_cmd = verification[0] if verification else ""
        syncore_contract = root / "syncore.yaml"
        if not syncore_contract.exists():
            return {
                "summary": "Add a repo-specific syncore.yaml contract for this repository.",
                "action": (
                    "Create syncore.yaml with the detected test, build, and lint commands so "
                    "future Syncore runs can inspect and verify this repo deterministically."
                ),
                "verification": verify_cmd,
                "target_files": ["syncore.yaml"],
                "risks": ["Keep the contract additive and match real repo commands exactly."],
            }
        return {
            "summary": (
                "Tighten the existing syncore.yaml contract using the current workspace scan."
            ),
            "action": (
                "Update syncore.yaml so the recorded commands and important files match the repo's "
                "actual test and verification flow."
            ),
            "verification": verify_cmd,
            "target_files": ["syncore.yaml"],
            "risks": ["Keep edits limited to syncore.yaml and preserve working repo commands."],
        }

    def _workspace_analysis_prompt_context(self, task: Task) -> str:
        if task.task_type != "analysis" or task.workspace_id is None:
            return ""
        workspace = self._store.get_workspace(task.workspace_id)
        if workspace is None:
            return ""
        metadata = dict(workspace.metadata or {})
        runbook = dict(metadata.get("workspace_runbook") or {})
        root = Path(workspace.root_path).resolve()
        summary_lines = ["Workspace scan summary:"]
        for label, key in [
            ("Languages", "languages"),
            ("Frameworks", "frameworks"),
            ("Package managers", "package_managers"),
            ("Important files", "important_files"),
            ("Docs", "docs"),
        ]:
            values = self._string_list(metadata.get(key))
            if values:
                summary_lines.append(f"- {label}: {', '.join(values[:8])}")
        test_commands = self._string_list(runbook.get("test_commands"))
        if test_commands:
            summary_lines.append(f"- Test commands: {', '.join(test_commands[:4])}")
        root_files = self._workspace_root_files(root)
        if root_files:
            summary_lines.append(f"- Root files: {', '.join(root_files[:12])}")
        previews = self._workspace_file_previews(root, root_files)
        if previews:
            summary_lines.append("Key file previews:")
            summary_lines.extend(previews)
        if not (root / "syncore.yaml").exists():
            summary_lines.append("- syncore.yaml is currently missing from the repo root.")
        return "\n".join(summary_lines)

    def _workspace_root_files(self, root: Path) -> list[str]:
        try:
            items = sorted(path.name for path in root.iterdir() if path.is_file())
        except OSError:
            return []
        return items[:20]

    def _workspace_file_previews(self, root: Path, root_files: list[str]) -> list[str]:
        preview_targets = [
            "README.md",
            "pyproject.toml",
            "package.json",
            "requirements.txt",
            "setup.cfg",
            "Cargo.toml",
            "go.mod",
        ]
        previews: list[str] = []
        for name in preview_targets:
            if name not in root_files:
                continue
            path = root / name
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            compact = shorten(" ".join(text.split()), width=220, placeholder=" ...")
            previews.append(f"- {name}: {compact}")
        return previews[:6]

    def _string_list(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, tuple):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return []

    def _extract_first_match(self, text: str, patterns: list[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return str(match.group(1)).strip()
        return ""

    def _extract_paths(self, text: str) -> list[str]:
        candidates = re.findall(
            r"\b(?:[\w.-]+/)*[\w.-]+\.(?:py|ts|tsx|js|jsx|json|md|toml|yaml|yml|ini|cfg|txt|rs|go|java|kt|sh)\b",
            text,
        )
        seen: set[str] = set()
        paths: list[str] = []
        for item in candidates:
            if item not in seen:
                seen.add(item)
                paths.append(item)
        return paths[:12]

    def _extract_list_items(self, text: str, *, headers: tuple[str, ...]) -> list[str]:
        lines = [line.strip() for line in text.splitlines()]
        items: list[str] = []
        capture = False
        for line in lines:
            normalized = line.lower().rstrip(":")
            if normalized in headers:
                capture = True
                continue
            if capture:
                if not line:
                    break
                if line.startswith(("-", "*")):
                    items.append(line.lstrip("-* ").strip())
                    continue
                if re.match(r"^\d+\.\s+", line):
                    items.append(re.sub(r"^\d+\.\s+", "", line).strip())
                    continue
                break
        return [item for item in items if item][:8]

    def _parse_uuid(self, raw: str | None) -> UUID | None:
        value = (raw or "").strip()
        if not value:
            return None
        try:
            return UUID(value)
        except ValueError:
            return None

    def _finalize_task(self, task_id: UUID) -> None:
        task = self._store.get_task(task_id)
        if task is not None and task.status != "completed":
            self._store.update_task(task_id, TaskUpdate(status="completed"))
        events = self._store.list_project_events(task_id=task_id, limit=500)
        if self._latest_event(events, "autonomy.completed") is None:
            latest_run_id = self._latest_stage_completion(events)
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task_id,
                    event_type="autonomy.completed",
                    event_data={"run_id": str(latest_run_id) if latest_run_id else ""},
                )
            )
        self._generate_digest_event(task_id)

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

    def _child_gate_status(
        self, *, task: Task, events: list[ProjectEvent]
    ) -> dict[str, str]:
        spawned = self._latest_event(events, "autonomy.subtasks.spawned")
        if spawned is None:
            return {"mode": "none"}
        raw_ids = str(spawned.event_data.get("child_task_ids") or "").strip()
        if not raw_ids:
            return {"mode": "none"}
        child_ids = [item.strip() for item in raw_ids.split(",") if item.strip()]
        if not child_ids:
            return {"mode": "none"}

        blocked: list[str] = []
        completed = 0
        active = 0
        for raw in child_ids:
            try:
                child_id = UUID(raw)
            except ValueError:
                continue
            child = self._store.get_task(child_id)
            if child is None:
                continue
            if child.status == "completed":
                completed += 1
            elif child.status == "blocked":
                blocked.append(str(child.id))
            else:
                active += 1

        if blocked:
            return {
                "mode": "children_failed",
                "note": f"Child tasks blocked: {', '.join(blocked[:5])}.",
            }
        if completed >= len(child_ids) and len(child_ids) > 0:
            if self._latest_event(events, "autonomy.children.completed") is None:
                self._store.save_project_event(
                    ProjectEventCreate(
                        task_id=task.id,
                        event_type="autonomy.children.completed",
                        event_data={"count": len(child_ids)},
                    )
                )
            return {"mode": "children_completed", "note": "All child tasks completed."}
        return {
            "mode": "awaiting_children",
            "note": f"Waiting for child tasks: completed={completed}, active={active}.",
        }

    def _generate_digest_event(self, task_id: UUID) -> None:
        events = self._store.list_project_events(task_id=task_id, limit=200)
        digest = self._digest_service.generate_digest(
            task_id=task_id,
            events=events,
            latest_baton=self._store.get_latest_baton_packet(task_id),
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="analyst.digest.generated",
                event_data={
                    "headline": digest.headline[:250],
                    "risk_level": digest.risk_level,
                    "total_events": digest.total_events,
                },
            )
        )


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
