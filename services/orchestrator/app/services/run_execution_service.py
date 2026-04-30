from __future__ import annotations

import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from textwrap import shorten
from typing import Iterator
from uuid import UUID

from packages.contracts.python.models import (
    AgentRunCreate,
    AgentRunUpdate,
    BatonPacketCreate,
    BatonPayload,
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


class RunExecutionService:
    WORKSPACE_POLICY_PROFILES: dict[str, dict[str, object]] = {
        "strict": {
            "allow_write": True,
            "allow_patch": True,
            "allow_read": True,
            "allow_search": True,
            "allow_commands": ("pytest", "python -m pytest"),
            "timeout_seconds": 90,
            "max_output_chars": 3000,
        },
        "balanced": {
            "allow_write": True,
            "allow_patch": True,
            "allow_read": True,
            "allow_search": True,
            "allow_commands": ("pytest", "python -m pytest", "npm test", "npm run test"),
            "timeout_seconds": 120,
            "max_output_chars": 6000,
        },
        "full-dev": {
            "allow_write": True,
            "allow_patch": True,
            "allow_read": True,
            "allow_search": True,
            "allow_commands": (
                "pytest",
                "python -m pytest",
                "npm test",
                "npm run test",
                "npm run lint",
                "npm run build",
                "uv run pytest",
                "go test",
                "cargo test",
            ),
            "timeout_seconds": 180,
            "max_output_chars": 10000,
        },
    }
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

    def execute_workspace_loop(
        self,
        payload: RunExecutionRequest,
        *,
        max_steps: int = 3,
        policy_profile: str = "balanced",
        dry_run: bool = False,
        require_approval: bool = False,
    ) -> dict[str, object]:
        task = self._store.get_task(payload.task_id)
        if task is None:
            raise LookupError("Task not found")
        if task.workspace_id is None:
            raise ValueError("Task does not have a workspace_id")
        workspace = self._store.get_workspace(task.workspace_id)
        if workspace is None:
            raise LookupError("Workspace not found")

        root = Path(workspace.root_path).resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Workspace path not found: {root}")
        profile = str(policy_profile or "balanced").strip().lower()
        if profile not in self.WORKSPACE_POLICY_PROFILES:
            profile = "balanced"
        policy = self.WORKSPACE_POLICY_PROFILES[profile]

        preflight = self._workspace_preflight(root=root, provider_hint=payload.provider)
        if preflight["status"] != "ok":
            self._record_event(
                task_id=payload.task_id,
                event_type="workspace.execution.preflight.failed",
                event_data={"reason": str(preflight.get("reason") or "unknown")},
            )
            raise ValueError(str(preflight.get("reason") or "Workspace preflight failed"))

        changed_files: list[str] = []
        diff_refs: list[str] = []
        command_results: list[dict[str, object]] = []
        read_refs: list[str] = []
        completed_work: list[str] = []
        next_action = "Run tests and verify calculator behavior."
        finish_summary = ""
        planned_actions: list[str] = []

        provider_name, provider = self._resolve_provider(payload.provider)
        max_steps = max(1, min(max_steps, 8))

        self._record_event(
            task_id=payload.task_id,
            event_type="workspace.execution.state.changed",
            event_data={"state": "planned", "profile": profile, "dry_run": dry_run},
        )
        plan_prompt = self._build_workspace_planner_prompt(
            base_prompt=payload.prompt,
            workspace_runbook=workspace.metadata.get("workspace_runbook", {}),
            profile=profile,
        )
        plan_result = provider.complete(
            model=payload.target_model,
            prompt=plan_prompt,
            system_prompt=payload.system_prompt,
            max_output_tokens=max(256, min(payload.max_output_tokens, 800)),
            temperature=0.1,
        )
        planned_actions = self._parse_plan_lines(plan_result.output_text)
        if require_approval:
            self._record_event(
                task_id=payload.task_id,
                event_type="workspace.execution.awaiting_approval",
                event_data={"planned_actions": len(planned_actions)},
            )
            raise ValueError("Workspace execution requires approval before applying actions.")

        if dry_run:
            self._record_event(
                task_id=payload.task_id,
                event_type="workspace.execution.dry_run",
                event_data={"planned_actions": len(planned_actions)},
            )
            return {
                "task_id": str(payload.task_id),
                "workspace_id": str(task.workspace_id),
                "provider": provider_name,
                "target_model": payload.target_model,
                "profile": profile,
                "state": "planned",
                "dry_run": True,
                "planned_actions": planned_actions[:40],
            }

        self._record_event(
            task_id=payload.task_id,
            event_type="workspace.execution.state.changed",
            event_data={"state": "executing", "profile": profile},
        )

        for step in range(1, max_steps + 1):
            file_snapshot = self._workspace_snapshot(root)
            worker_prompt = self._build_workspace_worker_prompt(
                base_prompt=payload.prompt,
                file_snapshot=file_snapshot,
                step=step,
                max_steps=max_steps,
            )
            result = provider.complete(
                model=payload.target_model,
                prompt=worker_prompt,
                system_prompt=payload.system_prompt,
                max_output_tokens=payload.max_output_tokens,
                temperature=payload.temperature,
            )
            actions = self._parse_worker_actions(result.output_text)
            if not actions:
                continue

            for action in actions:
                action_type = str(action.get("type", "")).strip().lower()
                if action_type == "write_file":
                    rel = str(action.get("path", "")).strip()
                    content = str(action.get("content", ""))
                    if not rel:
                        continue
                    ref_id = self._safe_write_with_diff(
                        task_id=payload.task_id,
                        root=root,
                        relative_path=rel,
                        content=content,
                    )
                    changed_files.append(rel)
                    diff_refs.append(ref_id)
                    completed_work.append(f"Updated {rel}")
                elif action_type == "patch_file":
                    rel = str(action.get("path", "")).strip()
                    before = str(action.get("before", ""))
                    after = str(action.get("after", ""))
                    if not rel or not before:
                        continue
                    ref_id = self._safe_patch_with_diff(
                        task_id=payload.task_id,
                        root=root,
                        relative_path=rel,
                        before_text=before,
                        after_text=after,
                    )
                    changed_files.append(rel)
                    diff_refs.append(ref_id)
                    completed_work.append(f"Patched {rel}")
                elif action_type == "read_file":
                    rel = str(action.get("path", "")).strip()
                    if not rel:
                        continue
                    read = self._safe_read_file(root=root, relative_path=rel)
                    if read:
                        read_refs.append(
                            self._store_text_reference(
                                task_id=payload.task_id,
                                content_type="workspace_read",
                                content_text=read,
                                retrieval_hint=f"Read snapshot for {rel}",
                            )
                        )
                elif action_type == "search_code":
                    pattern = str(action.get("pattern", "")).strip()
                    if not pattern:
                        continue
                    hits = self._safe_search_code(root=root, pattern=pattern)
                    if hits:
                        read_refs.append(
                            self._store_text_reference(
                                task_id=payload.task_id,
                                content_type="workspace_search",
                                content_text="\n".join(hits),
                                retrieval_hint=f"Search hits for pattern '{pattern}'",
                            )
                        )
                elif action_type == "run_command":
                    command = str(action.get("command", "")).strip()
                    if not command:
                        continue
                    command_results.append(
                        self._safe_run_workspace_command(root, command, policy=policy)
                    )
                elif action_type == "run_test":
                    command = str(action.get("command", "pytest -q")).strip()
                    command_results.append(
                        self._safe_run_workspace_command(root, command, policy=policy)
                    )
                elif action_type == "run_build":
                    command = str(action.get("command", "npm run build")).strip()
                    command_results.append(
                        self._safe_run_workspace_command(root, command, policy=policy)
                    )
                elif action_type == "complete_work":
                    text = str(action.get("text", "")).strip()
                    if text:
                        completed_work.append(text)
                elif action_type == "next_action":
                    text = str(action.get("text", "")).strip()
                    if text:
                        next_action = text
                elif action_type == "finish":
                    finish_summary = str(action.get("summary", "")).strip()
                    if not finish_summary:
                        finish_summary = "Workspace execution loop completed."
                    step = max_steps
                    break

        self._record_event(
            task_id=payload.task_id,
            event_type="workspace.execution.state.changed",
            event_data={"state": "verifying", "profile": profile},
        )
        verification = self._verify_workspace_execution(
            changed_files=changed_files,
            command_results=command_results,
        )
        if (
            verification["status"] != "ok"
            and provider_name == "local_echo"
            and str(verification.get("reason") or "")
            == "No changes or verification commands were produced."
        ):
            verification = {
                "status": "ok",
                "reason": "local_echo_noop_execution_accepted",
            }
            completed_work.append(
                "No-op local echo execution accepted for autonomy dry progression."
            )
        if verification["status"] != "ok":
            self._record_event(
                task_id=payload.task_id,
                event_type="workspace.execution.verification.failed",
                event_data={"reason": str(verification.get("reason") or "verification failed")},
            )
            raise RuntimeError(str(verification.get("reason") or "Workspace verification failed"))

        self._record_event(
            task_id=payload.task_id,
            event_type="workspace.execution.completed",
            event_data={
                "provider": provider_name,
                "model": payload.target_model,
                "changed_files": len(changed_files),
                "diff_refs": len(diff_refs),
                "read_refs": len([item for item in read_refs if item]),
                "profile": profile,
            },
        )

        baton = self._store.save_baton_packet(
            BatonPacketCreate(
                task_id=payload.task_id,
                from_agent=payload.target_agent,
                to_agent="analyst",
                summary=finish_summary or "Workspace implementation batch completed",
                payload=BatonPayload(
                    objective=payload.prompt,
                    completed_work=completed_work[:20],
                    constraints=[],
                    open_questions=[],
                    next_best_action=next_action,
                    relevant_artifacts=changed_files[:20],
                ),
            )
        )

        events = self._store.list_project_events(task_id=payload.task_id, limit=200)
        digest = self._digest_service.generate_digest(
            task_id=payload.task_id,
            events=events,
            latest_baton=baton,
        )
        self._record_event(
            task_id=payload.task_id,
            event_type="analyst.digest.generated",
            event_data={
                "headline": digest.headline[:250],
                "risk_level": digest.risk_level,
                "total_events": digest.total_events,
            },
        )

        return {
            "task_id": str(payload.task_id),
            "workspace_id": str(task.workspace_id),
            "provider": provider_name,
            "target_model": payload.target_model,
            "profile": profile,
            "changed_files": changed_files,
            "diff_ref_ids": diff_refs,
            "read_ref_ids": [item for item in read_refs if item],
            "planned_actions": planned_actions[:40],
            "commands": command_results,
            "baton_id": str(baton.id),
            "verification": verification,
            "digest": digest.model_dump(mode="json"),
        }

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

    def _build_workspace_worker_prompt(
        self,
        *,
        base_prompt: str,
        file_snapshot: str,
        step: int,
        max_steps: int,
    ) -> str:
        return (
            "You are Syncore workspace coder.\n"
            f"Step {step}/{max_steps}.\n"
            "Return ONLY JSON with schema: "
            "{\"actions\":[{\"type\":\"read_file|search_code|write_file|patch_file|run_command|run_test|run_build|complete_work|next_action|finish\","
            "\"path\":\"...\",\"content\":\"...\",\"before\":\"...\",\"after\":\"...\",\"pattern\":\"...\",\"command\":\"...\",\"text\":\"...\",\"summary\":\"...\"}]}\n"
            "Prefer write_file with full file content for deterministic updates.\n"
            "Use commands only when needed for verification.\n\n"
            "Task:\n"
            f"{base_prompt}\n\n"
            "Workspace snapshot:\n"
            f"{file_snapshot}"
        )

    def _build_workspace_planner_prompt(
        self,
        *,
        base_prompt: str,
        workspace_runbook: object,
        profile: str,
    ) -> str:
        return (
            "You are planning safe workspace actions for an autonomous coding loop.\n"
            f"Policy profile: {profile}.\n"
            "Return concise numbered steps, no markdown table.\n"
            "Prefer test/build verification and minimal file mutations.\n\n"
            f"Task:\n{base_prompt}\n\n"
            f"Workspace runbook metadata:\n{workspace_runbook}\n"
        )

    def _parse_plan_lines(self, output_text: str) -> list[str]:
        lines = [line.strip(" -\t") for line in output_text.splitlines() if line.strip()]
        return [line[:240] for line in lines[:60]]

    def _workspace_snapshot(self, root: Path) -> str:
        entries: list[str] = []
        for path in root.rglob("*"):
            if len(entries) >= 200:
                break
            if path.is_dir():
                continue
            rel = path.relative_to(root).as_posix()
            blocked_parts = {".git", "node_modules", ".venv", "__pycache__", ".next"}
            rel_parts = path.relative_to(root).parts
            if any(part in blocked_parts for part in rel_parts):
                continue
            entries.append(rel)
        if not entries:
            return "(empty workspace)"
        return "\n".join(f"- {item}" for item in entries)

    def _parse_worker_actions(self, output_text: str) -> list[dict[str, object]]:
        candidate = output_text.strip()
        fenced = re.search(r"```json\s*(\{.*?\})\s*```", candidate, re.DOTALL)
        if fenced:
            candidate = fenced.group(1)
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            return []
        actions = payload.get("actions", [])
        if not isinstance(actions, list):
            return []
        parsed: list[dict[str, object]] = []
        for action in actions:
            if isinstance(action, dict):
                parsed.append(action)
        return parsed

    def _resolve_workspace_path(self, root: Path, relative_path: str) -> Path:
        target = (root / relative_path).resolve()
        if root != target and root not in target.parents:
            raise PermissionError(f"Path traversal blocked: {relative_path}")
        name = target.name
        blocked = (
            name == ".env"
            or name.startswith(".env.")
            or name in {"id_rsa", "id_dsa"}
            or name.endswith((".pem", ".key"))
            or name.startswith(("secrets.", "credentials."))
        )
        if blocked:
            raise PermissionError(f"Blocked file path: {relative_path}")
        return target

    def _safe_read_file(self, *, root: Path, relative_path: str) -> str:
        target = self._resolve_workspace_path(root, relative_path)
        if not target.exists() or not target.is_file():
            return ""
        if target.stat().st_size > 1_000_000:
            return ""
        return target.read_text(encoding="utf-8", errors="replace")

    def _safe_search_code(self, *, root: Path, pattern: str, limit: int = 80) -> list[str]:
        safe_pattern = pattern[:120]
        hits: list[str] = []
        for path in root.rglob("*"):
            if len(hits) >= limit:
                break
            if path.is_dir():
                continue
            rel = path.relative_to(root)
            if any(
                part in {".git", "node_modules", ".venv", "__pycache__", ".next"}
                for part in rel.parts
            ):
                continue
            if path.stat().st_size > 1_000_000:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                if safe_pattern in line:
                    hits.append(f"{rel.as_posix()}:{idx}:{line[:200]}")
                    if len(hits) >= limit:
                        break
        return hits

    def _safe_write_with_diff(
        self,
        *,
        task_id: UUID,
        root: Path,
        relative_path: str,
        content: str,
    ) -> str:
        target = self._resolve_workspace_path(root, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        before = ""
        if target.exists():
            before = target.read_text(encoding="utf-8", errors="replace")
        target.write_text(content, encoding="utf-8")
        after = target.read_text(encoding="utf-8", errors="replace")
        diff = "".join(
            unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
            )
        )
        if not diff.strip():
            diff = f"(no textual diff) {relative_path}"
        ref = self._store.upsert_context_reference(
            ref_id=build_ref_id(task_id, "workspace_diff", diff),
            task_id=task_id,
            content_type="workspace_diff",
            original_content=diff,
            summary=shorten(" ".join(diff.split()), width=220, placeholder=" ..."),
            retrieval_hint=f"Diff for workspace file {relative_path}",
        )
        ref_id = str(ref["ref_id"])
        self._record_event(
            task_id=task_id,
            event_type="artifact.diff.stored",
            event_data={"path": relative_path, "ref_id": ref_id},
        )
        return ref_id

    def _safe_patch_with_diff(
        self,
        *,
        task_id: UUID,
        root: Path,
        relative_path: str,
        before_text: str,
        after_text: str,
    ) -> str:
        target = self._resolve_workspace_path(root, relative_path)
        if not target.exists():
            raise FileNotFoundError(f"Patch target does not exist: {relative_path}")
        existing = target.read_text(encoding="utf-8", errors="replace")
        if before_text not in existing:
            raise ValueError(f"Patch before-text not found in {relative_path}")
        updated = existing.replace(before_text, after_text, 1)
        return self._safe_write_with_diff(
            task_id=task_id,
            root=root,
            relative_path=relative_path,
            content=updated,
        )

    def _safe_run_workspace_command(
        self,
        root: Path,
        command: str,
        *,
        policy: dict[str, object],
    ) -> dict[str, object]:
        allowed_prefixes = tuple(policy.get("allow_commands", ()))
        if not any(command.startswith(str(prefix)) for prefix in allowed_prefixes):
            return {"command": command, "status": "blocked", "output": "Command not allowed"}
        timeout = int(policy.get("timeout_seconds", 120))
        max_output = int(policy.get("max_output_chars", 4000))
        completed = subprocess.run(
            command,
            shell=True,
            cwd=root,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        output = (completed.stdout or "") + (("\n" + completed.stderr) if completed.stderr else "")
        return {
            "command": command,
            "status": "ok" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "output": output[:max_output],
        }

    def _workspace_preflight(self, *, root: Path, provider_hint: str | None) -> dict[str, str]:
        if not root.exists() or not root.is_dir():
            return {"status": "failed", "reason": "workspace root missing"}
        if not os.access(root, os.R_OK | os.W_OK):
            return {"status": "failed", "reason": "workspace root not writable/readable"}
        provider_name = (provider_hint or self._default_provider or "local_echo").strip().lower()
        if provider_name and provider_name not in self._providers:
            return {"status": "failed", "reason": f"provider '{provider_name}' is not configured"}
        return {"status": "ok", "reason": ""}

    def _verify_workspace_execution(
        self,
        *,
        changed_files: list[str],
        command_results: list[dict[str, object]],
    ) -> dict[str, object]:
        failed_cmds = [
            item for item in command_results if str(item.get("status")) in {"failed", "blocked"}
        ]
        if failed_cmds:
            return {
                "status": "failed",
                "reason": "One or more workspace commands failed/blocked.",
                "failed_commands": [str(item.get("command")) for item in failed_cmds[:10]],
            }
        if not changed_files and not command_results:
            return {
                "status": "failed",
                "reason": "No changes or verification commands were produced.",
            }
        return {"status": "ok", "reason": ""}

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
