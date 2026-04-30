from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
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
        requires_approval = _as_bool(prefs.get("requires_approval"))
        if (
            self._workspace_auto_approve_low_risk
            and task.workspace_id is not None
            and task.complexity == "low"
        ):
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

        strategy = self._select_replan_strategy(
            events=events,
            stage=next_stage,
            cycle=cycle,
            execute_role=execute_role,
        )
        provider = self._resolve_provider(prefs)
        model = self._resolve_model(provider, prefs)
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
            details={"role": stage_role, "provider": provider or "", "model": model},
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
                    dry_run=False,
                )
                run = SimpleNamespace(
                    run_id=None,
                    provider=str(workspace_result.get("provider") or (provider or "")),
                    target_model=str(workspace_result.get("target_model") or model),
                    output_text=str(workspace_result.get("digest") or workspace_result),
                )
            else:
                run = self._run_execution_service.execute(request)
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

    def _resolve_provider(self, prefs: dict[str, str]) -> str | None:
        candidate = (
            prefs.get("preferred_provider") or self._default_provider or ""
        ).strip().lower()
        if not candidate or candidate == "other":
            return None
        return candidate

    def _resolve_model(self, provider: str | None, prefs: dict[str, str]) -> str:
        preferred_model = (prefs.get("preferred_model") or "").strip()
        if preferred_model:
            return preferred_model
        if provider == "local_echo" or self._default_provider == "local_echo":
            return "local_echo"
        return self._default_model

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
            if preferred:
                return f"{preferred}\n\nStrategy: {strategy}. Guidance: {guidance}"
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
            ("Requirements and design pass", "analysis"),
            ("Implementation pass", "implementation"),
            ("Verification and release pass", "review"),
            ("Documentation and polish pass", "integration"),
        ]
        selected = templates[:count]
        spawned_ids: list[str] = []
        for title_suffix, task_type in selected:
            child = self._store.create_task(
                TaskCreate(
                    title=f"{task.title} :: {title_suffix}",
                    task_type=task_type,  # type: ignore[arg-type]
                    complexity=task.complexity,
                    workspace_id=task.workspace_id,
                )
            )
            child_event_data: dict[str, str] = {
                "parent_task_id": str(task.id),
                "preferred_agent_role": prefs.get("preferred_agent_role", "coder"),
                "preferred_provider": prefs.get("preferred_provider", self._default_provider),
                "preferred_model": prefs.get("preferred_model", self._default_model),
                "execution_prompt": prefs.get("execution_prompt", ""),
                "requires_approval": prefs.get("requires_approval", "false"),
                "sdlc_enforce": prefs.get("sdlc_enforce", "false"),
                "auto_spawn": "false",
            }
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
