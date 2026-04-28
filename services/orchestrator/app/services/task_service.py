from uuid import UUID

from packages.contracts.python.models import Task, TaskCreate, TaskDetail, TaskUpdate
from services.memory import MemoryStoreProtocol


class TaskService:
    def __init__(self, store: MemoryStoreProtocol) -> None:
        self._store = store

    def create_task(self, payload: TaskCreate) -> Task:
        if (
            payload.workspace_id is not None
            and self._store.get_workspace(payload.workspace_id) is None
        ):
            raise ValueError("Workspace not found")
        return self._store.create_task(payload)

    def get_task(self, task_id: UUID) -> Task | None:
        return self._store.get_task(task_id)

    def update_task(self, task_id: UUID, payload: TaskUpdate) -> Task | None:
        if "workspace_id" in payload.model_fields_set:
            workspace_id = payload.workspace_id
            if workspace_id is not None and self._store.get_workspace(workspace_id) is None:
                raise ValueError("Workspace not found")
        return self._store.update_task(task_id, payload)

    def list_tasks(self, limit: int = 50, workspace_id: UUID | None = None) -> list[Task]:
        return self._store.list_tasks(limit=limit, workspace_id=workspace_id)

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
