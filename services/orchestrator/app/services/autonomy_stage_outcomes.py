from __future__ import annotations

from typing import Any

from packages.contracts.python.models import ProjectEventCreate, TaskUpdate

from app.services.autonomy_stage_failures import AutonomyStageFailureOutcomeHandler
from app.services.autonomy_stage_models import AutonomyStageContext


class AutonomyStageOutcomeHandler:
    def __init__(
        self,
        *,
        store,
        quality_gate,
        failure_handler,
        task_gate,
        retry_base_seconds: float,
        review_pass_keyword: str,
        low_info_stop_enabled: bool,
        parse_uuid,
        record_feedback,
        persist_execute_plan,
        persist_stage_handoff_artifacts,
        spawn_subtasks_once,
        child_gate_status,
        finalize_task,
        save_snapshot,
    ) -> None:
        self._store = store
        self._quality_gate = quality_gate
        self._failure_handler = failure_handler
        self._task_gate = task_gate
        self._retry_base_seconds = retry_base_seconds
        self._review_pass_keyword = review_pass_keyword
        self._low_info_stop_enabled = low_info_stop_enabled
        self._parse_uuid = parse_uuid
        self._record_feedback = record_feedback
        self._persist_execute_plan = persist_execute_plan
        self._persist_stage_handoff_artifacts = persist_stage_handoff_artifacts
        self._spawn_subtasks_once = spawn_subtasks_once
        self._child_gate_status = child_gate_status
        self._finalize_task = finalize_task
        self._save_snapshot = save_snapshot
        self._failures = AutonomyStageFailureOutcomeHandler(
            store=store,
            failure_handler=failure_handler,
            task_gate=task_gate,
            retry_base_seconds=retry_base_seconds,
            low_info_stop_enabled=low_info_stop_enabled,
            record_feedback=record_feedback,
            save_snapshot=save_snapshot,
        )

    def record_stage_started_snapshot(
        self,
        *,
        task_id,
        cycle: int,
        stage: str,
        strategy: str,
        stage_role: str,
        provider: str | None,
        model: str,
        previous_provider: str | None,
        previous_model: str | None,
    ) -> None:
        self._save_snapshot(
            task_id=task_id,
            cycle=cycle,
            stage=stage,
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

    def record_stage_completed(
        self,
        *,
        context: AutonomyStageContext,
        run,
        strategy: str,
        checklist_status: dict[str, bool],
        quality: dict[str, object],
    ) -> None:
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=context.task.id,
                event_type="autonomy.stage.completed",
                event_data={
                    "stage": context.stage,
                    "cycle": context.cycle,
                    "run_id": str(run.run_id),
                    "provider": run.provider,
                    "target_model": run.target_model,
                    "strategy": strategy,
                },
            )
        )
        self._save_snapshot(
            task_id=context.task.id,
            cycle=context.cycle,
            stage=context.stage,
            state="completed",
            strategy=strategy,
            quality_score=int(quality["score"]),
            details={
                "quality_passed": bool(quality["passed"]),
                "quality_reasons": "; ".join(quality["reasons"]),
                "run_id": str(run.run_id),
                "sdlc_enforced": context.enforce_sdlc,
                "sdlc_checked_count": sum(1 for value in checklist_status.values() if value),
            },
        )

    def handle_quality_outcome(
        self,
        *,
        context: AutonomyStageContext,
        run,
        quality: dict[str, object],
        strategy: str,
    ) -> dict[str, Any] | None:
        if bool(quality["passed"]):
            return None
        task_id = context.task.id
        quality_reason = "; ".join(quality["reasons"])
        quality_signature = self._quality_gate.quality_failure_signature(
            task_id=task_id,
            stage=context.stage,
            reason=quality_reason,
        )
        if (
            self._low_info_stop_enabled
            and self._quality_gate.is_low_information_quality_failure(
                task_id=task_id,
                stage=context.stage,
                signature=quality_signature,
            )
        ):
            self._store.update_task(task_id, TaskUpdate(status="blocked"))
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task_id,
                    event_type="autonomy.low_information_gain.detected",
                    event_data={
                        "stage": context.stage,
                        "cycle": context.cycle,
                        "failure_category": "quality_gate_failure",
                        "signature": quality_signature,
                    },
                )
            )
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task_id,
                    event_type="autonomy.stopped.low_information_gain",
                    event_data={
                        "stage": context.stage,
                        "cycle": context.cycle,
                        "reason": quality_reason[:250],
                    },
                )
            )
            return {
                "status": "failed",
                "run_id": run.run_id,
                "note": (
                    f"Stopped '{context.stage}' after repeated low-information quality failures."
                ),
            }
        if context.cycle >= context.max_cycles:
            self._store.update_task(task_id, TaskUpdate(status="blocked"))
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=task_id,
                    event_type="autonomy.failed",
                    event_data={
                        "stage": context.stage,
                        "cycle": context.cycle,
                        "error": quality_reason,
                    },
                )
            )
            return {
                "status": "failed",
                "run_id": run.run_id,
                "note": f"Quality gate failed at '{context.stage}' and max cycles reached.",
            }
        next_cycle = context.cycle + 1
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="autonomy.quality.failed",
                event_data={
                    "stage": context.stage,
                    "cycle": context.cycle,
                    "reason": quality_reason[:250],
                    "next_cycle": next_cycle,
                    "strategy": strategy,
                    "quality_score": int(quality["score"]),
                    "signature": quality_signature,
                },
            )
        )
        self._record_feedback(
            task_id=task_id,
            stage=context.stage,
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
        return {
            "status": "replanning",
            "run_id": run.run_id,
            "note": f"Quality gate failed at '{context.stage}'; moved to cycle {next_cycle}.",
        }

    def handle_review_outcome(
        self,
        *,
        context: AutonomyStageContext,
        run,
        strategy: str,
        local_echo_mode: bool,
    ) -> dict[str, Any] | None:
        review_failed = (
            self._review_pass_keyword
            and self._review_pass_keyword.upper() not in run.output_text.upper()
        )
        if local_echo_mode:
            review_failed = False
        if not review_failed:
            self._record_feedback(
                task_id=context.task.id,
                stage=context.stage,
                strategy=strategy,
                outcome="success",
            )
            self._quality_gate.record_meaningful_change_assessment(
                task=context.task,
                prefs=context.prefs,
                review_output=run.output_text,
                parse_uuid=self._parse_uuid,
            )
            self._finalize_task(context.task.id)
            return {
                "status": "completed",
                "run_id": run.run_id,
                "note": "Autonomy review passed and task finalized.",
            }
        if context.cycle >= context.max_cycles:
            self._store.update_task(context.task.id, TaskUpdate(status="blocked"))
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=context.task.id,
                    event_type="autonomy.failed",
                    event_data={
                        "stage": "review",
                        "cycle": context.cycle,
                        "error": "Review did not satisfy pass gate; max cycles reached.",
                    },
                )
            )
            return {
                "status": "failed",
                "run_id": run.run_id,
                "note": "Review gate failed and max cycles reached.",
            }
        next_cycle = context.cycle + 1
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=context.task.id,
                event_type="autonomy.review.failed",
                event_data={
                    "cycle": context.cycle,
                    "required_keyword": self._review_pass_keyword,
                    "next_cycle": next_cycle,
                },
            )
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=context.task.id,
                event_type="autonomy.cycle.started",
                event_data={"cycle": next_cycle, "mode": "replan"},
            )
        )
        return {
            "status": "replanning",
            "run_id": run.run_id,
            "note": f"Review gate failed; moved to cycle {next_cycle}.",
        }

    def handle_stage_success(
        self,
        *,
        context: AutonomyStageContext,
        run,
        strategy: str,
    ) -> dict[str, Any]:
        self._record_feedback(
            task_id=context.task.id,
            stage=context.stage,
            strategy=strategy,
            outcome="success",
        )
        if context.stage == "plan":
            self._persist_execute_plan(
                task=context.task,
                prefs=context.prefs,
                output_text=run.output_text,
                cycle=context.cycle,
                strategy=strategy,
            )
        self._persist_stage_handoff_artifacts(
            task=context.task,
            prefs=context.prefs,
            stage=context.stage,
            output_text=run.output_text,
        )
        if context.stage == "plan":
            self._spawn_subtasks_once(task=context.task, prefs=context.prefs)
            post_spawn_events = self._store.list_project_events(task_id=context.task.id, limit=500)
            post_spawn_gate = self._child_gate_status(task=context.task, events=post_spawn_events)
            if post_spawn_gate["mode"] == "awaiting_children":
                return {
                    "status": "in_progress",
                    "run_id": run.run_id,
                    "note": str(
                        post_spawn_gate.get("note")
                        or "Plan complete; child tasks spawned and running."
                    ),
                }
        return {
            "status": "in_progress",
            "run_id": run.run_id,
            "note": f"Stage '{context.stage}' completed.",
        }

    def handle_stage_failure(
        self,
        *,
        context: AutonomyStageContext,
        events: list[Any],
        strategy: str,
        error: Exception,
    ) -> dict[str, Any]:
        return self._failures.handle_stage_failure(
            context=context,
            events=events,
            strategy=strategy,
            error=error,
        )
