from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services.autonomy_service import AutonomyService
from app.store_factory import build_memory_store

router = APIRouter(prefix="/autonomy", tags=["autonomy"])


class AutonomyTaskResult(BaseModel):
    task_id: UUID
    status: str
    run_id: UUID | None = None
    note: str


class AutonomyScanResponse(BaseModel):
    processed: int = Field(ge=0)
    results: list[AutonomyTaskResult]


class AutonomyApprovalRequest(BaseModel):
    reason: str | None = None


class AutonomySnapshot(BaseModel):
    snapshot_id: str
    task_id: UUID
    cycle: int
    stage: str
    state: str
    strategy: str
    quality_score: int
    details: dict[str, object]
    created_at: str


def get_autonomy_service(settings: Settings = Depends(get_settings)) -> AutonomyService:
    return AutonomyService.from_settings(settings)


@router.post("/scan-once", response_model=AutonomyScanResponse)
def autonomy_scan_once(
    limit: int = Query(default=50, ge=1, le=200),
    service: AutonomyService = Depends(get_autonomy_service),
) -> AutonomyScanResponse:
    results = service.process_pending_tasks_once(limit=limit)
    return AutonomyScanResponse(
        processed=len(results),
        results=[
            AutonomyTaskResult(
                task_id=result.task_id,
                status=result.status,
                run_id=result.run_id,
                note=result.note,
            )
            for result in results
        ],
    )


@router.post("/tasks/{task_id}/run", response_model=AutonomyTaskResult)
def autonomy_run_task(
    task_id: UUID,
    service: AutonomyService = Depends(get_autonomy_service),
) -> AutonomyTaskResult:
    result = service.process_task(task_id)
    return AutonomyTaskResult(
        task_id=result.task_id,
        status=result.status,
        run_id=result.run_id,
        note=result.note,
    )


@router.post("/tasks/{task_id}/approve", response_model=AutonomyTaskResult)
def autonomy_approve_task(
    task_id: UUID,
    payload: AutonomyApprovalRequest,
    service: AutonomyService = Depends(get_autonomy_service),
) -> AutonomyTaskResult:
    result = service.set_approval(task_id=task_id, approved=True, reason=payload.reason)
    return AutonomyTaskResult(
        task_id=result.task_id,
        status=result.status,
        run_id=result.run_id,
        note=result.note,
    )


@router.post("/tasks/{task_id}/reject", response_model=AutonomyTaskResult)
def autonomy_reject_task(
    task_id: UUID,
    payload: AutonomyApprovalRequest,
    service: AutonomyService = Depends(get_autonomy_service),
) -> AutonomyTaskResult:
    result = service.set_approval(task_id=task_id, approved=False, reason=payload.reason)
    return AutonomyTaskResult(
        task_id=result.task_id,
        status=result.status,
        run_id=result.run_id,
        note=result.note,
    )


@router.get("/tasks/{task_id}/snapshots", response_model=list[AutonomySnapshot])
def autonomy_task_snapshots(
    task_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    settings: Settings = Depends(get_settings),
) -> list[AutonomySnapshot]:
    store = build_memory_store(settings)
    snapshots = store.list_autonomy_snapshots(task_id=task_id, limit=limit)
    return [
        AutonomySnapshot(
            snapshot_id=str(row.get("snapshot_id")),
            task_id=task_id,
            cycle=int(row.get("cycle") or 0),
            stage=str(row.get("stage") or ""),
            state=str(row.get("state") or ""),
            strategy=str(row.get("strategy") or ""),
            quality_score=int(row.get("quality_score") or 0),
            details=dict(row.get("details") or {}),
            created_at=str(row.get("created_at") or ""),
        )
        for row in snapshots
    ]
