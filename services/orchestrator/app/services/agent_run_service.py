from datetime import datetime, timezone
from uuid import UUID

from packages.contracts.python.models import (
    AgentRun,
    AgentRunCreate,
    AgentRunUpdate,
    ProjectEventCreate,
)
from pydantic import BaseModel
from services.memory import MemoryStoreProtocol

from app.config import Settings


class AgentRunResult(BaseModel):
    run_id: UUID
    task_id: UUID
    status: str
    output_summary: str | None = None
    prompt_ref_id: str | None = None
    context_ref_id: str | None = None
    output_ref_id: str | None = None
    output_text: str | None = None
    retrieval_hint: str | None = None


class AgentRunService:
    def __init__(self, store: MemoryStoreProtocol, settings: Settings | None = None) -> None:
        self._store = store
        self._settings = settings

    def create_run(self, payload: AgentRunCreate) -> AgentRun:
        task = self._store.get_task(payload.task_id)
        if task is None:
            raise LookupError("Task not found")

        return self._store.create_agent_run(payload)

    def update_run(self, run_id: UUID, payload: AgentRunUpdate) -> AgentRun | None:
        return self._store.update_agent_run(run_id, payload)

    def get_run(self, run_id: UUID) -> AgentRun | None:
        return self._store.get_agent_run(run_id)

    def list_runs(self, task_id: UUID | None = None, limit: int = 50) -> list[AgentRun]:
        runs = self._store.list_agent_runs(task_id=task_id, limit=limit)
        return self._reconcile_stale_runs(runs)

    def _reconcile_stale_runs(self, runs: list[AgentRun]) -> list[AgentRun]:
        timeout_seconds = (
            self._settings.run_stale_timeout_seconds if self._settings is not None else 1800
        )
        if timeout_seconds <= 0:
            return runs

        now = datetime.now(timezone.utc)
        reconciled: list[AgentRun] = []
        for run in runs:
            if run.status not in {"queued", "running"}:
                reconciled.append(run)
                continue

            age_seconds = (now - run.updated_at).total_seconds()
            if age_seconds < timeout_seconds:
                reconciled.append(run)
                continue

            updated = self._store.update_agent_run(
                run.id,
                AgentRunUpdate(
                    status="blocked",
                    error_message=(
                        f"Marked stale after {int(age_seconds)}s without progress."
                    ),
                ),
            )
            if updated is not None:
                self._store.save_project_event(
                    ProjectEventCreate(
                        task_id=updated.task_id,
                        event_type="run.stale_reconciled",
                        event_data={
                            "run_id": str(updated.id),
                            "previous_status": run.status,
                            "status": updated.status,
                            "age_seconds": int(age_seconds),
                        },
                    )
                )
                reconciled.append(updated)
            else:
                reconciled.append(run)
        return reconciled

    def cancel_run(self, run_id: UUID) -> AgentRun | None:
        run = self._store.get_agent_run(run_id)
        if run is None:
            return None
        if run.status not in {"queued", "running"}:
            raise ValueError(f"Run cannot be canceled from status '{run.status}'.")
        updated = self._store.update_agent_run(
            run_id,
            AgentRunUpdate(status="blocked", error_message="Canceled by operator."),
        )
        if updated is not None:
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=updated.task_id,
                    event_type="run.canceled",
                    event_data={"run_id": str(updated.id), "status": updated.status},
                )
            )
        return updated

    def resume_run(self, run_id: UUID) -> AgentRun | None:
        run = self._store.get_agent_run(run_id)
        if run is None:
            return None
        if run.status not in {"blocked", "failed"}:
            raise ValueError(f"Run cannot be resumed from status '{run.status}'.")
        updated = self._store.update_agent_run(
            run_id,
            AgentRunUpdate(status="queued", error_message=None),
        )
        if updated is not None:
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=updated.task_id,
                    event_type="run.resumed",
                    event_data={"run_id": str(updated.id), "status": updated.status},
                )
            )
        return updated

    def get_run_result(self, run_id: UUID) -> AgentRunResult | None:
        run = self._store.get_agent_run(run_id)
        if run is None:
            return None

        output_ref_id: str | None = None
        prompt_ref_id: str | None = None
        context_ref_id: str | None = None
        events = self._store.list_project_events(task_id=run.task_id, limit=500)
        for event in reversed(events):
            if event.event_type != "run.started":
                continue
            if str(event.event_data.get("run_id") or "") not in {"", str(run_id)}:
                continue
            prompt_candidate = str(event.event_data.get("prompt_ref_id") or "").strip()
            context_candidate = str(event.event_data.get("context_ref_id") or "").strip()
            if prompt_candidate:
                prompt_ref_id = prompt_candidate
            if context_candidate:
                context_ref_id = context_candidate
            break

        for event in reversed(events):
            if event.event_type != "run.output.stored":
                continue
            if str(event.event_data.get("run_id") or "") != str(run_id):
                continue
            candidate_ref = str(event.event_data.get("ref_id") or "").strip()
            if candidate_ref:
                output_ref_id = candidate_ref
                break

        output_text: str | None = None
        retrieval_hint: str | None = None
        if output_ref_id is not None:
            ref = self._store.get_context_reference(output_ref_id)
            if ref is not None:
                output_text = str(ref["original_content"])
                retrieval_hint = str(ref["retrieval_hint"])

        return AgentRunResult(
            run_id=run.id,
            task_id=run.task_id,
            status=run.status,
            output_summary=run.output_summary,
            prompt_ref_id=prompt_ref_id,
            context_ref_id=context_ref_id,
            output_ref_id=output_ref_id,
            output_text=output_text,
            retrieval_hint=retrieval_hint,
        )
