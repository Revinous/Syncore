from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.contracts.python.models import ProjectEventCreate, TaskUpdate

from app.services.autonomy_stage_models import AutonomyStageContext


class AutonomyStageFailureOutcomeHandler:
    def __init__(
        self,
        *,
        store,
        failure_handler,
        task_gate,
        retry_base_seconds: float,
        low_info_stop_enabled: bool,
        record_feedback,
        save_snapshot,
    ) -> None:
        self._store = store
        self._failure_handler = failure_handler
        self._task_gate = task_gate
        self._retry_base_seconds = retry_base_seconds
        self._low_info_stop_enabled = low_info_stop_enabled
        self._record_feedback = record_feedback
        self._save_snapshot = save_snapshot

    def handle_stage_failure(
        self,
        *,
        context: AutonomyStageContext,
        events: list[Any],
        strategy: str,
        error: Exception,
    ) -> dict[str, Any]:
        attempt = self._task_gate.failed_attempts(events, context.stage, cycle=context.cycle) + 1
        failure = self._failure_handler.classify_failure(
            task_id=context.task.id,
            stage=context.stage,
            cycle=context.cycle,
            error=error,
        )
        if self._low_info_stop_enabled and self._failure_handler.is_low_information_failure(
            task_id=context.task.id,
            stage=context.stage,
            failure_signature=str(failure.get("signature") or ""),
        ):
            self._store.update_task(context.task.id, TaskUpdate(status="blocked"))
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=context.task.id,
                    event_type="autonomy.low_information_gain.detected",
                    event_data={
                        "stage": context.stage,
                        "cycle": context.cycle,
                        "failure_category": str(failure.get("category") or ""),
                        "signature": str(failure.get("signature") or "")[:250],
                    },
                )
            )
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=context.task.id,
                    event_type="autonomy.stopped.low_information_gain",
                    event_data={
                        "stage": context.stage,
                        "cycle": context.cycle,
                        "reason": str(failure.get("reason") or str(error))[:250],
                    },
                )
            )
            return {
                "status": "failed",
                "run_id": None,
                "note": f"Stopped '{context.stage}' after repeated equivalent failures.",
            }
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=context.task.id,
                event_type="autonomy.stage.failed",
                event_data={
                    "stage": context.stage,
                    "cycle": context.cycle,
                    "attempt": attempt,
                    "error": str(error)[:250],
                    "strategy": strategy,
                    "failure_category": str(failure.get("category") or ""),
                    "retry_allowed": bool(failure.get("retry_allowed")),
                    "should_replan": bool(failure.get("should_replan")),
                    "recommended_strategy": str(failure.get("strategy") or "")[:120],
                    "signature": str(failure.get("signature") or "")[:250],
                },
            )
        )
        self._save_snapshot(
            task_id=context.task.id,
            cycle=context.cycle,
            stage=context.stage,
            state="failed",
            strategy=strategy,
            quality_score=0,
            details={
                "attempt": attempt,
                "error": str(error)[:250],
                "failure_category": str(failure.get("category") or ""),
                "recommended_strategy": str(failure.get("strategy") or ""),
                "signature": str(failure.get("signature") or "")[:250],
            },
        )
        if bool(failure.get("retry_allowed")) and attempt <= context.max_retries:
            delay_seconds = self._retry_base_seconds * (2 ** (attempt - 1))
            retry_at = datetime.now(timezone.utc).timestamp() + delay_seconds
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=context.task.id,
                    event_type="autonomy.retry.scheduled",
                    event_data={
                        "stage": context.stage,
                        "cycle": context.cycle,
                        "attempt": attempt,
                        "retry_at_epoch": retry_at,
                        "failure_category": str(failure.get("category") or ""),
                    },
                )
            )
            return {
                "status": "retry_scheduled",
                "run_id": None,
                "note": (
                    f"Stage '{context.stage}' failed (attempt {attempt}/{context.max_retries}); "
                    f"retry scheduled in {round(delay_seconds, 2)}s."
                ),
            }
        if bool(failure.get("should_replan")) and context.cycle < context.max_cycles:
            next_cycle = context.cycle + 1
            self._record_feedback(
                task_id=context.task.id,
                stage=context.stage,
                strategy=strategy,
                outcome="replan_required",
            )
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=context.task.id,
                    event_type="autonomy.cycle.started",
                    event_data={
                        "cycle": next_cycle,
                        "mode": "replan",
                        "failure_category": str(failure.get("category") or ""),
                    },
                )
            )
            return {
                "status": "replanning",
                "run_id": None,
                "note": f"Stage '{context.stage}' failed; replan started for cycle {next_cycle}.",
            }
        self._record_feedback(
            task_id=context.task.id,
            stage=context.stage,
            strategy=strategy,
            outcome="failed",
        )
        self._store.update_task(context.task.id, TaskUpdate(status="blocked"))
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=context.task.id,
                event_type="autonomy.failed",
                event_data={
                    "stage": context.stage,
                    "cycle": context.cycle,
                    "attempt": attempt,
                    "error": str(error)[:250],
                },
            )
        )
        return {
            "status": "failed",
            "run_id": None,
            "note": f"Stage '{context.stage}' exceeded retry budget and blocked the task.",
        }
