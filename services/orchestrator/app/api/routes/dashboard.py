from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from services.analyst.digest import AnalystDigestService

from app.api.routes.health import probe_postgres, probe_redis, probe_sqlite
from app.config import Settings, get_settings
from app.store_factory import build_memory_store

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DashboardSummary(BaseModel):
    runtime_mode: str
    db_backend: str
    health: str
    services: dict[str, str]
    workspace_count: int = Field(ge=0)
    open_task_count: int = Field(ge=0)
    active_run_count: int = Field(ge=0)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    recent_batons: list[dict[str, Any]] = Field(default_factory=list)
    latest_digest: dict[str, Any] | None = None


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(settings: Settings = Depends(get_settings)) -> DashboardSummary:
    store = build_memory_store(settings)

    if settings.syncore_db_backend == "sqlite":
        db_status, _ = probe_sqlite(settings.sqlite_db_path)
    else:
        db_status, _ = probe_postgres(settings.postgres_dsn)

    if settings.redis_required:
        redis_status, _ = probe_redis(settings.redis_url)
    else:
        redis_status = "skipped"

    workspaces = store.list_workspaces(limit=500)
    tasks = store.list_tasks(limit=500)
    open_task_count = len([task for task in tasks if task.status != "completed"])

    runs = store.list_agent_runs(task_id=None, limit=500)
    active_run_count = len([run for run in runs if run.status in {"queued", "running"}])

    recent_events = [
        event.model_dump(mode="json") for event in store.list_project_events(task_id=None, limit=10)
    ]

    recent_batons: list[dict[str, Any]] = []
    for task in tasks:
        recent_batons.extend(
            packet.model_dump(mode="json") for packet in store.list_baton_packets(task.id, limit=2)
        )
    recent_batons.sort(key=lambda packet: packet["created_at"], reverse=True)
    recent_batons = recent_batons[:10]

    latest_digest: dict[str, Any] | None = None
    digest_service = AnalystDigestService()
    for task in tasks:
        events = store.list_project_events(task.id, limit=50)
        if events:
            latest_digest = digest_service.generate_digest(task.id, events).model_dump(mode="json")
            break

    health = "ok"
    if db_status != "ok" or (settings.redis_required and redis_status != "ok"):
        health = "degraded"

    return DashboardSummary(
        runtime_mode=settings.syncore_runtime_mode,
        db_backend=settings.syncore_db_backend,
        health=health,
        services={
            "database": db_status,
            "redis": redis_status,
        },
        workspace_count=len(workspaces),
        open_task_count=open_task_count,
        active_run_count=active_run_count,
        recent_events=recent_events,
        recent_batons=recent_batons,
        latest_digest=latest_digest,
    )
