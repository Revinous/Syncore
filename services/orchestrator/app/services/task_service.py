from uuid import UUID

from packages.contracts.python.models import (
    Task,
    TaskCreate,
    TaskDetail,
    TaskUpdate,
)
from services.memory import MemoryStoreProtocol

from app.services.task_execution_report_service import TaskExecutionReportService
from app.services.task_model_policy_service import TaskModelPolicyService
from app.services.task_models import (
    ChildTaskStatusBoard,
    ChildTaskStatusItem,
    TaskExecutionReport,
    TaskModelPolicy,
    TaskModelPolicyUpdate,
    TaskModelSwitchRecord,
    TaskModelSwitchResult,
)


class TaskService:
    def __init__(
        self,
        store: MemoryStoreProtocol,
        *,
        configured_providers: set[str] | None = None,
        provider_model_hints: dict[str, str] | None = None,
        default_provider: str = "local_echo",
    ) -> None:
        self._store = store
        self._configured_providers = configured_providers or {"local_echo"}
        self._provider_model_hints = provider_model_hints or {}
        self._execution_reports = TaskExecutionReportService(store)
        self._model_policy = TaskModelPolicyService(
            store,
            configured_providers=self._configured_providers,
            provider_model_hints=self._provider_model_hints,
            default_provider=default_provider,
        )

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

    def get_execution_report(self, task_id: UUID) -> TaskExecutionReport | None:
        return self._execution_reports.get_execution_report(task_id)

    def switch_model(
        self,
        *,
        task_id: UUID,
        provider: str,
        model: str,
        target_agent: str,
        token_budget: int,
        reason: str | None = None,
    ) -> TaskModelSwitchResult:
        return self._model_policy.switch_model(
            task_id=task_id,
            provider=provider,
            model=model,
            target_agent=target_agent,
            token_budget=token_budget,
            reason=reason,
        )

    def list_model_switches(self, task_id: UUID, limit: int = 100) -> list[TaskModelSwitchRecord]:
        return self._model_policy.list_model_switches(task_id=task_id, limit=limit)

    def resolve_task_model_preference(
        self,
        task_id: UUID,
        *,
        stage: str = "execute",
    ) -> tuple[str, str]:
        return self._model_policy.resolve_task_model_preference(task_id, stage=stage)

    def get_model_policy(self, task_id: UUID) -> TaskModelPolicy:
        return self._model_policy.get_model_policy(task_id)

    def update_model_policy(
        self,
        task_id: UUID,
        payload: TaskModelPolicyUpdate,
    ) -> TaskModelPolicy:
        return self._model_policy.update_model_policy(task_id, payload)

    def get_child_status_board(self, parent_task_id: UUID) -> ChildTaskStatusBoard | None:
        parent = self._store.get_task(parent_task_id)
        if parent is None:
            return None

        children_by_id: dict[UUID, Task] = {}
        parent_events = self._store.list_project_events(task_id=parent_task_id, limit=200)
        for event in reversed(parent_events):
            if event.event_type != "autonomy.subtasks.spawned":
                continue
            raw_ids = str(event.event_data.get("child_task_ids") or "").strip()
            if not raw_ids:
                continue
            for raw in [item.strip() for item in raw_ids.split(",") if item.strip()]:
                try:
                    child_id = UUID(raw)
                except ValueError:
                    continue
                child = self._store.get_task(child_id)
                if child is not None:
                    children_by_id[child.id] = child
            if children_by_id:
                break

        children: list[Task] = list(children_by_id.values())
        if parent.workspace_id is None:
            all_tasks = self._store.list_tasks(limit=1000, workspace_id=None)
        else:
            all_tasks = self._store.list_tasks(limit=1000, workspace_id=parent.workspace_id)
        for candidate in all_tasks:
            if candidate.id in children_by_id:
                continue
            events = self._store.list_project_events(task_id=candidate.id, limit=20)
            for event in reversed(events):
                if event.event_type != "task.preferences":
                    continue
                raw_parent = str(event.event_data.get("parent_task_id") or "").strip()
                if raw_parent == str(parent_task_id):
                    children.append(candidate)
                break

        completed = len([task for task in children if task.status == "completed"])
        blocked = len([task for task in children if task.status == "blocked"])
        active = len([task for task in children if task.status in {"new", "in_progress"}])
        return ChildTaskStatusBoard(
            parent_task_id=parent_task_id,
            has_children=len(children) > 0,
            total_children=len(children),
            completed_children=completed,
            blocked_children=blocked,
            active_children=active,
            children=[
                ChildTaskStatusItem(
                    task_id=task.id,
                    title=task.title,
                    status=task.status,
                    task_type=task.task_type,
                    complexity=task.complexity,
                    updated_at=task.updated_at.isoformat(),
                )
                for task in children
            ],
        )
