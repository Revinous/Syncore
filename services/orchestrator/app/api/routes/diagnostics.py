from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
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


class DiagnosticsConfig(BaseModel):
    environment: str
    runtime_mode: str
    db_backend: str
    redis_required: bool
    redis_url: str
    postgres_dsn: str
    sqlite_db_path: str


class DiagnosticsOverview(BaseModel):
    service: str
    environment: str
    runtime_mode: str
    db_backend: str
    redis_required: bool


class DiagnosticsRoutes(BaseModel):
    routes: list[str]


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


@router.get("", response_model=DiagnosticsOverview)
def diagnostics_overview(settings: Settings = Depends(get_settings)) -> DiagnosticsOverview:
    return DiagnosticsOverview(
        service="orchestrator",
        environment=settings.environment,
        runtime_mode=settings.syncore_runtime_mode,
        db_backend=settings.syncore_db_backend,
        redis_required=settings.redis_required,
    )


@router.get("/config", response_model=DiagnosticsConfig)
def diagnostics_config(settings: Settings = Depends(get_settings)) -> DiagnosticsConfig:
    return DiagnosticsConfig(
        environment=settings.environment,
        runtime_mode=settings.syncore_runtime_mode,
        db_backend=settings.syncore_db_backend,
        redis_required=settings.redis_required,
        redis_url=settings.redis_url,
        postgres_dsn=settings.postgres_dsn,
        sqlite_db_path=settings.sqlite_db_path,
    )


@router.get("/routes", response_model=DiagnosticsRoutes)
def diagnostics_routes(request: Request) -> DiagnosticsRoutes:
    paths = sorted(
        {
            f"{','.join(sorted(route.methods or []))} {route.path}"
            for route in request.app.routes
            if getattr(route, "path", None)
        }
    )
    return DiagnosticsRoutes(routes=paths)
