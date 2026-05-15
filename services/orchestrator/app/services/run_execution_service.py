from __future__ import annotations

import json
import os
import shutil
import sys
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
from services.analyst.digest import AnalystDigestService
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
from app.services.execution_policy import ExecutionPolicyResolver
from app.services.workspace_acceptance_service import string_list
from app.services.workspace_action_dispatcher import WorkspaceActionDispatcher
from app.services.workspace_execution_coordinator import WorkspaceExecutionCoordinator
from app.services.workspace_execution_failures import WorkspaceExecutionFailureHandler
from app.services.workspace_execution_finalizer import WorkspaceExecutionFinalizer
from app.services.workspace_execution_utils import (
    check_action_allowed,
    normalize_workspace_command,
    resolve_workspace_path,
    runner_default_command,
)
from app.services.workspace_learning_service import WorkspaceLearningService
from app.services.workspace_operations_service import WorkspaceOperationsService
from app.services.workspace_planner import WorkspacePlanner
from app.services.workspace_policy_profiles import WORKSPACE_POLICY_PROFILES
from app.services.workspace_preflight_service import WorkspacePreflightService
from app.services.workspace_verification_service import WorkspaceVerificationService


class RunExecutionService:
    WORKSPACE_POLICY_PROFILES = WORKSPACE_POLICY_PROFILES

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
        self._digest_service = AnalystDigestService()
        self._policy_resolver = ExecutionPolicyResolver(self.WORKSPACE_POLICY_PROFILES)
        self._workspace_learning = WorkspaceLearningService(self._store)
        self._workspace_planner = WorkspacePlanner()
        self._workspace_preflight_service = WorkspacePreflightService(
            providers=self._providers,
            default_provider=self._default_provider,
            setup_command_resolver=runner_default_command,
        )
        self._workspace_operations = WorkspaceOperationsService(
            store=self._store,
            record_event=self._record_event,
            binary_available=self._binary_available,
        )
        self._workspace_dispatcher = WorkspaceActionDispatcher(
            check_action_allowed=check_action_allowed,
            write_with_diff=self._workspace_operations.write_with_diff,
            patch_with_diff=self._workspace_operations.patch_with_diff,
            delete_with_diff=self._workspace_operations.delete_with_diff,
            move_with_diff=self._workspace_operations.move_with_diff,
            read_file=self._workspace_operations.read_file,
            search_code=self._workspace_operations.search_code,
            store_text_reference=self._store_text_reference,
            run_workspace_command=self._workspace_operations.run_workspace_command,
            runner_default_command=runner_default_command,
        )
        self._workspace_finalizer = WorkspaceExecutionFinalizer(
            store=self._store,
            digest_service=self._digest_service,
            workspace_learning=self._workspace_learning,
            parse_uuid=_parse_uuid,
        )
        def _workspace_run_command(root: Path, command: str, policy: dict[str, object]):
            return self._safe_run_workspace_command(root, command, policy=policy)

        self._workspace_verifier = WorkspaceVerificationService(
            run_command=_workspace_run_command,
            normalize_command=self._normalize_workspace_command,
        )
        self._workspace_failures = WorkspaceExecutionFailureHandler(
            finalizer=self._workspace_finalizer,
            record_event=self._record_event,
        )
        self._workspace_execution = WorkspaceExecutionCoordinator(
            store=self._store,
            default_provider=self._default_provider,
            policy_resolver=self._policy_resolver,
            planner=self._workspace_planner,
            preflight_service=self._workspace_preflight_service,
            dispatcher=self._workspace_dispatcher,
            verifier=self._workspace_verifier,
            finalizer=self._workspace_finalizer,
            resolve_provider=self._resolve_provider,
            task_preferences=self._task_preferences,
            attempt_auto_repair=self._workspace_operations.attempt_auto_repair,
            record_event=self._record_event,
            failure_handler=self._workspace_failures,
        )

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
            layering_fallback_threshold_pct=settings.context_layering_fallback_threshold_pct,
            layering_fallback_min_samples=settings.context_layering_fallback_min_samples,
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
            p.strip().lower() for p in settings.provider_fallback_order.split(",") if p.strip()
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

    def execute_workspace_loop(
        self,
        payload: RunExecutionRequest,
        *,
        max_steps: int = 3,
        policy_profile: str = "balanced",
        dry_run: bool = False,
        require_approval: bool = False,
    ) -> dict[str, object]:
        return self._workspace_execution.execute_loop(
            payload,
            max_steps=max_steps,
            policy_profile=policy_profile,
            dry_run=dry_run,
            require_approval=require_approval,
        )

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
        explicit = (requested_provider or "").strip().lower()
        primary = (explicit or self._default_provider).strip().lower()
        if explicit:
            return [primary]
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

    def _safe_write_with_diff(
        self,
        *,
        task_id: UUID,
        root: Path,
        relative_path: str,
        content: str,
    ) -> str:
        return self._workspace_operations.write_with_diff(
            task_id=task_id,
            root=root,
            relative_path=relative_path,
            content=content,
        )

    def _safe_patch_with_diff(
        self,
        *,
        task_id: UUID,
        root: Path,
        relative_path: str,
        before_text: str,
        after_text: str,
    ) -> str:
        return self._workspace_operations.patch_with_diff(
            task_id=task_id,
            root=root,
            relative_path=relative_path,
            before_text=before_text,
            after_text=after_text,
        )

    def _safe_delete_with_diff(
        self,
        *,
        task_id: UUID,
        root: Path,
        relative_path: str,
    ) -> str:
        return self._workspace_operations.delete_with_diff(
            task_id=task_id,
            root=root,
            relative_path=relative_path,
        )

    def _safe_move_with_diff(
        self,
        *,
        task_id: UUID,
        root: Path,
        source_path: str,
        destination_path: str,
    ) -> str:
        return self._workspace_operations.move_with_diff(
            task_id=task_id,
            root=root,
            source_path=source_path,
            destination_path=destination_path,
        )

    def _safe_run_workspace_command(
        self,
        root: Path,
        command: str,
        *,
        policy: dict[str, object],
    ) -> dict[str, object]:
        return self._workspace_operations.run_workspace_command(root, command, policy=policy)

    def _safe_read_file(self, *, root: Path, relative_path: str) -> str:
        return self._workspace_operations.read_file(root=root, relative_path=relative_path)

    def _safe_search_code(self, *, root: Path, pattern: str) -> list[str]:
        return self._workspace_operations.search_code(root=root, pattern=pattern)

    def _attempt_workspace_auto_repair(
        self,
        *,
        task_id: UUID,
        root: Path,
        runner: dict[str, object],
        runbook: dict[str, object],
        policy: dict[str, object],
    ) -> bool:
        return self._workspace_operations.attempt_auto_repair(
            task_id=task_id,
            root=root,
            runner=runner,
            runbook=runbook,
            policy=policy,
        )

    def _task_preferences(self, task_id: UUID) -> dict[str, str]:
        list_events = getattr(self._store, "list_project_events", None)
        if not callable(list_events):
            return {}
        events = list_events(task_id=task_id, limit=500)
        for event in reversed(events):
            if getattr(event, "event_type", "") != "task.preferences":
                continue
            merged: dict[str, str] = {}
            event_data = getattr(event, "event_data", {}) or {}
            if not isinstance(event_data, dict):
                continue
            for key, value in event_data.items():
                if isinstance(value, str):
                    merged[key] = value
                elif isinstance(value, (int, float, bool)):
                    merged[key] = str(value)
            return merged
        return {}

    def _effective_workspace_policy(
        self,
        *,
        requested_profile: str,
        workspace_metadata: dict[str, object],
        task_preferences: dict[str, str],
    ) -> dict[str, object]:
        return self._policy_resolver.resolve_workspace_policy(
            requested_profile=requested_profile,
            workspace_metadata=workspace_metadata,
            task_preferences=task_preferences,
        )

    def _normalize_workspace_command(self, command: str) -> str:
        normalized = normalize_workspace_command(command)
        if (
            normalized.startswith("python ")
            and shutil.which("python") is None
            and self._binary_available("python3")
        ):
            return normalized.replace("python ", "python3 ", 1)
        return normalized

    def _resolve_workspace_path(self, root: Path, relative_path: str) -> Path:
        try:
            return resolve_workspace_path(root, relative_path)
        except ValueError as exc:
            raise PermissionError(str(exc)) from exc

    def _check_action_allowed(
        self,
        *,
        action_type: str,
        policy: dict[str, object],
        relative_path: str | None = None,
        command: str | None = None,
    ) -> dict[str, str]:
        return check_action_allowed(
            action_type=action_type,
            policy=policy,
            relative_path=relative_path,
            command=command,
        )

    def _verify_mechanical_gates(
        self,
        *,
        command_results: list[dict[str, object]],
        acceptance: dict[str, list[str]],
        runner: dict[str, object],
    ) -> dict[str, object]:
        return self._workspace_verifier.verify_mechanical_gates(
            command_results=command_results,
            acceptance=acceptance,
            runner=runner,
        )

    def _verify_workspace_execution(
        self,
        *,
        changed_files: list[str],
        command_results: list[dict[str, object]],
        root: Path,
        task_preferences: dict[str, str],
        contract: dict[str, object],
        runbook: dict[str, object],
        runner: dict[str, object] | None = None,
        policy: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return self._workspace_verifier.verify_workspace_execution(
            changed_files=changed_files,
            command_results=command_results,
            root=root,
            task_preferences=task_preferences,
            contract=contract,
            runbook=runbook,
            runner=runner,
            policy=policy,
        )

    def _run_all_runner_test_commands(
        self,
        *,
        root: Path,
        command_results: list[dict[str, object]],
        runner: dict[str, object],
        policy: dict[str, object],
    ) -> None:
        self._workspace_verifier.run_all_runner_test_commands(
            root=root,
            command_results=command_results,
            runner=runner,
            policy=policy,
        )

    def _validate_meaningful_candidate_change(
        self,
        *,
        task_id: UUID,
        task_preferences: dict[str, str],
        changed_files: list[str],
    ) -> dict[str, object]:
        parent_id = _parse_uuid(task_preferences.get("parent_task_id"))
        if parent_id is None:
            if changed_files:
                return {"status": "ok", "reason": ""}
            return {
                "status": "failed",
                "reason": "Meaningful change gate requires a concrete repo artifact.",
            }
        candidate = self._selected_candidate_for_parent(parent_id)
        if candidate is None:
            return {"status": "ok", "reason": ""}
        raw_targets = candidate.get("target_files")
        target_files = self._candidate_target_files(raw_targets)
        candidate_id = str(candidate.get("candidate_id") or "")
        if not changed_files:
            return {
                "status": "failed",
                "reason": "Selected candidate completed without a persisted repo diff.",
                "candidate_id": candidate_id,
            }
        if target_files and not any(
            changed == target or changed.endswith(target) or target.endswith(changed)
            for changed in changed_files
            for target in target_files
        ):
            return {
                "status": "failed",
                "reason": "Changed files do not match the selected candidate target files.",
                "candidate_id": candidate_id,
            }
        return {"status": "ok", "reason": "", "candidate_id": candidate_id}

    def _candidate_target_files(self, value: object) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return string_list(value)

    def _selected_candidate_for_parent(self, parent_id: UUID) -> dict[str, object] | None:
        return self._workspace_finalizer._selected_candidate_for_parent(parent_id)

    def _workspace_preflight(
        self,
        *,
        root: Path,
        provider_hint: str | None,
        required_env: list[str] | None = None,
        required_binaries: list[str] | None = None,
        required_files: list[str] | None = None,
        supported_os: list[str] | None = None,
        runner: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return self._workspace_preflight_service.verify(
            root=root,
            provider_hint=provider_hint,
            required_env=required_env,
            required_binaries=required_binaries,
            required_files=required_files,
            supported_os=supported_os,
            runner=runner,
        )

    def _binary_available(self, binary: str) -> bool:
        return self._resolve_binary(binary) is not None

    def _resolve_binary(self, binary: str) -> str | None:
        direct = shutil.which(binary)
        if direct:
            return direct
        aliases = {
            "python": ["python3", Path(sys.executable).name, sys.executable],
            "pip": ["pip3"],
        }
        for candidate in aliases.get(binary, []):
            resolved = shutil.which(candidate) if os.path.sep not in candidate else candidate
            if resolved and (os.path.sep not in candidate or Path(candidate).exists()):
                return resolved
        return None

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

    def _store_workspace_execution_report(
        self,
        *,
        task_id: UUID,
        status: str,
        summary_reason: str,
        provider: str,
        target_model: str,
        profile: str,
        changed_files: list[str],
        diff_refs: list[str],
        planned_actions: list[str],
        command_results: list[dict[str, object]],
        verification: dict[str, object],
    ) -> str:
        payload = {
            "status": status,
            "summary_reason": summary_reason,
            "provider": provider,
            "target_model": target_model,
            "profile": profile,
            "changed_files": changed_files,
            "diff_ref_ids": diff_refs,
            "planned_actions": planned_actions[:40],
            "commands": command_results,
            "verification": verification,
        }
        original = json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2)
        summary = shorten(
            f"{status} {summary_reason} files={len(changed_files)} commands={len(command_results)}",
            width=220,
            placeholder=" ...",
        )
        record = self._store.upsert_context_reference(
            ref_id=build_ref_id(task_id, "workspace_execution_report", original),
            task_id=task_id,
            content_type="workspace_execution_report",
            original_content=original,
            summary=summary,
            retrieval_hint=(
                "Workspace execution report with verification commands, diff refs, and "
                "outcome rationale."
            ),
        )
        ref_id = str(record["ref_id"])
        self._record_event(
            task_id=task_id,
            event_type="workspace.execution.report.stored",
            event_data={"ref_id": ref_id, "status": status, "profile": profile},
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


def _parse_uuid(raw: str | None) -> UUID | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
