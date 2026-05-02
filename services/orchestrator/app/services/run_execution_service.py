from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
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
    WorkspaceUpdate,
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
from app.services.policy_packs import get_policy_pack
from app.services.workspace_readiness import compute_workspace_readiness


class RunExecutionService:
    WORKSPACE_POLICY_PROFILES: dict[str, dict[str, object]] = {
        "strict": {
            "allow_write": True,
            "allow_patch": True,
            "allow_read": True,
            "allow_search": True,
            "allow_delete": False,
            "allow_move": False,
            "allow_commands": ("pytest", "python -m pytest"),
            "allowed_actions": (
                "read_file",
                "search_code",
                "write_file",
                "patch_file",
                "run_command",
                "run_test",
                "complete_work",
                "next_action",
                "finish",
            ),
            "timeout_seconds": 90,
            "max_output_chars": 3000,
        },
        "balanced": {
            "allow_write": True,
            "allow_patch": True,
            "allow_read": True,
            "allow_search": True,
            "allow_delete": False,
            "allow_move": True,
            "allow_commands": ("pytest", "python -m pytest", "npm test", "npm run test"),
            "allowed_actions": (
                "read_file",
                "search_code",
                "write_file",
                "patch_file",
                "move_file",
                "run_command",
                "run_test",
                "run_build",
                "run_lint",
                "run_format",
                "complete_work",
                "next_action",
                "finish",
            ),
            "timeout_seconds": 120,
            "max_output_chars": 6000,
        },
        "full-dev": {
            "allow_write": True,
            "allow_patch": True,
            "allow_read": True,
            "allow_search": True,
            "allow_delete": True,
            "allow_move": True,
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
            "allowed_actions": (
                "read_file",
                "search_code",
                "write_file",
                "patch_file",
                "move_file",
                "delete_file",
                "run_command",
                "run_test",
                "run_build",
                "run_lint",
                "run_format",
                "run_targeted_test",
                "install_deps",
                "complete_work",
                "next_action",
                "finish",
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
        task_preferences = self._load_task_preferences(payload.task_id)
        contract = dict(workspace.metadata.get("syncore_contract") or {})
        runbook = dict(workspace.metadata.get("workspace_runbook") or {})
        runner = dict(workspace.metadata.get("workspace_runner") or runbook.get("runner") or {})
        policy = self._effective_workspace_policy(
            requested_profile=profile,
            workspace_metadata=workspace.metadata,
            task_preferences=task_preferences,
        )
        profile = str(policy.get("profile") or "balanced")

        preflight = self._workspace_preflight(
            root=root,
            provider_hint=payload.provider,
            required_env=self._string_list(runbook.get("required_env")),
            required_binaries=self._string_list(runbook.get("required_binaries"))
            or self._string_list(runner.get("required_binaries")),
            required_files=self._string_list(runbook.get("required_files")),
            supported_os=self._string_list(runner.get("supported_os")),
            runner=runner,
        )
        if preflight["status"] != "ok":
            repaired = self._attempt_workspace_auto_repair(
                task_id=payload.task_id,
                root=root,
                runner=runner,
                runbook=runbook,
                policy=policy,
            )
            if repaired:
                preflight = self._workspace_preflight(
                    root=root,
                    provider_hint=payload.provider,
                    required_env=self._string_list(runbook.get("required_env")),
                    required_binaries=self._string_list(runbook.get("required_binaries"))
                    or self._string_list(runner.get("required_binaries")),
                    required_files=self._string_list(runbook.get("required_files")),
                    supported_os=self._string_list(runner.get("supported_os")),
                    runner=runner,
                )
        if preflight["status"] != "ok":
            classification = self._classify_workspace_issue(
                stage="preflight",
                reason=str(preflight.get("reason") or "unknown"),
            )
            self._update_workspace_learning_failure(
                workspace_id=task.workspace_id,
                reason=str(preflight.get("reason") or "unknown"),
                category=classification["category"],
                strategy=classification["strategy"],
            )
            self._record_event(
                task_id=payload.task_id,
                event_type="workspace.execution.preflight.failed",
                event_data={
                    "reason": str(preflight.get("reason") or "unknown"),
                    "failure_category": classification["category"],
                    "recommended_strategy": classification["strategy"],
                    "provider": str(payload.provider or self._default_provider),
                    "suggestions": shorten(
                        " | ".join(str(item) for item in preflight.get("suggestions", [])),
                        width=250,
                        placeholder=" ...",
                    ),
                },
            )
            raise ValueError(str(preflight.get("reason") or "Workspace preflight failed"))

        changed_files: list[str] = []
        diff_refs: list[str] = []
        command_results: list[dict[str, object]] = []
        read_refs: list[str] = []
        completed_work: list[str] = []
        next_action = "Run the repo's verification checks for the changed files."
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
            workspace_runbook=runbook,
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
                contract=contract,
                runner=runner,
                policy=policy,
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
                action_gate = self._check_action_allowed(
                    action_type=action_type,
                    policy=policy,
                    relative_path=str(action.get("path", "")).strip() or None,
                    command=str(action.get("command", "")).strip() or None,
                )
                if action_gate["status"] != "ok":
                    command_results.append(
                        {
                            "command": str(action.get("command") or action_type),
                            "status": "blocked",
                            "output": str(action_gate.get("reason") or "Action blocked"),
                        }
                    )
                    continue
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
                elif action_type == "create_file":
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
                    completed_work.append(f"Created {rel}")
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
                elif action_type == "delete_file":
                    rel = str(action.get("path", "")).strip()
                    if not rel:
                        continue
                    ref_id = self._safe_delete_with_diff(
                        task_id=payload.task_id,
                        root=root,
                        relative_path=rel,
                    )
                    changed_files.append(rel)
                    diff_refs.append(ref_id)
                    completed_work.append(f"Deleted {rel}")
                elif action_type == "move_file":
                    rel = str(action.get("path", "")).strip()
                    destination = str(action.get("destination", "")).strip()
                    if not rel or not destination:
                        continue
                    ref_id = self._safe_move_with_diff(
                        task_id=payload.task_id,
                        root=root,
                        source_path=rel,
                        destination_path=destination,
                    )
                    changed_files.extend([rel, destination])
                    diff_refs.append(ref_id)
                    completed_work.append(f"Moved {rel} to {destination}")
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
                    command = str(
                        action.get("command")
                        or self._runner_default_command(runner, "test", "pytest -q")
                    ).strip()
                    command_results.append(
                        self._safe_run_workspace_command(root, command, policy=policy)
                    )
                elif action_type == "run_build":
                    command = str(
                        action.get("command")
                        or self._runner_default_command(runner, "build", "npm run build")
                    ).strip()
                    command_results.append(
                        self._safe_run_workspace_command(root, command, policy=policy)
                    )
                elif action_type == "run_lint":
                    command = str(
                        action.get("command")
                        or self._runner_default_command(runner, "lint", "")
                    ).strip()
                    if not command:
                        continue
                    command_results.append(
                        self._safe_run_workspace_command(root, command, policy=policy)
                    )
                elif action_type == "run_format":
                    command = str(
                        action.get("command")
                        or self._runner_default_command(runner, "format", "")
                    ).strip()
                    if not command:
                        continue
                    command_results.append(
                        self._safe_run_workspace_command(root, command, policy=policy)
                    )
                elif action_type == "run_targeted_test":
                    command = str(
                        action.get("command")
                        or self._runner_default_command(runner, "test", "pytest -q")
                    ).strip()
                    command_results.append(
                        self._safe_run_workspace_command(root, command, policy=policy)
                    )
                elif action_type == "install_deps":
                    command = str(
                        action.get("command")
                        or self._runner_default_command(runner, "setup", "")
                    ).strip()
                    if not command:
                        continue
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

            if changed_files or command_results:
                self._ensure_required_verification_commands_run(
                    root=root,
                    command_results=command_results,
                    acceptance=self._merged_acceptance_criteria(
                        task_preferences=task_preferences,
                        contract=contract,
                        runbook=runbook,
                    ),
                    runner=runner,
                    policy=policy,
                )
                step_verification = self._verify_workspace_execution(
                    changed_files=changed_files,
                    command_results=list(command_results),
                    root=root,
                    task_preferences=task_preferences,
                    contract=contract,
                    runbook=runbook,
                    runner=runner,
                    policy=policy,
                )
                if step_verification["status"] == "ok":
                    if not finish_summary:
                        finish_summary = (
                            "Workspace execution loop completed after verification passed."
                        )
                    break

        self._record_event(
            task_id=payload.task_id,
            event_type="workspace.execution.state.changed",
            event_data={"state": "verifying", "profile": profile},
        )
        self._ensure_required_verification_commands_run(
            root=root,
            command_results=command_results,
            acceptance=self._merged_acceptance_criteria(
                task_preferences=task_preferences,
                contract=contract,
                runbook=runbook,
            ),
            runner=runner,
            policy=policy,
        )
        verification = self._verify_workspace_execution(
            changed_files=changed_files,
            command_results=command_results,
            root=root,
            task_preferences=task_preferences,
            contract=contract,
            runbook=runbook,
            runner=runner,
            policy=policy,
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
            classification = self._classify_workspace_issue(
                stage="verification",
                reason=str(verification.get("reason") or "verification failed"),
            )
            self._update_workspace_learning_failure(
                workspace_id=task.workspace_id,
                reason=str(verification.get("reason") or "verification failed"),
                category=classification["category"],
                strategy=classification["strategy"],
            )
            self._record_event(
                task_id=payload.task_id,
                event_type="workspace.execution.verification.failed",
                event_data={
                    "reason": str(verification.get("reason") or "verification failed"),
                    "failure_category": classification["category"],
                    "recommended_strategy": classification["strategy"],
                    "provider": provider_name,
                },
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
        self._update_workspace_learning(
            workspace_id=task.workspace_id,
            provider=provider_name,
            model=payload.target_model,
            profile=profile,
            policy=policy,
            runner=runner,
            command_results=command_results,
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
        contract: dict[str, object],
        runner: dict[str, object],
        policy: dict[str, object],
    ) -> str:
        return (
            "You are Syncore workspace coder.\n"
            f"Step {step}/{max_steps}.\n"
            "Return ONLY JSON with schema: "
            "{\"actions\":[{\"type\":\"read_file|search_code|write_file|create_file|patch_file|move_file|delete_file|run_command|run_test|run_build|run_lint|run_format|run_targeted_test|install_deps|complete_work|next_action|finish\","
            "\"path\":\"...\",\"destination\":\"...\",\"content\":\"...\",\"before\":\"...\",\"after\":\"...\",\"pattern\":\"...\",\"command\":\"...\",\"text\":\"...\",\"summary\":\"...\"}]}\n"
            "Prefer write_file with full file content for deterministic updates.\n"
            "Use commands only when needed for verification.\n\n"
            "Task:\n"
            f"{base_prompt}\n\n"
            "Workspace contract:\n"
            f"{contract}\n\n"
            "Selected runner:\n"
            f"{runner}\n\n"
            "Execution policy:\n"
            f"{policy}\n\n"
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

    def _safe_delete_with_diff(
        self,
        *,
        task_id: UUID,
        root: Path,
        relative_path: str,
    ) -> str:
        target = self._resolve_workspace_path(root, relative_path)
        if not target.exists():
            raise FileNotFoundError(f"Delete target does not exist: {relative_path}")
        before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        if target.is_file():
            target.unlink()
        diff = "".join(
            unified_diff(
                before.splitlines(keepends=True),
                [],
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
            )
        )
        ref = self._store.upsert_context_reference(
            ref_id=build_ref_id(task_id, "workspace_diff", diff or relative_path),
            task_id=task_id,
            content_type="workspace_diff",
            original_content=diff or f"Deleted {relative_path}",
            summary=shorten(
                " ".join((diff or f'Deleted {relative_path}').split()),
                width=220,
                placeholder=" ...",
            ),
            retrieval_hint=f"Diff for workspace file {relative_path}",
        )
        ref_id = str(ref["ref_id"])
        self._record_event(
            task_id=task_id,
            event_type="artifact.diff.stored",
            event_data={"path": relative_path, "ref_id": ref_id},
        )
        return ref_id

    def _safe_move_with_diff(
        self,
        *,
        task_id: UUID,
        root: Path,
        source_path: str,
        destination_path: str,
    ) -> str:
        source = self._resolve_workspace_path(root, source_path)
        destination = self._resolve_workspace_path(root, destination_path)
        if not source.exists():
            raise FileNotFoundError(f"Move source does not exist: {source_path}")
        before = source.read_text(encoding="utf-8", errors="replace") if source.is_file() else ""
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        diff = (
            f"Moved {source_path} -> {destination_path}\n"
            f"Original content preview:\n{before[:1000]}"
        )
        ref = self._store.upsert_context_reference(
            ref_id=build_ref_id(task_id, "workspace_diff", diff),
            task_id=task_id,
            content_type="workspace_diff",
            original_content=diff,
            summary=shorten(" ".join(diff.split()), width=220, placeholder=" ..."),
            retrieval_hint=f"Move record for {source_path} to {destination_path}",
        )
        ref_id = str(ref["ref_id"])
        self._record_event(
            task_id=task_id,
            event_type="artifact.diff.stored",
            event_data={"path": destination_path, "ref_id": ref_id},
        )
        return ref_id

    def _runner_default_command(
        self,
        runner: dict[str, object],
        section: str,
        fallback: str,
    ) -> str:
        commands = dict(runner.get("commands") or {})
        values = self._string_list(commands.get(section))
        return values[0] if values else fallback

    def _check_action_allowed(
        self,
        *,
        action_type: str,
        policy: dict[str, object],
        relative_path: str | None = None,
        command: str | None = None,
    ) -> dict[str, str]:
        allowed_actions = {
            str(item).strip().lower() for item in tuple(policy.get("allowed_actions") or ())
        }
        denied_actions = {
            str(item).strip().lower() for item in tuple(policy.get("denied_actions") or ())
        }
        if action_type in denied_actions:
            return {"status": "blocked", "reason": f"Action '{action_type}' denied by policy"}
        if allowed_actions and action_type not in allowed_actions:
            return {"status": "blocked", "reason": f"Action '{action_type}' is not allowed"}
        forbidden_paths = self._string_list(policy.get("forbidden_paths"))
        if relative_path and forbidden_paths and any(
            relative_path == path or relative_path.startswith(path.rstrip("/") + "/")
            for path in forbidden_paths
        ):
            return {
                "status": "blocked",
                "reason": f"Path '{relative_path}' is forbidden by workspace policy",
            }
        allowed_paths = self._string_list(policy.get("allowed_paths"))
        if relative_path and allowed_paths and not any(
            relative_path == path or relative_path.startswith(path.rstrip("/") + "/")
            for path in allowed_paths
        ):
            return {
                "status": "blocked",
                "reason": f"Path '{relative_path}' is outside allowed workspace roots",
            }
        approval_paths = self._string_list(policy.get("approval_required_paths"))
        if relative_path and approval_paths and any(
            relative_path == path or relative_path.startswith(path.rstrip("/") + "/")
            for path in approval_paths
        ):
            return {
                "status": "blocked",
                "reason": f"Path '{relative_path}' requires explicit approval",
            }
        if command:
            allowed = self._command_allowed(command, policy)
            if not allowed:
                return {"status": "blocked", "reason": f"Command '{command}' is not allowed"}
        return {"status": "ok", "reason": ""}

    def _command_allowed(self, command: str, policy: dict[str, object]) -> bool:
        blocked_commands = tuple(policy.get("blocked_commands", ()))
        if any(command.startswith(str(prefix)) for prefix in blocked_commands):
            return False
        allowed_prefixes = tuple(policy.get("allow_commands", ()))
        if any(command.startswith(str(prefix)) for prefix in allowed_prefixes):
            return True
        patterns = tuple(policy.get("allowed_command_patterns", ()))
        return any(re.fullmatch(str(pattern), command) for pattern in patterns)

    def _preflight_failure(
        self,
        *,
        reason: str,
        suggestions: list[str],
        missing_env: list[str] | None = None,
        missing_binaries: list[str] | None = None,
        missing_files: list[str] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "failed",
            "reason": reason,
            "suggestions": suggestions[:8],
        }
        if missing_env:
            payload["missing_env"] = missing_env[:20]
        if missing_binaries:
            payload["missing_binaries"] = missing_binaries[:20]
        if missing_files:
            payload["missing_files"] = missing_files[:20]
        return payload

    def _binary_install_suggestions(self, binary: str) -> list[str]:
        common = {
            "python": ["Install Python 3.10+ and ensure `python` or `python3` is on PATH."],
            "node": ["Install Node.js 20+ and ensure `node` is on PATH."],
            "npm": ["Install Node.js/npm and verify `npm --version` succeeds."],
            "pnpm": ["Install pnpm globally, for example `npm install -g pnpm`."],
            "uv": ["Install uv, for example `curl -LsSf https://astral.sh/uv/install.sh | sh`."],
            "cargo": ["Install Rust toolchain via rustup so `cargo` is available on PATH."],
            "go": ["Install Go and verify `go version` succeeds."],
            "gradle": ["Install Gradle or use the project wrapper if available."],
            "java": ["Install a JDK and verify `java -version` succeeds."],
        }
        return common.get(
            binary,
            [f"Install '{binary}' and ensure it is available on PATH before retrying."],
        )

    def _attempt_workspace_auto_repair(
        self,
        *,
        task_id: UUID,
        root: Path,
        runner: dict[str, object],
        runbook: dict[str, object],
        policy: dict[str, object],
    ) -> bool:
        if self._needs_dependency_bootstrap(root=root, runner=runner, runbook=runbook) is False:
            return False
        setup_command = self._runner_default_command(runner, "setup", "")
        if not setup_command:
            return False
        result = self._safe_run_workspace_command(root, setup_command, policy=policy)
        self._record_event(
            task_id=task_id,
            event_type="workspace.auto_repair.attempted",
            event_data={
                "command": setup_command[:200],
                "status": str(result.get("status") or ""),
            },
        )
        return str(result.get("status")) == "ok"

    def _needs_dependency_bootstrap(
        self,
        *,
        root: Path,
        runner: dict[str, object],
        runbook: dict[str, object],
    ) -> bool:
        package_manager = str(runbook.get("package_manager") or runner.get("package_manager") or "")
        runner_name = str(runner.get("name") or "")
        if (
            package_manager in {"npm", "pnpm", "yarn"}
            or runner_name.startswith("node-")
            or runner_name == "monorepo-pnpm"
        ):
            return (root / "package.json").exists() and not (root / "node_modules").exists()
        if runner_name.startswith("python-"):
            if (root / "pyproject.toml").exists() and not (root / ".venv").exists():
                return True
            if (root / "requirements.txt").exists():
                return True
        if runner_name == "rust-cli":
            return (root / "Cargo.toml").exists()
        if runner_name == "go-service":
            return (root / "go.mod").exists()
        if runner_name == "java-gradle":
            return (root / "build.gradle").exists() or (root / "build.gradle.kts").exists()
        return False

    def _safe_run_workspace_command(
        self,
        root: Path,
        command: str,
        *,
        policy: dict[str, object],
    ) -> dict[str, object]:
        if not self._command_allowed(command, policy):
            return {"command": command, "status": "blocked", "output": "Command not allowed"}
        command = self._normalize_workspace_command(command)
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

    def _verify_secret_safety(
        self,
        *,
        root: Path,
        changed_files: list[str],
    ) -> dict[str, object]:
        secret_markers = ("api_key", "secret_key", "sk-proj-", "BEGIN PRIVATE KEY")
        for rel in changed_files[:50]:
            target = root / rel
            if not target.exists() or not target.is_file():
                continue
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lowered = content.lower()
            if any(marker.lower() in lowered for marker in secret_markers):
                return {
                    "status": "failed",
                    "reason": "Potential secret material detected in changed files.",
                    "path": rel,
                }
        return {"status": "ok", "reason": ""}

    def _classify_workspace_issue(self, *, stage: str, reason: str) -> dict[str, str]:
        lowered = reason.lower()
        if "env var" in lowered or "binary" in lowered or "os" in lowered:
            return {"category": "environment_failure", "strategy": "repair_environment"}
        if "provider" in lowered:
            return {"category": "provider_failure", "strategy": "switch_model_or_provider"}
        if "command" in lowered and "allowed" in lowered:
            return {"category": "policy_block", "strategy": "relax_policy_or_request_approval"}
        if "forbidden" in lowered or "approval" in lowered:
            return {"category": "risk_guardrail", "strategy": "reduce_scope_or_request_approval"}
        if "artifact" in lowered or "behavior" in lowered:
            return {"category": "acceptance_failure", "strategy": "tighten_implementation_scope"}
        if "verification" in lowered or "required" in lowered:
            return {"category": "verification_failure", "strategy": "raise_verification"}
        return {"category": f"{stage}_failure", "strategy": "replan"}

    def _update_workspace_learning(
        self,
        *,
        workspace_id: UUID | None,
        provider: str,
        model: str,
        profile: str,
        policy: dict[str, object],
        runner: dict[str, object],
        command_results: list[dict[str, object]],
    ) -> None:
        if workspace_id is None:
            return
        workspace = self._store.get_workspace(workspace_id)
        if workspace is None:
            return
        metadata = dict(workspace.metadata)
        learning = dict(metadata.get("learning") or {})
        commands_ok = [
            str(item.get("command"))
            for item in command_results
            if str(item.get("status")) == "ok" and item.get("command")
        ]
        learning["last_successful_provider"] = provider
        learning["last_successful_model"] = model
        learning["last_successful_profile"] = profile
        learning["last_successful_runner"] = runner.get("name")
        learning["last_successful_policy_pack"] = policy.get("policy_pack")
        learning["successful_commands"] = commands_ok[:20]
        learning["success_count"] = int(learning.get("success_count") or 0) + 1
        learning["updated_at"] = datetime.now(timezone.utc).isoformat()
        metadata["learning"] = learning
        metadata["workspace_readiness"] = compute_workspace_readiness(
            scan=dict(metadata.get("scan") or {}),
            contract=dict(metadata.get("syncore_contract") or {}),
            runner=dict(metadata.get("workspace_runner") or runner),
            learning=learning,
        )
        self._store.update_workspace(
            workspace_id,
            WorkspaceUpdate(metadata=metadata),
        )

    def _update_workspace_learning_failure(
        self,
        *,
        workspace_id: UUID | None,
        reason: str,
        category: str,
        strategy: str,
    ) -> None:
        if workspace_id is None:
            return
        workspace = self._store.get_workspace(workspace_id)
        if workspace is None:
            return
        metadata = dict(workspace.metadata)
        learning = dict(metadata.get("learning") or {})
        failures = list(learning.get("recent_failures") or [])
        failures.append(
            {
                "category": category,
                "strategy": strategy,
                "reason": reason[:200],
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        learning["recent_failures"] = failures[-10:]
        learning["failure_count"] = int(learning.get("failure_count") or 0) + 1
        learning["updated_at"] = datetime.now(timezone.utc).isoformat()
        metadata["learning"] = learning
        metadata["workspace_readiness"] = compute_workspace_readiness(
            scan=dict(metadata.get("scan") or {}),
            contract=dict(metadata.get("syncore_contract") or {}),
            runner=dict(metadata.get("workspace_runner") or {}),
            learning=learning,
        )
        self._store.update_workspace(
            workspace_id,
            WorkspaceUpdate(metadata=metadata),
        )

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
        if not root.exists() or not root.is_dir():
            return self._preflight_failure(
                reason="workspace root missing",
                suggestions=["Ensure the workspace path exists before running Syncore."],
            )
        if not os.access(root, os.R_OK | os.W_OK):
            return self._preflight_failure(
                reason="workspace root not writable/readable",
                suggestions=[
                    "Check filesystem permissions for the workspace directory.",
                    "Ensure the current user can read and write under the workspace root.",
                ],
            )
        provider_name = (provider_hint or self._default_provider or "local_echo").strip().lower()
        if provider_name and provider_name not in self._providers:
            return self._preflight_failure(
                reason=f"provider '{provider_name}' is not configured",
                suggestions=[
                    f"Configure credentials for provider '{provider_name}' in .env.",
                    "Use a configured provider or fall back to local_echo for dry runs.",
                ],
            )
        for env_name in required_env or []:
            if env_name and not os.getenv(env_name):
                return self._preflight_failure(
                    reason=f"required env var '{env_name}' is missing",
                    suggestions=[
                        f"Export {env_name}=... in the shell before starting Syncore.",
                        f"Add {env_name} to the workspace .env contract documentation.",
                    ],
                    missing_env=[env_name],
                )
        current_os = platform.system().lower()
        supported = [item.lower() for item in (supported_os or []) if item]
        if supported and current_os not in supported:
            return self._preflight_failure(
                reason=f"workspace contract does not support current os '{current_os}'",
                suggestions=[
                    "Run the workspace on a supported OS or update syncore.yaml environment.os.",
                ],
            )
        for binary in required_binaries or []:
            if binary and not self._binary_available(binary):
                return self._preflight_failure(
                    reason=f"required binary '{binary}' is missing from PATH",
                    suggestions=self._binary_install_suggestions(binary),
                    missing_binaries=[binary],
                )
        if runner:
            runner_expected = self._string_list(runner.get("expected_files"))
            if runner_expected and not any((root / rel).exists() for rel in runner_expected):
                return self._preflight_failure(
                    reason="workspace does not match the expected runner file layout",
                    suggestions=[
                        "Rescan the workspace and confirm the selected policy pack/runner.",
                        "Add an explicit runner to syncore.yaml if auto-detection is wrong.",
                    ],
                    missing_files=runner_expected,
                )
            commands = dict(runner.get("commands") or {})
            setup_commands = self._string_list(commands.get("setup"))
            for command in setup_commands[:1]:
                binary = command.split()[0] if command.split() else ""
                if binary and not self._binary_available(binary):
                    return self._preflight_failure(
                        reason=f"runner setup binary '{binary}' is missing from PATH",
                        suggestions=self._binary_install_suggestions(binary),
                        missing_binaries=[binary],
                    )
        for rel in required_files or []:
            if rel and not (root / rel).exists():
                return self._preflight_failure(
                    reason=f"required file '{rel}' is missing",
                    suggestions=[
                        f"Create or restore '{rel}' before autonomous execution.",
                        "Update syncore.yaml if the contract no longer reflects the repo layout.",
                    ],
                    missing_files=[rel],
                )
        return {"status": "ok", "reason": "", "suggestions": []}

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

    def _normalize_workspace_command(self, command: str) -> str:
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            return command
        if not tokens:
            return command
        resolved = self._resolve_binary(tokens[0])
        if not resolved:
            return command
        if tokens[0] == "python" and resolved.endswith("python3"):
            tokens[0] = "python3"
            return shlex.join(tokens)
        if tokens[0] == "pip" and resolved.endswith("pip3"):
            tokens[0] = "pip3"
            return shlex.join(tokens)
        return command

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
        acceptance = self._merged_acceptance_criteria(
            task_preferences=task_preferences,
            contract=contract,
            runbook=runbook,
        )
        enriched_command_results = list(command_results)
        behavioral = self._run_behavioral_probes(
            root=root,
            acceptance=acceptance,
            policy=policy or {},
            command_results=enriched_command_results,
        )
        if behavioral["status"] != "ok":
            return behavioral
        forbidden_paths = self._string_list(runbook.get("forbidden_paths"))
        risk_rules = dict(runbook.get("risk_rules") or contract.get("risk_rules") or {})
        mechanical = self._verify_mechanical_gates(
            command_results=enriched_command_results,
            acceptance=acceptance,
            runner=runner or {},
        )
        if mechanical["status"] != "ok":
            return mechanical
        diff_risk = self._verify_diff_risk(
            changed_files=changed_files,
            forbidden_paths=forbidden_paths,
            risk_rules=risk_rules,
        )
        if diff_risk["status"] != "ok":
            return diff_risk
        acceptance_result = self._verify_acceptance_criteria(
            root=root,
            changed_files=changed_files,
            acceptance=acceptance,
        )
        if acceptance_result["status"] != "ok":
            return acceptance_result
        secret_check = self._verify_secret_safety(root=root, changed_files=changed_files)
        if secret_check["status"] != "ok":
            return secret_check
        failed_cmds = [
            item
            for item in enriched_command_results
            if str(item.get("status")) in {"failed", "blocked"}
        ]
        if failed_cmds:
            return {
                "status": "failed",
                "reason": "One or more workspace commands failed/blocked.",
                "failed_commands": [str(item.get("command")) for item in failed_cmds[:10]],
            }
        if not changed_files and not enriched_command_results:
            return {
                "status": "failed",
                "reason": "No changes or verification commands were produced.",
            }
        return {"status": "ok", "reason": ""}

    def _effective_workspace_policy(
        self,
        *,
        requested_profile: str,
        workspace_metadata: dict[str, object],
        task_preferences: dict[str, str],
    ) -> dict[str, object]:
        requested_profile = str(requested_profile or "").strip().lower()
        explicit_requested = requested_profile in self.WORKSPACE_POLICY_PROFILES
        profile = requested_profile if explicit_requested else "balanced"
        base = dict(self.WORKSPACE_POLICY_PROFILES[profile])
        pack_name = str(
            task_preferences.get("policy_pack")
            or workspace_metadata.get("policy_pack")
            or ""
        ).strip()
        pack = get_policy_pack(pack_name)
        if pack:
            override_profile = str(pack.get("profile") or "").strip()
            if not explicit_requested and override_profile in self.WORKSPACE_POLICY_PROFILES:
                base = dict(self.WORKSPACE_POLICY_PROFILES[override_profile])
                profile = override_profile
            pack_commands = tuple(pack.get("allow_commands") or ())
            if pack_commands:
                base["allow_commands"] = pack_commands
            pack_allowed_patterns = tuple(pack.get("allowed_command_patterns") or ())
            if pack_allowed_patterns:
                base["allowed_command_patterns"] = pack_allowed_patterns
            base["verification_required_commands"] = tuple(
                pack.get("verification_required_commands") or ()
            )
            base["allowed_actions"] = tuple(
                pack.get("allowed_actions") or base.get("allowed_actions") or ()
            )
            base["approval_required_paths"] = tuple(
                pack.get("approval_required_paths") or ()
            )
            base["network_policy"] = str(pack.get("network_policy") or "offline")
        runbook = dict(workspace_metadata.get("workspace_runbook") or {})
        runner_commands = dict(runbook.get("runner", {}).get("commands") or {})
        runbook_allowed = tuple(
            self._string_list(runbook.get("allowed_commands"))
            + self._string_list(runbook.get("runbook_commands"))
            + self._string_list(runbook.get("setup_commands"))
            + self._string_list(runbook.get("build_commands"))
            + self._string_list(runbook.get("test_commands"))
            + self._string_list(runbook.get("lint_commands"))
            + self._string_list(runbook.get("format_commands"))
            + self._string_list(runner_commands.get("setup"))
            + self._string_list(runner_commands.get("build"))
            + self._string_list(runner_commands.get("test"))
            + self._string_list(runner_commands.get("lint"))
            + self._string_list(runner_commands.get("format"))
        )
        if runbook_allowed:
            base["allow_commands"] = tuple(
                dict.fromkeys(tuple(base.get("allow_commands") or ()) + runbook_allowed)
            )
        runbook_probe_commands = tuple(self._string_list(runbook.get("probe_commands")))
        if runbook_probe_commands:
            base["allow_commands"] = (
                tuple(
                    dict.fromkeys(
                        tuple(base.get("allow_commands") or ()) + runbook_probe_commands
                    )
                )
            )
        runbook_patterns = tuple(self._string_list(runbook.get("allowed_command_patterns")))
        if runbook_patterns:
            base["allowed_command_patterns"] = runbook_patterns
        base["blocked_commands"] = tuple(self._string_list(runbook.get("blocked_commands")))
        base["allowed_paths"] = tuple(self._string_list(runbook.get("allowed_paths")))
        base["forbidden_paths"] = tuple(self._string_list(runbook.get("forbidden_paths")))
        base["approval_required_paths"] = tuple(
            self._string_list(runbook.get("approval_required_paths"))
        ) or tuple(base.get("approval_required_paths") or ())
        contract = dict(workspace_metadata.get("syncore_contract") or {})
        capabilities = dict(contract.get("capabilities") or {})
        allowed_actions = self._string_list(capabilities.get("allow_actions"))
        if allowed_actions:
            base["allowed_actions"] = tuple(allowed_actions)
        denied_actions = self._string_list(capabilities.get("deny_actions"))
        if denied_actions:
            base["denied_actions"] = tuple(denied_actions)
        base["profile"] = profile
        base["policy_pack"] = pack_name or None
        return base

    def _load_task_preferences(self, task_id: UUID) -> dict[str, str]:
        events = self._store.list_project_events(task_id=task_id, limit=200)
        for event in reversed(events):
            if event.event_type != "task.preferences":
                continue
            prefs: dict[str, str] = {}
            for key, value in event.event_data.items():
                if value is None:
                    continue
                prefs[str(key)] = str(value)
            return prefs
        return {}

    def _merged_acceptance_criteria(
        self,
        *,
        task_preferences: dict[str, str],
        contract: dict[str, object],
        runbook: dict[str, object],
    ) -> dict[str, list[str]]:
        contract_acceptance = contract.get("acceptance")
        source = (
            contract_acceptance
            if isinstance(contract_acceptance, dict)
            else runbook.get("acceptance")
        )
        source_dict = dict(source) if isinstance(source, dict) else {}
        runner_commands = dict(runbook.get("runner", {}).get("commands") or {})
        merged = {
            "must_pass_commands": self._string_list(source_dict.get("must_pass_commands")),
            "must_modify_paths": self._string_list(source_dict.get("must_modify_paths")),
            "must_not_modify_paths": self._string_list(source_dict.get("must_not_modify_paths")),
            "must_include_behavior": self._string_list(source_dict.get("must_include_behavior")),
            "must_create_paths": self._string_list(source_dict.get("must_create_paths")),
            "must_observe_output": self._string_list(source_dict.get("must_observe_output")),
            "probe_commands": self._string_list(source_dict.get("probe_commands")),
        }
        if not merged["probe_commands"]:
            merged["probe_commands"] = (
                self._string_list(runbook.get("probe_commands"))
                or self._string_list(runner_commands.get("probe"))
            )
        if not merged["must_observe_output"]:
            merged["must_observe_output"] = self._default_probe_markers(
                probe_commands=merged["probe_commands"]
            )
        for key in tuple(merged.keys()):
            pref_value = task_preferences.get(key)
            if pref_value:
                merged[key] = [item.strip() for item in pref_value.split(",") if item.strip()]
        return merged

    def _verify_mechanical_gates(
        self,
        *,
        command_results: list[dict[str, object]],
        acceptance: dict[str, list[str]],
        runner: dict[str, object],
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
        required = acceptance.get("must_pass_commands", [])
        if not required:
            runner_commands = dict(runner.get("commands") or {})
            required = self._string_list(runner_commands.get("test"))[:1]
        if required:
            observed_ok = {
                str(item.get("command") or "")
                for item in command_results
                if str(item.get("status")) == "ok"
            }
            missing = [
                command for command in required
                if not any(
                    self._workspace_commands_match(command, observed)
                    for observed in observed_ok
                )
            ]
            if missing:
                return {
                    "status": "failed",
                    "reason": "Required verification commands did not pass.",
                    "missing_commands": missing,
                }
        return {"status": "ok", "reason": ""}

    def _ensure_required_verification_commands_run(
        self,
        *,
        root: Path,
        command_results: list[dict[str, object]],
        acceptance: dict[str, list[str]],
        runner: dict[str, object],
        policy: dict[str, object],
    ) -> None:
        required = acceptance.get("must_pass_commands", [])
        if not required:
            runner_commands = dict(runner.get("commands") or {})
            required = self._string_list(runner_commands.get("test"))[:1]
        if not required:
            return
        observed = {
            str(item.get("command") or "")
            for item in command_results
        }
        for command in required:
            if any(self._workspace_commands_match(command, existing) for existing in observed):
                continue
            result = self._safe_run_workspace_command(root, command, policy=policy)
            command_results.append(result)
            observed.add(str(result.get("command") or command))

    def _workspace_commands_match(self, expected: str, observed: str) -> bool:
        normalized_expected = self._normalize_workspace_command(expected).strip()
        normalized_observed = self._normalize_workspace_command(observed).strip()
        if not normalized_expected or not normalized_observed:
            return False
        return (
            normalized_expected == normalized_observed
            or normalized_expected in normalized_observed
            or normalized_observed in normalized_expected
        )

    def _verify_diff_risk(
        self,
        *,
        changed_files: list[str],
        forbidden_paths: list[str],
        risk_rules: dict[str, object],
    ) -> dict[str, object]:
        if forbidden_paths:
            violations = [
                path
                for path in changed_files
                if any(
                    path == forbidden or path.startswith(forbidden.rstrip("/") + "/")
                    for forbidden in forbidden_paths
                )
            ]
            if violations:
                return {
                    "status": "failed",
                    "reason": "Workspace changed forbidden paths.",
                    "violations": violations[:20],
                }
        max_changed = risk_rules.get("max_changed_files")
        if (
            isinstance(max_changed, int)
            and max_changed > 0
            and len(set(changed_files)) > max_changed
        ):
            return {
                "status": "failed",
                "reason": "Workspace changed too many files for current risk budget.",
                "changed_files": len(set(changed_files)),
                "limit": max_changed,
            }
        return {"status": "ok", "reason": ""}

    def _verify_acceptance_criteria(
        self,
        *,
        root: Path,
        changed_files: list[str],
        acceptance: dict[str, list[str]],
    ) -> dict[str, object]:
        must_modify = acceptance.get("must_modify_paths", [])
        if must_modify:
            missing_paths = [
                path
                for path in must_modify
                if not any(
                    changed == path or changed.startswith(path.rstrip("/") + "/")
                    for changed in changed_files
                )
            ]
            if missing_paths:
                return {
                    "status": "failed",
                    "reason": "Required paths were not modified.",
                    "missing_paths": missing_paths,
                }
        must_not_modify = acceptance.get("must_not_modify_paths", [])
        if must_not_modify:
            violated = [
                path
                for path in changed_files
                if any(
                    path == forbidden or path.startswith(forbidden.rstrip("/") + "/")
                    for forbidden in must_not_modify
                )
            ]
            if violated:
                return {
                    "status": "failed",
                    "reason": "Disallowed paths were modified.",
                    "violations": violated[:20],
                }
        behaviors = acceptance.get("must_include_behavior", [])
        if behaviors:
            corpus: list[str] = []
            for rel in changed_files[:50]:
                target = root / rel
                if target.exists() and target.is_file():
                    try:
                        corpus.append(target.read_text(encoding="utf-8", errors="replace"))
                    except OSError:
                        continue
            joined = "\n".join(corpus).lower()
            missing_behaviors = [
                item for item in behaviors
                if item.lower() not in joined
            ]
            if missing_behaviors:
                return {
                    "status": "failed",
                    "reason": "Acceptance behavior markers were not found in changed artifacts.",
                    "missing_behaviors": missing_behaviors,
                }
        must_create = acceptance.get("must_create_paths", [])
        if must_create:
            missing_create = [
                path for path in must_create if not (root / path).exists()
            ]
            if missing_create:
                return {
                    "status": "failed",
                    "reason": "Required artifacts were not created.",
                    "missing_paths": missing_create,
                }
        return {"status": "ok", "reason": ""}

    def _run_behavioral_probes(
        self,
        *,
        root: Path,
        acceptance: dict[str, list[str]],
        policy: dict[str, object],
        command_results: list[dict[str, object]],
    ) -> dict[str, object]:
        probe_commands = acceptance.get("probe_commands", [])
        for command in probe_commands:
            result = self._safe_run_workspace_command(root, command, policy=policy or {})
            command_results.append(result)
            if str(result.get("status")) != "ok":
                return {
                    "status": "failed",
                    "reason": "Behavioral probe command failed.",
                    "failed_command": command,
                }
        expected_output = acceptance.get("must_observe_output", [])
        if expected_output:
            observed_output = "\n".join(
                str(item.get("output") or "")
                for item in command_results
                if str(item.get("status")) == "ok"
            ).lower()
            missing_output = [
                marker for marker in expected_output if marker.lower() not in observed_output
            ]
            if missing_output:
                return {
                    "status": "failed",
                    "reason": "Expected behavioral output markers were not observed.",
                    "missing_output_markers": missing_output,
                }
        return {"status": "ok", "reason": ""}

    def _default_probe_markers(self, *, probe_commands: list[str]) -> list[str]:
        markers: list[str] = []
        for command in probe_commands:
            if "python-ready" in command:
                markers.append("python-ready")
            elif "flask-ready" in command:
                markers.append("flask-ready")
            elif "node-ready" in command:
                markers.append("node-ready")
            elif "pnpm-ready" in command:
                markers.append("pnpm-ready")
            elif "go version" in command:
                markers.append("go version")
            elif "cargo --version" in command:
                markers.append("cargo")
            elif "java -version" in command:
                markers.append("version")
            elif "manage.py check" in command:
                markers.append("system check")
        return markers[:10]

    def _string_list(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, tuple):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

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
