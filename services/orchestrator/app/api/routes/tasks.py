from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from packages.contracts.python.models import Task, TaskCreate, TaskDetail, TaskUpdate

from app.config import Settings, get_settings
from app.services.task_service import TaskService
from app.store_factory import build_memory_store

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_task_service(settings: Settings = Depends(get_settings)) -> TaskService:
    return TaskService(build_memory_store(settings))


@router.post("", response_model=Task, status_code=201)
def create_task(
    payload: TaskCreate,
    service: TaskService = Depends(get_task_service),
) -> Task:
    return service.create_task(payload)


@router.get("", response_model=list[Task])
def list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    service: TaskService = Depends(get_task_service),
) -> list[Task]:
    return service.list_tasks(limit=limit)


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
