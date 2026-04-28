import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.config import get_settings
from app.observability import log_event
from app.services.autonomy_service import AutonomyService


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log_event("app.startup", environment=settings.environment)
    worker_task: asyncio.Task[None] | None = None

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
    yield
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
