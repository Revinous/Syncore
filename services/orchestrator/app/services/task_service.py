from uuid import UUID

from packages.contracts.python.models import Task, TaskCreate, TaskDetail
from services.memory.store import MemoryStore


class TaskService:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def create_task(self, payload: TaskCreate) -> Task:
        return self._store.create_task(payload)

    def get_task(self, task_id: UUID) -> Task | None:
        return self._store.get_task(task_id)

    def list_tasks(self, limit: int = 50) -> list[Task]:
        return self._store.list_tasks(limit=limit)

    def get_task_detail(self, task_id: UUID) -> TaskDetail | None:
        task = self._store.get_task(task_id)
        if task is None:
            return None

        return TaskDetail(
            task=task,
            agent_runs=self._store.list_agent_runs(task_id),
            baton_packets=self._store.list_baton_packets(task_id),
            event_count=self._store.count_project_events(task_id),
            digest_path=f"/analyst/digest/{task_id}",
        )
