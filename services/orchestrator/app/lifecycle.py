import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.config import get_settings
from app.observability import log_event
from app.services.autonomy_service import AutonomyService
from app.services.run_queue_service import RunQueueService


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log_event("app.startup", environment=settings.environment)
    worker_task: asyncio.Task[None] | None = None
    queue_worker_task: asyncio.Task[None] | None = None

    if settings.autonomy_enabled:
        autonomy_service = AutonomyService.from_settings(settings)
        worker_task = asyncio.create_task(
            _autonomy_loop(
                service=autonomy_service,
                interval_seconds=settings.autonomy_poll_interval_seconds,
            ),
            name="syncore-autonomy-loop",
        )
        log_event(
            "autonomy.loop.started",
            interval_seconds=settings.autonomy_poll_interval_seconds,
        )
    if settings.queue_worker_enabled:
        queue_service = RunQueueService.from_settings(settings)
        queue_worker_task = asyncio.create_task(
            _run_queue_loop(
                service=queue_service,
                interval_seconds=settings.queue_worker_poll_interval_seconds,
            ),
            name="syncore-run-queue-loop",
        )
        log_event(
            "run.queue.loop.started",
            interval_seconds=settings.queue_worker_poll_interval_seconds,
        )
    yield
    if queue_worker_task is not None:
        queue_worker_task.cancel()
        try:
            await queue_worker_task
        except asyncio.CancelledError:
            pass
        log_event("run.queue.loop.stopped")
    if worker_task is not None:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        log_event("autonomy.loop.stopped")
    log_event("app.shutdown", environment=settings.environment)


async def _autonomy_loop(*, service: AutonomyService, interval_seconds: float) -> None:
    safe_interval = max(interval_seconds, 0.2)
    while True:
        try:
            results = await asyncio.to_thread(service.process_pending_tasks_once, 50)
            if results:
                log_event(
                    "autonomy.loop.tick",
                    processed=len(results),
                    statuses=[result.status for result in results],
                )
        except Exception as error:
            log_event("autonomy.loop.error", error=str(error))
        await asyncio.sleep(safe_interval)


async def _run_queue_loop(*, service: RunQueueService, interval_seconds: float) -> None:
    safe_interval = max(interval_seconds, 0.2)
    while True:
        try:
            results = await asyncio.to_thread(service.scan_once, 10)
            if results:
                log_event(
                    "run.queue.loop.tick",
                    processed=len(results),
                    statuses=[result.status for result in results],
                )
        except Exception as error:
            log_event("run.queue.loop.error", error=str(error))
        await asyncio.sleep(safe_interval)
