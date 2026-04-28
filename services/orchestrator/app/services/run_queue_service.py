from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from packages.contracts.python.models import RunExecutionRequest
from services.memory import MemoryStoreProtocol, create_memory_store

from app.config import Settings
from app.observability import log_event
from app.services.run_execution_service import RunExecutionService


@dataclass(frozen=True)
class QueueScanResult:
    job_id: str
    task_id: UUID
    status: str
    run_id: UUID | None = None
    note: str = ""


class RunQueueService:
    def __init__(self, *, store: MemoryStoreProtocol, run_execution: RunExecutionService) -> None:
        self._store = store
        self._run_execution = run_execution

    @classmethod
    def from_settings(cls, settings: Settings) -> "RunQueueService":
        store = create_memory_store(
            db_backend=settings.syncore_db_backend,
            postgres_dsn=settings.postgres_dsn,
            sqlite_db_path=settings.sqlite_db_path,
        )
        return cls(store=store, run_execution=RunExecutionService.from_settings(settings))

    def enqueue(self, payload: RunExecutionRequest, max_attempts: int = 3) -> dict[str, object]:
        return self._store.enqueue_run_job(
            task_id=payload.task_id,
            payload=payload.model_dump(mode="json"),
            max_attempts=max_attempts,
        )

    def scan_once(self, limit: int = 10) -> list[QueueScanResult]:
        bounded_limit = min(max(limit, 1), 100)
        results: list[QueueScanResult] = []
        for _ in range(bounded_limit):
            job = self._store.claim_next_run_job()
            if job is None:
                break
            results.append(self._execute_claimed_job(job))
        return results

    def _execute_claimed_job(self, job: dict[str, object]) -> QueueScanResult:
        job_id = str(job["job_id"])
        task_id = UUID(str(job["task_id"]))
        payload_data = job.get("payload")
        if not isinstance(payload_data, dict):
            self._store.complete_run_job(
                job_id=job_id,
                status="failed",
                error="Invalid queued payload.",
            )
            return QueueScanResult(
                job_id=job_id,
                task_id=task_id,
                status="failed",
                note="Invalid queued payload.",
            )

        try:
            request = RunExecutionRequest.model_validate(payload_data)
        except Exception as error:
            self._store.complete_run_job(
                job_id=job_id,
                status="failed",
                error=f"Payload validation failed: {error}",
            )
            return QueueScanResult(
                job_id=job_id,
                task_id=task_id,
                status="failed",
                note="Payload validation failed.",
            )

        try:
            response = self._run_execution.execute(request)
            self._store.complete_run_job(
                job_id=job_id,
                status="completed",
                run_id=response.run_id,
            )
            log_event(
                "run.queue.completed",
                job_id=job_id,
                task_id=str(task_id),
                run_id=str(response.run_id),
            )
            return QueueScanResult(
                job_id=job_id,
                task_id=task_id,
                status="completed",
                run_id=response.run_id,
                note="Queued run completed.",
            )
        except Exception as error:
            completed = self._store.complete_run_job(
                job_id=job_id,
                status="retry",
                error=str(error),
            )
            next_status = str(completed.get("status", "failed")) if completed else "failed"
            log_event(
                "run.queue.failed",
                job_id=job_id,
                task_id=str(task_id),
                status=next_status,
                error=str(error)[:250],
            )
            return QueueScanResult(
                job_id=job_id,
                task_id=task_id,
                status=next_status,
                note=f"Queued run failed: {error}",
            )
