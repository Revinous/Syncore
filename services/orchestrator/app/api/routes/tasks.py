from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from packages.contracts.python.models import Task, TaskCreate, TaskDetail, TaskUpdate
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services.task_service import (
    ChildTaskStatusBoard,
    TaskModelPolicy,
    TaskModelPolicyUpdate,
    TaskModelSwitchRecord,
    TaskModelSwitchResult,
    TaskService,
)
from app.store_factory import build_memory_store

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_task_service(settings: Settings = Depends(get_settings)) -> TaskService:
    configured = {"local_echo"}
    hints = {"local_echo": "local_echo"}
    if (settings.openai_api_key or "").strip():
        configured.add("openai")
        hints["openai"] = "gpt-5.4"
    if (settings.anthropic_api_key or "").strip():
        configured.add("anthropic")
        hints["anthropic"] = "claude-3-7-sonnet-latest"
    if (settings.gemini_api_key or "").strip():
        configured.add("gemini")
        hints["gemini"] = "gemini-2.5-pro"
    return TaskService(
        build_memory_store(settings),
        configured_providers=configured,
        provider_model_hints=hints,
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
