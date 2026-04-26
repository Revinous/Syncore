from uuid import UUID

from packages.contracts.python.models import ProjectEvent, ProjectEventCreate
from services.memory.store import MemoryStore


class EventService:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def create_event(self, payload: ProjectEventCreate) -> ProjectEvent:
        task = self._store.get_task(payload.task_id)
        if task is None:
            raise LookupError("Task not found")

        return self._store.save_project_event(payload)

    def list_events(self, task_id: UUID, limit: int = 100) -> list[ProjectEvent]:
        return self._store.list_project_events(task_id=task_id, limit=limit)
