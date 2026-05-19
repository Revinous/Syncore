from __future__ import annotations

from app.config import Settings
from app.services.provider_config import configured_provider_hints
from app.services.run_execution_service import RunExecutionService
from app.services.run_queue_service import RunQueueService
from app.services.task_service import TaskService
from app.store_factory import build_memory_store


def build_run_execution_service(settings: Settings) -> RunExecutionService:
    return RunExecutionService.from_settings(settings)


def build_run_queue_service(settings: Settings) -> RunQueueService:
    return RunQueueService.from_settings(settings)


def build_task_service(settings: Settings) -> TaskService:
    configured, hints = configured_provider_hints(settings)
    return TaskService(
        build_memory_store(settings),
        configured_providers=configured,
        provider_model_hints=hints,
    )
