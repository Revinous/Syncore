from __future__ import annotations

from app.services.workspace_execution_utils import classify_workspace_issue


class WorkspaceExecutionFailureHandler:
    def __init__(self, *, finalizer, record_event) -> None:
        self._finalizer = finalizer
        self._record_event = record_event

    def fail_verification(
        self,
        *,
        payload,
        task,
        provider_name: str,
        target_model: str,
        profile: str,
        planned_actions: list[str],
        state,
        verification: dict[str, object],
    ) -> None:
        classification = classify_workspace_issue(
            stage="verification",
            reason=str(verification.get("reason") or "verification failed"),
        )
        report_ref_id = self._finalizer.store_report(
            task_id=payload.task_id,
            status="failed",
            summary_reason=str(verification.get("reason") or "verification failed"),
            provider=provider_name,
            target_model=target_model,
            profile=profile,
            changed_files=state.changed_files,
            diff_refs=state.diff_refs,
            planned_actions=planned_actions,
            command_results=state.command_results,
            verification=verification,
        )
        self._finalizer.record_learning_failure(
            workspace_id=task.workspace_id,
            reason=str(verification.get("reason") or "verification failed"),
            category=classification["category"],
            strategy=classification["strategy"],
        )
        self._record_event(
            task_id=payload.task_id,
            event_type="workspace.execution.verification.failed",
            event_data={
                "reason": str(verification.get("reason") or "verification failed"),
                "failure_category": classification["category"],
                "recommended_strategy": classification["strategy"],
                "provider": provider_name,
                "report_ref_id": report_ref_id,
            },
        )
        raise RuntimeError(str(verification.get("reason") or "Workspace verification failed"))

    def fail_meaningful_change(
        self,
        *,
        payload,
        provider_name: str,
        target_model: str,
        profile: str,
        planned_actions: list[str],
        state,
        verification: dict[str, object],
        candidate_validation: dict[str, object],
    ) -> None:
        classification = classify_workspace_issue(
            stage="verification",
            reason=str(candidate_validation.get("reason") or "candidate validation failed"),
        )
        report_ref_id = self._finalizer.store_report(
            task_id=payload.task_id,
            status="failed",
            summary_reason=str(candidate_validation.get("reason") or "candidate validation failed"),
            provider=provider_name,
            target_model=target_model,
            profile=profile,
            changed_files=state.changed_files,
            diff_refs=state.diff_refs,
            planned_actions=planned_actions,
            command_results=state.command_results,
            verification={**verification, "candidate_validation": candidate_validation},
        )
        self._record_event(
            task_id=payload.task_id,
            event_type="workspace.execution.meaningful_change.failed",
            event_data={
                "reason": str(candidate_validation.get("reason") or ""),
                "failure_category": classification["category"],
                "recommended_strategy": classification["strategy"],
                "candidate_id": str(candidate_validation.get("candidate_id") or ""),
                "report_ref_id": report_ref_id,
            },
        )
        raise RuntimeError(
            str(candidate_validation.get("reason") or "Meaningful change gate failed")
        )
