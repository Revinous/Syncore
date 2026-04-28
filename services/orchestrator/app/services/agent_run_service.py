from uuid import UUID

from packages.contracts.python.models import AgentRun, AgentRunCreate, AgentRunUpdate
from pydantic import BaseModel
from services.memory import MemoryStoreProtocol


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
    def __init__(self, store: MemoryStoreProtocol) -> None:
        self._store = store

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
        return self._store.list_agent_runs(task_id=task_id, limit=limit)

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
