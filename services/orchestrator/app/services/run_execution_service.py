from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
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
from app.observability import record_run_outcome
from app.runs.providers import (
    AnthropicMessagesProvider,
    GeminiGenerateContentProvider,
    LlmProvider,
    LocalEchoProvider,
    OpenAIChatCompletionsProvider,
    ProviderCapabilities,
)
from app.services.context_service import ContextService


class RunExecutionService:
    def __init__(
        self,
        *,
        store: MemoryStoreProtocol,
        context_service: ContextService,
        providers: dict[str, LlmProvider],
        default_provider: str,
        failover_enabled: bool,
        fallback_order: list[str],
        default_timeout_seconds: int,
        max_concurrent_runs_per_task: int,
        max_concurrent_runs_per_workspace: int,
    ) -> None:
        self._store = store
        self._context_service = context_service
        self._providers = providers
        self._default_provider = default_provider
        self._failover_enabled = failover_enabled
        self._fallback_order = fallback_order
        self._default_timeout_seconds = max(default_timeout_seconds, 5)
        self._max_concurrent_runs_per_task = max(max_concurrent_runs_per_task, 1)
        self._max_concurrent_runs_per_workspace = max(max_concurrent_runs_per_workspace, 1)

    @classmethod
    def from_settings(cls, settings: Settings) -> "RunExecutionService":
        store = create_memory_store(
            db_backend=settings.syncore_db_backend,
            postgres_dsn=settings.postgres_dsn,
            sqlite_db_path=settings.sqlite_db_path,
        )
        context_service = ContextService(
            store,
            layering_enabled=settings.context_layering_enabled,
            layering_dual_mode=settings.context_layering_dual_mode,
        )
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
        anthropic_api_key = (settings.anthropic_api_key or "").strip()
        if anthropic_api_key:
            providers["anthropic"] = AnthropicMessagesProvider(
                api_key=anthropic_api_key,
                base_url=settings.anthropic_base_url,
                api_version=settings.anthropic_api_version,
                timeout_seconds=settings.openai_timeout_seconds,
            )
        gemini_api_key = (settings.gemini_api_key or "").strip()
        if gemini_api_key:
            providers["gemini"] = GeminiGenerateContentProvider(
                api_key=gemini_api_key,
                base_url=settings.gemini_base_url,
                timeout_seconds=settings.openai_timeout_seconds,
            )
        fallback_order = [
            p.strip().lower()
            for p in settings.provider_fallback_order.split(",")
            if p.strip()
        ]
        return cls(
            store=store,
            context_service=context_service,
            providers=providers,
            default_provider=settings.default_llm_provider,
            failover_enabled=settings.provider_failover_enabled,
            fallback_order=fallback_order,
            default_timeout_seconds=settings.run_default_timeout_seconds,
            max_concurrent_runs_per_task=settings.max_concurrent_runs_per_task,
            max_concurrent_runs_per_workspace=settings.max_concurrent_runs_per_workspace,
        )

    def execute(self, payload: RunExecutionRequest) -> RunExecutionResponse:
        duplicate = self._maybe_get_idempotent_response(payload)
        if duplicate is not None:
            return duplicate
        self._enforce_concurrency_limits(payload.task_id)

        optimized_bundle = self._context_service.assemble_optimized_context(
            task_id=payload.task_id,
            target_agent=payload.target_agent,
            target_model=payload.target_model,
            token_budget=payload.token_budget,
        )
        prompt = self._build_prompt(payload.prompt, optimized_bundle.optimized_context)
        prompt_ref_id = self._store_text_reference(
            task_id=payload.task_id,
            content_type="run_prompt",
            content_text=prompt,
            retrieval_hint="Full worker prompt snapshot for this run.",
        )
        context_ref_id = self._store_text_reference(
            task_id=payload.task_id,
            content_type="run_context_rendered",
            content_text=str(optimized_bundle.optimized_context.get("rendered_prompt", "")),
            retrieval_hint="Rendered optimized context used for this run.",
        )

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
        provider_candidates = self._provider_candidates(payload.provider)
        requested_provider = (
            provider_candidates[0] if provider_candidates else self._default_provider
        )
        self._record_event(
            task_id=payload.task_id,
            event_type="run.started",
            event_data={
                "run_id": str(run.id),
                "provider": requested_provider,
                "target_model": payload.target_model,
                "target_agent": payload.target_agent,
                "prompt_ref_id": prompt_ref_id,
                "context_ref_id": context_ref_id,
            },
        )

        try:
            provider_name, result = self._complete_with_failover(payload=payload, prompt=prompt)
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
            response = RunExecutionResponse(
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
            self._persist_idempotent_response(payload, response)
            record_run_outcome(success=True)
            return response
        except Exception as error:
            self._store.update_agent_run(
                run.id,
                AgentRunUpdate(status="failed", error_message=str(error)[:500]),
            )
            self._record_event(
                task_id=payload.task_id,
                event_type="run.failed",
                event_data={
                    "provider": requested_provider,
                    "target_model": payload.target_model,
                    "error": str(error)[:250],
                },
            )
            record_run_outcome(success=False)
            raise RuntimeError(f"Run execution failed: {error}") from error

    def stream_execute(self, payload: RunExecutionRequest) -> Iterator[RunStreamEvent]:
        duplicate = self._maybe_get_idempotent_response(payload)
        if duplicate is not None:
            yield RunStreamEvent(
                event="completed",
                run_id=duplicate.run_id,
                task_id=duplicate.task_id,
                provider=duplicate.provider,
                target_model=duplicate.target_model,
                estimated_output_tokens=duplicate.estimated_output_tokens,
            )
            return
        self._enforce_concurrency_limits(payload.task_id)

        optimized_bundle = self._context_service.assemble_optimized_context(
            task_id=payload.task_id,
            target_agent=payload.target_agent,
            target_model=payload.target_model,
            token_budget=payload.token_budget,
        )
        provider_name, provider = self._resolve_provider(payload.provider)
        prompt = self._build_prompt(payload.prompt, optimized_bundle.optimized_context)
        prompt_ref_id = self._store_text_reference(
            task_id=payload.task_id,
            content_type="run_prompt",
            content_text=prompt,
            retrieval_hint="Full worker prompt snapshot for this run.",
        )
        context_ref_id = self._store_text_reference(
            task_id=payload.task_id,
            content_type="run_context_rendered",
            content_text=str(optimized_bundle.optimized_context.get("rendered_prompt", "")),
            retrieval_hint="Rendered optimized context used for this run.",
        )

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
                "run_id": str(run.id),
                "provider": provider_name,
                "target_model": payload.target_model,
                "target_agent": payload.target_agent,
                "prompt_ref_id": prompt_ref_id,
                "context_ref_id": context_ref_id,
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
            record_run_outcome(success=True)
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
            record_run_outcome(success=False)

    def _resolve_provider(self, requested_provider: str | None) -> tuple[str, LlmProvider]:
        provider_name = requested_provider or self._default_provider
        provider = self._providers.get(provider_name)
        if provider is None:
            available = ", ".join(sorted(self._providers.keys()))
            raise ValueError(
                f"Provider '{provider_name}' is not configured. Available providers: {available}."
            )
        return provider_name, provider

    def list_provider_capabilities(self) -> list[ProviderCapabilities]:
        return [self._providers[name].capabilities() for name in sorted(self._providers.keys())]

    def _complete_with_failover(
        self, *, payload: RunExecutionRequest, prompt: str
    ) -> tuple[str, object]:
        candidates = self._provider_candidates(payload.provider)
        timeout_seconds = payload.timeout_seconds or self._default_timeout_seconds
        errors: list[str] = []
        for provider_name in candidates:
            provider = self._providers.get(provider_name)
            if provider is None:
                continue
            try:
                result = self._run_complete_with_timeout(
                    provider=provider,
                    payload=payload,
                    prompt=prompt,
                    timeout_seconds=timeout_seconds,
                )
                return provider_name, result
            except Exception as error:
                errors.append(f"{provider_name}: {error}")
                continue
        raise RuntimeError("All provider attempts failed: " + " | ".join(errors))

    def _provider_candidates(self, requested_provider: str | None) -> list[str]:
        primary = (requested_provider or self._default_provider).strip().lower()
        if not self._failover_enabled:
            return [primary]
        ordered = [primary]
        for candidate in self._fallback_order:
            if candidate and candidate not in ordered:
                ordered.append(candidate)
        for candidate in sorted(self._providers.keys()):
            if candidate not in ordered:
                ordered.append(candidate)
        return ordered

    def _run_complete_with_timeout(
        self,
        *,
        provider: LlmProvider,
        payload: RunExecutionRequest,
        prompt: str,
        timeout_seconds: int,
    ):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                provider.complete,
                model=payload.target_model,
                prompt=prompt,
                system_prompt=payload.system_prompt,
                max_output_tokens=payload.max_output_tokens,
                temperature=payload.temperature,
            )
            try:
                return future.result(timeout=timeout_seconds)
            except FutureTimeoutError as error:
                future.cancel()
                raise RuntimeError(
                    f"Provider timeout after {timeout_seconds}s for model {payload.target_model}."
                ) from error

    def _maybe_get_idempotent_response(
        self, payload: RunExecutionRequest
    ) -> RunExecutionResponse | None:
        key = (payload.idempotency_key or "").strip()
        if not key:
            return None
        ref = self._store.get_context_reference(f"idem_{payload.task_id.hex}_{key}")
        if ref is None:
            return None
        try:
            parsed = json.loads(str(ref["original_content"]))
        except (TypeError, json.JSONDecodeError):
            return None
        return RunExecutionResponse.model_validate(parsed)

    def _persist_idempotent_response(
        self, payload: RunExecutionRequest, response: RunExecutionResponse
    ) -> None:
        key = (payload.idempotency_key or "").strip()
        if not key:
            return
        response_json = response.model_dump_json()
        idem_ref = f"idem_{payload.task_id.hex}_{key}"
        self._store.upsert_context_reference(
            ref_id=idem_ref,
            task_id=payload.task_id,
            content_type="run_response",
            original_content=response_json,
            summary=f"Idempotent response for task {payload.task_id}",
            retrieval_hint="Internal idempotency replay record.",
        )

    def _enforce_concurrency_limits(self, task_id: UUID) -> None:
        task_runs = self._store.list_agent_runs(task_id=task_id, limit=200)
        active_for_task = [run for run in task_runs if run.status in {"queued", "running"}]
        if len(active_for_task) >= self._max_concurrent_runs_per_task:
            raise RuntimeError(
                f"Task concurrency limit reached ({self._max_concurrent_runs_per_task})."
            )

        task = self._store.get_task(task_id)
        if task is None or task.workspace_id is None:
            return
        workspace_tasks = self._store.list_tasks(limit=500, workspace_id=task.workspace_id)
        active_workspace = 0
        for candidate in workspace_tasks:
            runs = self._store.list_agent_runs(task_id=candidate.id, limit=200)
            active_workspace += len([run for run in runs if run.status in {"queued", "running"}])
            if active_workspace >= self._max_concurrent_runs_per_workspace:
                raise RuntimeError(
                    "Workspace concurrency limit reached "
                    f"({self._max_concurrent_runs_per_workspace})."
                )

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

    def _store_text_reference(
        self,
        *,
        task_id: UUID,
        content_type: str,
        content_text: str,
        retrieval_hint: str,
    ) -> str:
        if not content_text.strip():
            return ""
        summary = shorten(" ".join(content_text.split()), width=220, placeholder=" ...")
        ref_id = build_ref_id(task_id, content_type, content_text)
        record = self._store.upsert_context_reference(
            ref_id=ref_id,
            task_id=task_id,
            content_type=content_type,
            original_content=content_text,
            summary=summary,
            retrieval_hint=retrieval_hint,
        )
        return str(record["ref_id"])


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
