from __future__ import annotations

import json
from uuid import UUID

from packages.contracts.python.models import AgentRun
from services.memory import MemoryStoreProtocol

from app.services.task_models import (
    TaskExecutionArtifact,
    TaskExecutionCommand,
    TaskExecutionReport,
    TaskExecutionRunOutput,
)


class TaskExecutionReportService:
    def __init__(self, store: MemoryStoreProtocol) -> None:
        self._store = store

    def get_execution_report(self, task_id: UUID) -> TaskExecutionReport | None:
        task = self._store.get_task(task_id)
        if task is None:
            return None

        runs = self._store.list_agent_runs(task_id=task_id, limit=200)
        events = self._store.list_project_events(task_id=task_id, limit=500)
        latest_report_event = next(
            (
                event
                for event in reversed(events)
                if event.event_type == "workspace.execution.report.stored"
            ),
            None,
        )

        report_ref_id: str | None = None
        report_payload: dict[str, object] = {}
        if latest_report_event is not None:
            report_ref_id = str(latest_report_event.event_data.get("ref_id") or "").strip() or None
            if report_ref_id:
                ref = self._store.get_context_reference(report_ref_id)
                if ref is not None:
                    try:
                        report_payload = _json_object(str(ref["original_content"]))
                    except ValueError:
                        report_payload = {}

        latest_outcome = next(
            (
                event
                for event in reversed(events)
                if event.event_type
                in {
                    "workspace.execution.completed",
                    "workspace.execution.verification.failed",
                    "workspace.execution.meaningful_change.failed",
                    "run.failed",
                    "run.completed",
                }
            ),
            None,
        )
        diff_artifacts = self._diff_artifacts(events)
        output_artifacts = [
            self._build_run_output(run=runs_item, events=events) for runs_item in runs
        ]
        command_results = [
            TaskExecutionCommand(
                command=str(item.get("command") or ""),
                status=str(item.get("status") or "unknown"),
                output_preview=_preview_text(str(item.get("output") or "")) or None,
            )
            for item in _list_of_dicts(report_payload.get("commands"))
        ]
        changed_files = [
            str(item) for item in _list_of_strings(report_payload.get("changed_files"))
        ]
        planned_actions = [
            str(item) for item in _list_of_strings(report_payload.get("planned_actions"))
        ]
        verification = _json_object(report_payload.get("verification"))
        verification_status = str(verification.get("status") or "").strip() or None
        verification_reason = str(verification.get("reason") or "").strip() or None

        outcome_status = "unknown"
        summary_reason = "No execution outcome recorded yet."
        meaningful_change = False
        if latest_outcome is not None:
            outcome_status = latest_outcome.event_type
            summary_reason = (
                str(latest_outcome.event_data.get("reason") or "").strip()
                or str(latest_outcome.event_data.get("error") or "").strip()
                or latest_outcome.event_type.replace(".", " ")
            )
            meaningful_change = (
                str(latest_outcome.event_data.get("meaningful_change") or "").lower() == "true"
            )
        if report_payload:
            meaningful_change = bool(verification.get("status") == "ok") or meaningful_change
            default_reason = latest_outcome.event_type.replace(".", " ") if latest_outcome else ""
            if not summary_reason or summary_reason == default_reason:
                summary_reason = (
                    str(report_payload.get("summary_reason") or "").strip() or summary_reason
                )
        if latest_outcome and latest_outcome.event_type == "workspace.execution.completed":
            summary_reason = (
                verification_reason or "Workspace verification passed and changes were persisted."
            )
            meaningful_change = True
            verification_status = verification_status or "ok"
            if not changed_files:
                changed_files = []
                seen_paths: set[str] = set()
                for artifact in diff_artifacts:
                    if artifact.path in seen_paths:
                        continue
                    seen_paths.add(artifact.path)
                    changed_files.append(artifact.path)

        return TaskExecutionReport(
            task_id=task_id,
            outcome_status=outcome_status,
            summary_reason=summary_reason,
            meaningful_change=meaningful_change,
            changed_files=_dedupe_strings(changed_files),
            planned_actions=planned_actions,
            verification_status=verification_status,
            verification_reason=verification_reason,
            verification_commands=command_results,
            diff_artifacts=diff_artifacts,
            output_artifacts=output_artifacts,
            report_ref_id=report_ref_id,
            last_event_type=latest_outcome.event_type if latest_outcome else None,
            last_updated_at=latest_outcome.created_at.isoformat() if latest_outcome else None,
        )

    def _diff_artifacts(self, events) -> list[TaskExecutionArtifact]:
        diff_artifacts: list[TaskExecutionArtifact] = []
        seen_diff_refs: set[str] = set()
        for event in reversed(events):
            if event.event_type != "artifact.diff.stored":
                continue
            ref_id = str(event.event_data.get("ref_id") or "").strip()
            path = str(event.event_data.get("path") or "").strip()
            if not ref_id or ref_id in seen_diff_refs:
                continue
            seen_diff_refs.add(ref_id)
            ref = self._store.get_context_reference(ref_id)
            if ref is None:
                continue
            diff_artifacts.append(
                TaskExecutionArtifact(
                    ref_id=ref_id,
                    path=path or str(ref.get("retrieval_hint") or ""),
                    content_type=str(ref.get("content_type") or "workspace_diff"),
                    summary=str(ref.get("summary") or ""),
                    retrieval_hint=str(ref.get("retrieval_hint") or ""),
                    preview=_preview_text(str(ref.get("original_content") or "")),
                    created_at=event.created_at.isoformat(),
                )
            )
        diff_artifacts.reverse()
        return diff_artifacts

    def _build_run_output(self, *, run: AgentRun, events) -> TaskExecutionRunOutput:
        output_ref_id: str | None = None
        provider: str | None = None
        target_model: str | None = None
        for event in reversed(events):
            if event.event_type != "run.output.stored":
                continue
            if str(event.event_data.get("run_id") or "") != str(run.id):
                continue
            output_ref_id = str(event.event_data.get("ref_id") or "").strip() or None
            provider = str(event.event_data.get("provider") or "").strip() or None
            target_model = str(event.event_data.get("target_model") or "").strip() or None
            break
        output_preview: str | None = None
        if output_ref_id:
            ref = self._store.get_context_reference(output_ref_id)
            if ref is not None:
                output_preview = _preview_text(str(ref.get("original_content") or "")) or None
        return TaskExecutionRunOutput(
            run_id=run.id,
            role=run.role,
            status=run.status,
            provider=provider,
            target_model=target_model,
            output_ref_id=output_ref_id,
            output_preview=output_preview,
            error_message=run.error_message,
            updated_at=run.updated_at.isoformat(),
        )


def _preview_text(value: str, limit: int = 1800) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...truncated..."


def _list_of_strings(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
