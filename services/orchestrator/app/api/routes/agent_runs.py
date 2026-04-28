from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from packages.contracts.python.models import AgentRun, AgentRunCreate, AgentRunUpdate

from app.config import Settings, get_settings
from app.services.agent_run_service import AgentRunResult, AgentRunService
from app.store_factory import build_memory_store

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


def get_agent_run_service(settings: Settings = Depends(get_settings)) -> AgentRunService:
    return AgentRunService(build_memory_store(settings))


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


@router.get("", response_model=list[AgentRun])
def list_agent_runs(
    task_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    service: AgentRunService = Depends(get_agent_run_service),
) -> list[AgentRun]:
    return service.list_runs(task_id=task_id, limit=limit)


@router.get("/{run_id}", response_model=AgentRun)
def get_agent_run(
    run_id: UUID,
    service: AgentRunService = Depends(get_agent_run_service),
) -> AgentRun:
    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@router.get("/{run_id}/result", response_model=AgentRunResult)
def get_agent_run_result(
    run_id: UUID,
    service: AgentRunService = Depends(get_agent_run_service),
) -> AgentRunResult:
    result = service.get_run_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return result
