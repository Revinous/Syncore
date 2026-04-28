from uuid import UUID

from packages.contracts.python.models import (
    ProjectEventCreate,
    Task,
    TaskCreate,
    TaskDetail,
    TaskUpdate,
)
from pydantic import BaseModel, Field
from services.memory import MemoryStoreProtocol

from app.services.context_service import ContextService


class TaskModelSwitchResult(BaseModel):
    task_id: UUID
    previous_provider: str | None = None
    previous_model: str | None = None
    preferred_provider: str = Field(min_length=1)
    preferred_model: str = Field(min_length=1)
    target_agent: str = Field(min_length=1)
    token_budget: int = Field(ge=256, le=200_000)
    context_bundle_id: UUID
    estimated_token_count: int = Field(ge=0)
    included_refs: list[str] = Field(default_factory=list)


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
        task = self._store.get_task(task_id)
        if task is None:
            raise LookupError("Task not found")

        provider_norm = provider.strip().lower()
        model_norm = model.strip()
        if not provider_norm:
            raise ValueError("provider is required")
        if not model_norm:
            raise ValueError("model is required")

        events = self._store.list_project_events(task_id=task_id, limit=500)
        previous_provider, previous_model, current_prefs = self._latest_preferences(events)
        next_prefs = dict(current_prefs)
        next_prefs["preferred_provider"] = provider_norm
        next_prefs["preferred_model"] = model_norm
        if reason:
            next_prefs["model_switch_reason"] = reason[:200]

        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="task.preferences",
                event_data=next_prefs,
            )
        )

        context_service = ContextService(self._store)
        optimized = context_service.assemble_optimized_context(
            task_id=task_id,
            target_agent=target_agent,
            target_model=model_norm,
            token_budget=token_budget,
        )
        if optimized.bundle_id is None:
            raise RuntimeError("context bundle id missing after optimization")

        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="model.switch.completed",
                event_data={
                    "from_provider": previous_provider or "",
                    "from_model": previous_model or "",
                    "to_provider": provider_norm,
                    "to_model": model_norm,
                    "target_agent": target_agent,
                    "context_bundle_id": str(optimized.bundle_id),
                },
            )
        )

        return TaskModelSwitchResult(
            task_id=task_id,
            previous_provider=previous_provider,
            previous_model=previous_model,
            preferred_provider=provider_norm,
            preferred_model=model_norm,
            target_agent=target_agent,
            token_budget=token_budget,
            context_bundle_id=optimized.bundle_id,
            estimated_token_count=optimized.estimated_token_count,
            included_refs=optimized.included_refs,
        )

    def _latest_preferences(
        self,
        events,
    ) -> tuple[str | None, str | None, dict[str, str | int | float | bool | None]]:
        for event in reversed(events):
            if event.event_type != "task.preferences":
                continue
            prefs = dict(event.event_data)
            provider = str(prefs.get("preferred_provider") or "").strip().lower() or None
            model = str(prefs.get("preferred_model") or "").strip() or None
            return provider, model, prefs
        return None, None, {}
