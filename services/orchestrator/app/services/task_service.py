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
    continuity_status: str = "preserved"
    continuity_notes: list[str] = Field(default_factory=list)


class ChildTaskStatusItem(BaseModel):
    task_id: UUID
    title: str
    status: str
    task_type: str
    complexity: str
    updated_at: str


class ChildTaskStatusBoard(BaseModel):
    parent_task_id: UUID
    has_children: bool
    total_children: int = Field(ge=0)
    completed_children: int = Field(ge=0)
    blocked_children: int = Field(ge=0)
    active_children: int = Field(ge=0)
    children: list[ChildTaskStatusItem] = Field(default_factory=list)


class TaskModelSwitchRecord(BaseModel):
    switched_at: str
    from_provider: str | None = None
    from_model: str | None = None
    to_provider: str
    to_model: str
    target_agent: str | None = None
    continuity_status: str | None = None
    context_bundle_id: str | None = None


class TaskService:
    def __init__(
        self,
        store: MemoryStoreProtocol,
        *,
        configured_providers: set[str] | None = None,
        provider_model_hints: dict[str, str] | None = None,
    ) -> None:
        self._store = store
        self._configured_providers = configured_providers or {"local_echo"}
        self._provider_model_hints = provider_model_hints or {}

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
        if provider_norm not in self._configured_providers:
            providers = ", ".join(sorted(self._configured_providers))
            raise ValueError(
                f"Provider '{provider_norm}' is not configured. Available: {providers}"
            )
        self._validate_model_for_provider(provider=provider_norm, model=model_norm)

        events = self._store.list_project_events(task_id=task_id, limit=500)
        previous_provider, previous_model, current_prefs = self._latest_preferences(events)
        continuity_status, continuity_notes = self._continuity_notes(
            previous_provider=previous_provider,
            previous_model=previous_model,
            next_provider=provider_norm,
            next_model=model_norm,
        )
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
                    "continuity_status": continuity_status,
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
            continuity_status=continuity_status,
            continuity_notes=continuity_notes,
        )

    def list_model_switches(self, task_id: UUID, limit: int = 100) -> list[TaskModelSwitchRecord]:
        if self._store.get_task(task_id) is None:
            raise LookupError("Task not found")
        events = self._store.list_project_events(task_id=task_id, limit=max(limit, 1))
        records: list[TaskModelSwitchRecord] = []
        for event in reversed(events):
            if event.event_type != "model.switch.completed":
                continue
            data = event.event_data
            to_provider = str(data.get("to_provider") or "").strip()
            to_model = str(data.get("to_model") or "").strip()
            if not to_provider or not to_model:
                continue
            records.append(
                TaskModelSwitchRecord(
                    switched_at=event.created_at.isoformat(),
                    from_provider=str(data.get("from_provider") or "").strip() or None,
                    from_model=str(data.get("from_model") or "").strip() or None,
                    to_provider=to_provider,
                    to_model=to_model,
                    target_agent=str(data.get("target_agent") or "").strip() or None,
                    continuity_status=str(data.get("continuity_status") or "").strip() or None,
                    context_bundle_id=str(data.get("context_bundle_id") or "").strip() or None,
                )
            )
        return records

    def resolve_task_model_preference(self, task_id: UUID) -> tuple[str, str]:
        task = self._store.get_task(task_id)
        if task is None:
            raise LookupError("Task not found")
        events = self._store.list_project_events(task_id=task_id, limit=500)
        provider, model, _ = self._latest_preferences(events)
        resolved_provider = provider or "local_echo"
        resolved_model = model or self._provider_model_hints.get(resolved_provider, "local_echo")
        if resolved_provider not in self._configured_providers:
            resolved_provider = "local_echo"
            resolved_model = "local_echo"
        return resolved_provider, resolved_model

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

    def _validate_model_for_provider(self, *, provider: str, model: str) -> None:
        lowered = model.lower()
        if provider == "local_echo" and lowered != "local_echo":
            raise ValueError("local_echo provider only supports model 'local_echo'.")
        if provider == "openai" and not lowered.startswith(("gpt", "o1", "o3", "o4")):
            raise ValueError("OpenAI model should start with gpt/o1/o3/o4.")
        if provider == "anthropic" and "claude" not in lowered:
            raise ValueError("Anthropic model should contain 'claude'.")
        if provider == "gemini" and "gemini" not in lowered:
            raise ValueError("Gemini model should contain 'gemini'.")

    def _continuity_notes(
        self,
        *,
        previous_provider: str | None,
        previous_model: str | None,
        next_provider: str,
        next_model: str,
    ) -> tuple[str, list[str]]:
        notes: list[str] = []
        if previous_provider is None and previous_model is None:
            notes.append("First explicit provider/model selection for this task.")
            return "initialized", notes
        if previous_provider == next_provider and previous_model == next_model:
            notes.append("Provider/model unchanged; continuity fully preserved.")
            return "unchanged", notes
        if previous_provider != next_provider:
            notes.append(
                f"Cross-provider switch: {previous_provider or '-'} -> {next_provider}."
            )
            notes.append("Context bundle reassembled to preserve task continuity.")
            return "cross_provider_switched", notes
        notes.append(f"Intra-provider model switch: {previous_model or '-'} -> {next_model}.")
        notes.append("Context bundle reassembled for the new model.")
        return "model_switched", notes
