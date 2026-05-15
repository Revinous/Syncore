from __future__ import annotations

import json
from textwrap import shorten
from uuid import UUID

from packages.contracts.python.models import BatonPacketCreate, BatonPayload, ProjectEventCreate
from services.analyst.digest import AnalystDigestService
from services.memory import MemoryStoreProtocol

from app.context.retrieval_refs import build_ref_id
from app.services.workspace_acceptance_service import string_list
from app.services.workspace_learning_service import WorkspaceLearningService


class WorkspaceExecutionFinalizer:
    def __init__(
        self,
        *,
        store: MemoryStoreProtocol,
        digest_service: AnalystDigestService,
        workspace_learning: WorkspaceLearningService,
        parse_uuid,
    ) -> None:
        self._store = store
        self._digest_service = digest_service
        self._workspace_learning = workspace_learning
        self._parse_uuid = parse_uuid

    def validate_meaningful_candidate_change(
        self,
        *,
        task_id: UUID,
        task_preferences: dict[str, str],
        changed_files: list[str],
    ) -> dict[str, object]:
        parent_id = self._parse_uuid(task_preferences.get("parent_task_id"))
        if parent_id is None:
            if changed_files:
                return {"status": "ok", "reason": ""}
            return {
                "status": "failed",
                "reason": "Meaningful change gate requires a concrete repo artifact.",
            }
        candidate = self._selected_candidate_for_parent(parent_id)
        if candidate is None:
            return {"status": "ok", "reason": ""}
        raw_targets = candidate.get("target_files")
        target_files = self._candidate_target_files(raw_targets)
        candidate_id = str(candidate.get("candidate_id") or "")
        if not changed_files:
            return {
                "status": "failed",
                "reason": "Selected candidate completed without a persisted repo diff.",
                "candidate_id": candidate_id,
            }
        if target_files and not any(
            changed == target or changed.endswith(target) or target.endswith(changed)
            for changed in changed_files
            for target in target_files
        ):
            return {
                "status": "failed",
                "reason": "Changed files do not match the selected candidate target files.",
                "candidate_id": candidate_id,
            }
        return {"status": "ok", "reason": "", "candidate_id": candidate_id}

    def store_report(
        self,
        *,
        task_id: UUID,
        status: str,
        summary_reason: str,
        provider: str,
        target_model: str,
        profile: str,
        changed_files: list[str],
        diff_refs: list[str],
        planned_actions: list[str],
        command_results: list[dict[str, object]],
        verification: dict[str, object],
    ) -> str:
        payload = {
            "status": status,
            "summary_reason": summary_reason,
            "provider": provider,
            "target_model": target_model,
            "profile": profile,
            "changed_files": changed_files,
            "diff_ref_ids": diff_refs,
            "planned_actions": planned_actions[:40],
            "commands": command_results,
            "verification": verification,
        }
        original = json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2)
        summary = shorten(
            f"{status} {summary_reason} files={len(changed_files)} commands={len(command_results)}",
            width=220,
            placeholder=" ...",
        )
        record = self._store.upsert_context_reference(
            ref_id=build_ref_id(task_id, "workspace_execution_report", original),
            task_id=task_id,
            content_type="workspace_execution_report",
            original_content=original,
            summary=summary,
            retrieval_hint=(
                "Workspace execution report with verification commands, diff refs, and "
                "outcome rationale."
            ),
        )
        ref_id = str(record["ref_id"])
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="workspace.execution.report.stored",
                event_data={"ref_id": ref_id, "status": status, "profile": profile},
            )
        )
        return ref_id

    def record_learning_success(
        self,
        *,
        workspace_id: UUID | None,
        provider: str,
        model: str,
        profile: str,
        policy: dict[str, object],
        runner: dict[str, object],
        command_results: list[dict[str, object]],
    ) -> None:
        self._workspace_learning.record_success(
            workspace_id=workspace_id,
            provider=provider,
            model=model,
            profile=profile,
            policy=policy,
            runner=runner,
            command_results=command_results,
        )

    def record_learning_failure(
        self,
        *,
        workspace_id: UUID | None,
        reason: str,
        category: str,
        strategy: str,
    ) -> None:
        self._workspace_learning.record_failure(
            workspace_id=workspace_id,
            reason=reason,
            category=category,
            strategy=strategy,
        )

    def finalize_success(
        self,
        *,
        task_id: UUID,
        workspace_id: UUID | None,
        from_agent: str,
        objective: str,
        provider: str,
        target_model: str,
        profile: str,
        changed_files: list[str],
        diff_refs: list[str],
        read_refs: list[str],
        planned_actions: list[str],
        command_results: list[dict[str, object]],
        verification: dict[str, object],
        finish_summary: str,
        completed_work: list[str],
        next_action: str,
        policy: dict[str, object],
        runner: dict[str, object],
    ) -> dict[str, object]:
        report_ref_id = self.store_report(
            task_id=task_id,
            status="completed",
            summary_reason=str(verification.get("reason") or "Workspace verification passed."),
            provider=provider,
            target_model=target_model,
            profile=profile,
            changed_files=changed_files,
            diff_refs=diff_refs,
            planned_actions=planned_actions,
            command_results=command_results,
            verification=verification,
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="workspace.execution.completed",
                event_data={
                    "provider": provider,
                    "model": target_model,
                    "changed_files": len(changed_files),
                    "diff_refs": len(diff_refs),
                    "read_refs": len([item for item in read_refs if item]),
                    "profile": profile,
                    "meaningful_change": "true",
                    "report_ref_id": report_ref_id,
                },
            )
        )
        baton = self._store.save_baton_packet(
            BatonPacketCreate(
                task_id=task_id,
                from_agent=from_agent,
                to_agent="analyst",
                summary=finish_summary or "Workspace implementation batch completed",
                payload=BatonPayload(
                    objective=objective,
                    completed_work=completed_work[:20],
                    constraints=[],
                    open_questions=[],
                    next_best_action=next_action,
                    relevant_artifacts=changed_files[:20],
                ),
            )
        )
        events = self._store.list_project_events(task_id=task_id, limit=200)
        digest = self._digest_service.generate_digest(
            task_id=task_id,
            events=events,
            latest_baton=baton,
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
        self.record_learning_success(
            workspace_id=workspace_id,
            provider=provider,
            model=target_model,
            profile=profile,
            policy=policy,
            runner=runner,
            command_results=command_results,
        )
        return {
            "task_id": str(task_id),
            "workspace_id": str(workspace_id),
            "provider": provider,
            "target_model": target_model,
            "profile": profile,
            "changed_files": changed_files,
            "diff_ref_ids": diff_refs,
            "read_ref_ids": [item for item in read_refs if item],
            "planned_actions": planned_actions[:40],
            "commands": command_results,
            "baton_id": str(baton.id),
            "verification": verification,
            "report_ref_id": report_ref_id,
            "digest": digest.model_dump(mode="json"),
        }

    def _candidate_target_files(self, value: object) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return string_list(value)

    def _selected_candidate_for_parent(self, parent_id: UUID) -> dict[str, object] | None:
        parent_events = self._store.list_project_events(task_id=parent_id, limit=500)
        child_ids: list[UUID] = []
        for event in reversed(parent_events):
            if event.event_type != "autonomy.subtasks.spawned":
                continue
            raw_ids = str(event.event_data.get("child_task_ids") or "").strip()
            for raw in (item.strip() for item in raw_ids.split(",") if item.strip()):
                parsed = self._parse_uuid(raw)
                if parsed is not None:
                    child_ids.append(parsed)
            break
        for child_id in child_ids:
            child = self._store.get_task(child_id)
            if child is None or child.task_type != "analysis":
                continue
            child_events = self._store.list_project_events(task_id=child_id, limit=250)
            for event in reversed(child_events):
                if event.event_type == "autonomy.candidate.selected":
                    return {
                        "candidate_id": event.event_data.get("candidate_id"),
                        "target_files": event.event_data.get("target_files"),
                        "verification_command": event.event_data.get("verification_command"),
                    }
        return None
