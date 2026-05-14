from __future__ import annotations

from app.config import Settings
from app.services.run_execution_service import RunExecutionService
from app.services.run_queue_service import RunQueueService
from app.services.task_service import TaskService
from app.store_factory import build_memory_store


def build_run_execution_service(settings: Settings) -> RunExecutionService:
    return RunExecutionService.from_settings(settings)


def build_run_queue_service(settings: Settings) -> RunQueueService:
    return RunQueueService.from_settings(settings)


def build_task_service(settings: Settings) -> TaskService:
    configured = {"local_echo"}
    hints = {"local_echo": "local_echo"}
    if (settings.openai_api_key or "").strip():
        configured.add("openai")
        hints["openai"] = "gpt-5.4"
    if (settings.anthropic_api_key or "").strip():
        configured.add("anthropic")
        hints["anthropic"] = "claude-3-7-sonnet-latest"
    if (settings.gemini_api_key or "").strip():
        configured.add("gemini")
        hints["gemini"] = "gemini-2.5-pro"
    return TaskService(
        build_memory_store(settings),
        configured_providers=configured,
        provider_model_hints=hints,
    )
