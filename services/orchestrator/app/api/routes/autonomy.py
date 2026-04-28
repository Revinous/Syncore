from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services.autonomy_service import AutonomyService

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
