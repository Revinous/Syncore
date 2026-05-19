from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from packages.contracts.python.models import Task, TaskCreate, TaskDetail, TaskUpdate
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services.local_settings_service import (
    LocalExecutionSettingsService,
    resolve_default_provider_settings,
)
from app.services.provider_config import configured_provider_hints
from app.services.task_models import (
    ChildTaskStatusBoard,
    TaskExecutionReport,
    TaskModelPolicy,
    TaskModelPolicyUpdate,
    TaskModelSwitchRecord,
    TaskModelSwitchResult,
)
from app.services.task_service import TaskService
from app.store_factory import build_memory_store

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_task_service(settings: Settings = Depends(get_settings)) -> TaskService:
    configured, hints = configured_provider_hints(settings)
    local_settings = LocalExecutionSettingsService().load()
    default_provider, _ = resolve_default_provider_settings(
        configured_providers=configured,
        provider_model_hints=hints,
        fallback_provider=settings.default_llm_provider,
        fallback_model=hints.get(settings.default_llm_provider, settings.default_llm_provider),
        stored_preference=(
            local_settings.default_provider_preference if local_settings else None
        ),
    )
    return TaskService(
        build_memory_store(settings),
        configured_providers=configured,
        provider_model_hints=hints,
        default_provider=default_provider,
    )


@router.post("", response_model=Task, status_code=201)
def create_task(
    payload: TaskCreate,
    service: TaskService = Depends(get_task_service),
) -> Task:
    try:
        return service.create_task(payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("", response_model=list[Task])
def list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    workspace_id: UUID | None = Query(default=None),
    service: TaskService = Depends(get_task_service),
) -> list[Task]:
    return service.list_tasks(limit=limit, workspace_id=workspace_id)


@router.get("/{task_id}", response_model=TaskDetail)
def get_task_detail(
    task_id: UUID,
    service: TaskService = Depends(get_task_service),
) -> TaskDetail:
    detail = service.get_task_detail(task_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return detail


@router.get("/{task_id}/execution-report", response_model=TaskExecutionReport)
def get_task_execution_report(
    task_id: UUID,
    service: TaskService = Depends(get_task_service),
) -> TaskExecutionReport:
    report = service.get_execution_report(task_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return report


@router.patch("/{task_id}", response_model=Task)
def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    service: TaskService = Depends(get_task_service),
) -> Task:
    try:
        updated = service.update_task(task_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated


@router.get("/{task_id}/children", response_model=ChildTaskStatusBoard)
def get_task_children_status(
    task_id: UUID,
    service: TaskService = Depends(get_task_service),
) -> ChildTaskStatusBoard:
    board = service.get_child_status_board(task_id)
    if board is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return board


class TaskModelSwitchRequest(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    target_agent: str = Field(default="coder", min_length=1)
    token_budget: int = Field(default=8_000, ge=256, le=200_000)
    reason: str | None = None


@router.post("/{task_id}/model-switch", response_model=TaskModelSwitchResult)
def switch_task_model(
    task_id: UUID,
    payload: TaskModelSwitchRequest,
    service: TaskService = Depends(get_task_service),
) -> TaskModelSwitchResult:
    try:
        return service.switch_model(
            task_id=task_id,
            provider=payload.provider,
            model=payload.model,
            target_agent=payload.target_agent,
            token_budget=payload.token_budget,
            reason=payload.reason,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/{task_id}/model-switches", response_model=list[TaskModelSwitchRecord])
def list_task_model_switches(
    task_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    service: TaskService = Depends(get_task_service),
) -> list[TaskModelSwitchRecord]:
    try:
        return service.list_model_switches(task_id=task_id, limit=limit)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{task_id}/model-policy", response_model=TaskModelPolicy)
def get_task_model_policy(
    task_id: UUID,
    service: TaskService = Depends(get_task_service),
) -> TaskModelPolicy:
    try:
        return service.get_model_policy(task_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.put("/{task_id}/model-policy", response_model=TaskModelPolicy)
def update_task_model_policy(
    task_id: UUID,
    payload: TaskModelPolicyUpdate,
    service: TaskService = Depends(get_task_service),
) -> TaskModelPolicy:
    try:
        return service.update_model_policy(task_id, payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
