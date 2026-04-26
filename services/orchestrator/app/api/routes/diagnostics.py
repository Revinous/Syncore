from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.store_factory import build_memory_store

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class TaskDiagnostics(BaseModel):
    task_id: UUID
    task_exists: bool
    agent_run_count: int
    baton_packet_count: int
    event_count: int


@router.get("/task/{task_id}", response_model=TaskDiagnostics)
def diagnostics_for_task(
    task_id: UUID,
    settings: Settings = Depends(get_settings),
) -> TaskDiagnostics:
    store = build_memory_store(settings)
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    runs = store.list_agent_runs(task_id)
    packets = store.list_baton_packets(task_id)
    events = store.list_project_events(task_id)

    return TaskDiagnostics(
        task_id=task_id,
        task_exists=True,
        agent_run_count=len(runs),
        baton_packet_count=len(packets),
        event_count=len(events),
    )
