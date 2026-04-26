from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from packages.contracts.python.models import ProjectEvent, ProjectEventCreate
from services.memory.store import MemoryStore

from app.config import Settings, get_settings
from app.services.event_service import EventService

router = APIRouter(prefix="/project-events", tags=["project-events"])


def get_event_service(settings: Settings = Depends(get_settings)) -> EventService:
    return EventService(MemoryStore(settings.postgres_dsn))


@router.post("", response_model=ProjectEvent, status_code=201)
def create_project_event(
    payload: ProjectEventCreate,
    service: EventService = Depends(get_event_service),
) -> ProjectEvent:
    try:
        return service.create_event(payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{task_id}", response_model=list[ProjectEvent])
def list_project_events(
    task_id: UUID,
    limit: int = Query(default=100, ge=1, le=200),
    service: EventService = Depends(get_event_service),
) -> list[ProjectEvent]:
    return service.list_events(task_id=task_id, limit=limit)
