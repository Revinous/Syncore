from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from textwrap import shorten
from typing import Iterator
from uuid import UUID

from packages.contracts.python.models import (
    AgentRunCreate,
    AgentRunUpdate,
    ProjectEventCreate,
    RunExecutionRequest,
    RunExecutionResponse,
    RunStreamEvent,
)
from services.memory import MemoryStoreProtocol, create_memory_store

from app.config import Settings
from app.context.retrieval_refs import build_ref_id, estimate_tokens
from app.runs.providers import LlmProvider, LocalEchoProvider, OpenAIChatCompletionsProvider
from app.services.context_service import ContextService


class RunExecutionService:
    def __init__(
        self,
        *,
        store: MemoryStoreProtocol,
        context_service: ContextService,
        providers: dict[str, LlmProvider],
        default_provider: str,
    ) -> None:
        self._store = store
        self._context_service = context_service
        self._providers = providers
        self._default_provider = default_provider

    @classmethod
    def from_settings(cls, settings: Settings) -> "RunExecutionService":
        store = create_memory_store(
            db_backend=settings.syncore_db_backend,
            postgres_dsn=settings.postgres_dsn,
            sqlite_db_path=settings.sqlite_db_path,
        )
        context_service = ContextService(store)
        providers: dict[str, LlmProvider] = {
            "local_echo": LocalEchoProvider(),
        }
        openai_api_key = _resolve_openai_api_key(settings.openai_api_key)
        if openai_api_key:
            providers["openai"] = OpenAIChatCompletionsProvider(
                api_key=openai_api_key,
                base_url=settings.openai_base_url,
                timeout_seconds=settings.openai_timeout_seconds,
            )
        return cls(
            store=store,
            context_service=context_service,
            providers=providers,
            default_provider=settings.default_llm_provider,
        )

    def execute(self, payload: RunExecutionRequest) -> RunExecutionResponse:
        optimized_bundle = self._context_service.assemble_optimized_context(
            task_id=payload.task_id,
            target_agent=payload.target_agent,
            target_model=payload.target_model,
            token_budget=payload.token_budget,
        )
        provider_name, provider = self._resolve_provider(payload.provider)
        prompt = self._build_prompt(payload.prompt, optimized_bundle.optimized_context)

        run = self._store.create_agent_run(
            AgentRunCreate(
                task_id=payload.task_id,
                role=payload.agent_role,
                status="running",
                input_summary=shorten(
                    " ".join(payload.prompt.split()), width=300, placeholder=" ..."
                ),
            )
        )
        self._record_event(
            task_id=payload.task_id,
            event_type="run.started",
            event_data={
                "provider": provider_name,
                "target_model": payload.target_model,
                "target_agent": payload.target_agent,
            },
        )

        try:
            result = provider.complete(
                model=payload.target_model,
                prompt=prompt,
                system_prompt=payload.system_prompt,
                max_output_tokens=payload.max_output_tokens,
                temperature=payload.temperature,
            )
            completed_at = datetime.now(timezone.utc)
            input_tokens = estimate_tokens(prompt)
            output_tokens = estimate_tokens(result.output_text)
            total_tokens = input_tokens + output_tokens

            self._store.update_agent_run(
                run.id,
                AgentRunUpdate(
                    status="completed",
                    output_summary=shorten(result.output_text, width=500, placeholder=" ..."),
                ),
            )
            output_ref_id = self._store_run_output_reference(
                task_id=payload.task_id,
                run_id=run.id,
                provider=provider_name,
                model=payload.target_model,
                output_text=result.output_text,
            )
            self._record_event(
                task_id=payload.task_id,
                event_type="run.completed",
                event_data={
                    "provider": provider_name,
                    "target_model": payload.target_model,
                    "estimated_input_tokens": input_tokens,
                    "estimated_output_tokens": output_tokens,
                    "output_ref_id": output_ref_id,
                },
            )
            return RunExecutionResponse(
                run_id=run.id,
                task_id=payload.task_id,
                status="completed",
                provider=provider_name,
                target_agent=payload.target_agent,
                target_model=payload.target_model,
                output_text=result.output_text,
                estimated_input_tokens=input_tokens,
                estimated_output_tokens=output_tokens,
                total_estimated_tokens=total_tokens,
                optimized_bundle_id=optimized_bundle.bundle_id,
                included_refs=optimized_bundle.included_refs,
                warnings=optimized_bundle.warnings,
                created_at=run.created_at,
                completed_at=completed_at,
            )
        except Exception as error:
            self._store.update_agent_run(
                run.id,
                AgentRunUpdate(status="failed", error_message=str(error)[:500]),
            )
            self._record_event(
                task_id=payload.task_id,
                event_type="run.failed",
                event_data={
                    "provider": provider_name,
                    "target_model": payload.target_model,
                    "error": str(error)[:250],
                },
            )
            raise RuntimeError(f"Run execution failed: {error}") from error

    def stream_execute(self, payload: RunExecutionRequest) -> Iterator[RunStreamEvent]:
        optimized_bundle = self._context_service.assemble_optimized_context(
            task_id=payload.task_id,
            target_agent=payload.target_agent,
            target_model=payload.target_model,
            token_budget=payload.token_budget,
        )
        provider_name, provider = self._resolve_provider(payload.provider)
        prompt = self._build_prompt(payload.prompt, optimized_bundle.optimized_context)

        run = self._store.create_agent_run(
            AgentRunCreate(
                task_id=payload.task_id,
                role=payload.agent_role,
                status="running",
                input_summary=shorten(
                    " ".join(payload.prompt.split()), width=300, placeholder=" ..."
                ),
            )
        )
        self._record_event(
            task_id=payload.task_id,
            event_type="run.started",
            event_data={
                "provider": provider_name,
                "target_model": payload.target_model,
                "target_agent": payload.target_agent,
            },
        )

        yield RunStreamEvent(
            event="started",
            run_id=run.id,
            task_id=payload.task_id,
            provider=provider_name,
            target_model=payload.target_model,
        )

        full_output_parts: list[str] = []
        try:
            for chunk in provider.stream(
                model=payload.target_model,
                prompt=prompt,
                system_prompt=payload.system_prompt,
                max_output_tokens=payload.max_output_tokens,
                temperature=payload.temperature,
            ):
                full_output_parts.append(chunk)
                yield RunStreamEvent(
                    event="chunk",
                    run_id=run.id,
                    task_id=payload.task_id,
                    provider=provider_name,
                    target_model=payload.target_model,
                    content=chunk,
                )

            full_output = "".join(full_output_parts)
            output_tokens = estimate_tokens(full_output)

            self._store.update_agent_run(
                run.id,
                AgentRunUpdate(
                    status="completed",
                    output_summary=shorten(full_output, width=500, placeholder=" ..."),
                ),
            )
            output_ref_id = self._store_run_output_reference(
                task_id=payload.task_id,
                run_id=run.id,
                provider=provider_name,
                model=payload.target_model,
                output_text=full_output,
            )
            self._record_event(
                task_id=payload.task_id,
                event_type="run.completed",
                event_data={
                    "provider": provider_name,
                    "target_model": payload.target_model,
                    "estimated_input_tokens": estimate_tokens(prompt),
                    "estimated_output_tokens": output_tokens,
                    "output_ref_id": output_ref_id,
                },
            )
            yield RunStreamEvent(
                event="completed",
                run_id=run.id,
                task_id=payload.task_id,
                provider=provider_name,
                target_model=payload.target_model,
                estimated_output_tokens=output_tokens,
            )
        except Exception as error:
            self._store.update_agent_run(
                run.id,
                AgentRunUpdate(status="failed", error_message=str(error)[:500]),
            )
            self._record_event(
                task_id=payload.task_id,
                event_type="run.failed",
                event_data={
                    "provider": provider_name,
                    "target_model": payload.target_model,
                    "error": str(error)[:250],
                },
            )
            yield RunStreamEvent(
                event="error",
                run_id=run.id,
                task_id=payload.task_id,
                provider=provider_name,
                target_model=payload.target_model,
                error=str(error),
            )

    def _resolve_provider(self, requested_provider: str | None) -> tuple[str, LlmProvider]:
        provider_name = requested_provider or self._default_provider
        provider = self._providers.get(provider_name)
        if provider is None:
            available = ", ".join(sorted(self._providers.keys()))
            raise ValueError(
                f"Provider '{provider_name}' is not configured. Available providers: {available}."
            )
        return provider_name, provider

    def _build_prompt(self, user_prompt: str, optimized_context: dict[str, object]) -> str:
        rendered_context = str(optimized_context.get("rendered_prompt", "")).strip()
        prompt_parts = [
            "You are executing a Syncore run with optimized context.",
            "Use context first; request full artifacts by context_ref only when needed.",
            "",
            "## Worker Request",
            user_prompt.strip(),
            "",
            "## Optimized Context",
            rendered_context,
        ]
        return "\n".join(prompt_parts).strip()

    def _record_event(
        self,
        *,
        task_id: UUID,
        event_type: str,
        event_data: dict[str, str | int | float | bool | None],
    ) -> None:
        self._store.save_project_event(
            ProjectEventCreate(task_id=task_id, event_type=event_type, event_data=event_data)
        )

    def _store_run_output_reference(
        self,
        *,
        task_id: UUID,
        run_id: UUID,
        provider: str,
        model: str,
        output_text: str,
    ) -> str:
        excerpt = " ".join(output_text.split())
        summary = shorten(excerpt, width=220, placeholder=" ...")
        retrieval_hint = (
            f"run_id={run_id} provider={provider} model={model}; "
            "retrieve via GET /context/references/{ref_id}"
        )
        ref_id = build_ref_id(task_id, "run_output", output_text)
        record = self._store.upsert_context_reference(
            ref_id=ref_id,
            task_id=task_id,
            content_type="run_output",
            original_content=output_text,
            summary=summary,
            retrieval_hint=retrieval_hint,
        )
        ref_id = str(record["ref_id"])
        self._record_event(
            task_id=task_id,
            event_type="run.output.stored",
            event_data={
                "run_id": str(run_id),
                "ref_id": ref_id,
                "provider": provider,
                "target_model": model,
                "chars": len(output_text),
            },
        )
        return ref_id


def _resolve_openai_api_key(configured_api_key: str | None) -> str | None:
    configured = (configured_api_key or "").strip()
    if configured and configured.lower() not in {"replace_me", "changeme", "your_api_key_here"}:
        return configured

    auth_path = os.getenv("SYNCORE_OPENAI_AUTH_PATH")
    if auth_path:
        path = Path(auth_path).expanduser()
    else:
        path = Path.home() / ".syncore" / "openai_credentials.json"

    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    file_key = str(payload.get("api_key", "")).strip()
    if not file_key:
        return None
    return file_key
