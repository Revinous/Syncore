from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from packages.contracts.python.models import (
    BatonPacketCreate,
    BatonPayload,
    ProjectEvent,
    ProjectEventCreate,
    RoutingRequest,
    RunExecutionRequest,
    Task,
    TaskUpdate,
)
from services.analyst.digest import AnalystDigestService
from services.memory import MemoryStoreProtocol

from app.config import Settings
from app.services.routing_service import RoutingService
from app.services.run_execution_service import RunExecutionService
from app.store_factory import build_memory_store

AUTONOMY_STAGES = ("plan", "execute", "review")


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

        provider = self._resolve_provider(prefs)
        model = self._resolve_model(provider, prefs)
        max_retries = self._resolve_max_retries(prefs)
        prompt = self._prompt_for_stage(stage=next_stage, task=task, prefs=prefs, cycle=cycle)
        stage_role = self._role_for_stage(stage=next_stage, execute_role=execute_role)

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
            run = self._run_execution_service.execute(request)
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
                    },
                )
            )

            if next_stage == "review":
                review_failed = (
                    self._review_pass_keyword
                    and self._review_pass_keyword.upper() not in run.output_text.upper()
                )
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
                self._finalize_task(task_id)
                return AutonomyResult(
                    task_id=task_id,
                    status="completed",
                    run_id=run.run_id,
                    note="Autonomy review passed and task finalized.",
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
                    },
                )
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
    ) -> str:
        if stage == "plan":
            mode = "Replan" if cycle > 1 else "Plan"
            return (
                f"You are Syncore planner ({mode}).\n"
                f"Task title: {task.title}\n"
                f"Task type: {task.task_type}\n"
                f"Complexity: {task.complexity}\n"
                "Produce a short implementation plan with clear first action."
            )
        if stage == "execute":
            preferred = prefs.get("execution_prompt", "").strip()
            if preferred:
                return preferred
            return _default_prompt(task)
        return (
            "You are Syncore reviewer.\n"
            f"Review task outcome for: {task.title}\n"
            f"If acceptable, include exact token: {self._review_pass_keyword}\n"
            "Return pass/fail with key risks and next verification step."
        )

    def _role_for_stage(self, *, stage: str, execute_role: str) -> str:
        if stage == "plan":
            return "planner"
        if stage == "execute":
            return _normalize_agent_role(execute_role)
        return "reviewer"

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

    def _generate_digest_event(self, task_id: UUID) -> None:
        events = self._store.list_project_events(task_id=task_id, limit=200)
        digest = self._digest_service.generate_digest(task_id=task_id, events=events)
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


def _default_prompt(task: Task) -> str:
    return (
        "You are the autonomous implementation worker.\n"
        f"Task title: {task.title}\n"
        f"Task type: {task.task_type}\n"
        f"Complexity: {task.complexity}\n"
        "Deliver a concrete implementation plan and the first executable step."
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
