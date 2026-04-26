from uuid import UUID

from packages.contracts.python.models import AgentRun, AgentRunCreate, AgentRunUpdate
from services.memory.store import MemoryStore


class AgentRunService:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def create_run(self, payload: AgentRunCreate) -> AgentRun:
        task = self._store.get_task(payload.task_id)
        if task is None:
            raise LookupError("Task not found")

        return self._store.create_agent_run(payload)

    def update_run(self, run_id: UUID, payload: AgentRunUpdate) -> AgentRun | None:
        return self._store.update_agent_run(run_id, payload)
