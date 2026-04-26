from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from packages.contracts.python.models import AgentRun, AgentRunCreate, AgentRunUpdate
from services.memory.store import MemoryStore

from app.config import Settings, get_settings
from app.services.agent_run_service import AgentRunService

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


def get_agent_run_service(settings: Settings = Depends(get_settings)) -> AgentRunService:
    return AgentRunService(MemoryStore(settings.postgres_dsn))


@router.post("", response_model=AgentRun, status_code=201)
def create_agent_run(
    payload: AgentRunCreate,
    service: AgentRunService = Depends(get_agent_run_service),
) -> AgentRun:
    try:
        return service.create_run(payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/{run_id}", response_model=AgentRun)
def update_agent_run(
    run_id: UUID,
    payload: AgentRunUpdate,
    service: AgentRunService = Depends(get_agent_run_service),
) -> AgentRun:
    try:
        updated = service.update_run(run_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if updated is None:
        raise HTTPException(status_code=404, detail="Agent run not found")

    return updated
