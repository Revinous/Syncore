from __future__ import annotations

from pathlib import Path

from packages.contracts.python.models import RunExecutionRequest
from services.memory import MemoryStoreProtocol

from app.services.workspace_acceptance_service import string_list
from app.services.workspace_action_dispatcher import WorkspaceLoopState
from app.services.workspace_execution_utils import classify_workspace_issue


class WorkspaceExecutionCoordinator:
    def __init__(
        self,
        *,
        store: MemoryStoreProtocol,
        default_provider: str,
        policy_resolver,
        planner,
        preflight_service,
        dispatcher,
        verifier,
        finalizer,
        resolve_provider,
        task_preferences,
        attempt_auto_repair,
        record_event,
        failure_handler,
    ) -> None:
        self._store = store
        self._default_provider = default_provider
        self._policy_resolver = policy_resolver
        self._planner = planner
        self._preflight_service = preflight_service
        self._dispatcher = dispatcher
        self._verifier = verifier
        self._finalizer = finalizer
        self._resolve_provider = resolve_provider
        self._task_preferences = task_preferences
        self._attempt_auto_repair = attempt_auto_repair
        self._record_event = record_event
        self._failure_handler = failure_handler

    def execute_loop(
        self,
        payload: RunExecutionRequest,
        *,
        max_steps: int,
        policy_profile: str,
        dry_run: bool,
        require_approval: bool,
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
        task_preferences = self._task_preferences(payload.task_id)
        contract = dict(workspace.metadata.get("syncore_contract") or {})
        runbook = dict(workspace.metadata.get("workspace_runbook") or {})
        runner = dict(workspace.metadata.get("workspace_runner") or runbook.get("runner") or {})
        policy = self._policy_resolver.resolve_workspace_policy(
            requested_profile=profile,
            workspace_metadata=workspace.metadata,
            task_preferences=task_preferences,
        )
        profile = str(policy.get("profile") or "balanced")

        preflight = self._preflight_service.verify(
            root=root,
            provider_hint=payload.provider,
            required_env=string_list(runbook.get("required_env")),
            required_binaries=string_list(runbook.get("required_binaries"))
            or string_list(runner.get("required_binaries")),
            required_files=string_list(runbook.get("required_files")),
            supported_os=string_list(runner.get("supported_os")),
            runner=runner,
        )
        if preflight["status"] != "ok":
            repaired = self._attempt_auto_repair(
                task_id=payload.task_id,
                root=root,
                runner=runner,
                runbook=runbook,
                policy=policy,
            )
            if repaired:
                preflight = self._preflight_service.verify(
                    root=root,
                    provider_hint=payload.provider,
                    required_env=string_list(runbook.get("required_env")),
                    required_binaries=string_list(runbook.get("required_binaries"))
                    or string_list(runner.get("required_binaries")),
                    required_files=string_list(runbook.get("required_files")),
                    supported_os=string_list(runner.get("supported_os")),
                    runner=runner,
                )
        if preflight["status"] != "ok":
            classification = classify_workspace_issue(
                stage="preflight",
                reason=str(preflight.get("reason") or "unknown"),
            )
            self._finalizer.record_learning_failure(
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
                    "suggestions": " | ".join(
                        str(item) for item in preflight.get("suggestions", [])
                    )[:250],
                },
            )
            raise ValueError(str(preflight.get("reason") or "Workspace preflight failed"))

        state = WorkspaceLoopState()
        provider_name, provider = self._resolve_provider(payload.provider)
        max_steps = max(1, min(max_steps, 8))

        self._record_event(
            task_id=payload.task_id,
            event_type="workspace.execution.state.changed",
            event_data={"state": "planned", "profile": profile, "dry_run": dry_run},
        )
        planned_actions = self._planner.parse_plan_lines(
            provider.complete(
                model=payload.target_model,
                prompt=self._planner.build_planner_prompt(
                    base_prompt=payload.prompt,
                    workspace_runbook=runbook,
                    profile=profile,
                ),
                system_prompt=payload.system_prompt,
                max_output_tokens=max(256, min(payload.max_output_tokens, 800)),
                temperature=0.1,
            ).output_text
        )
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
            actions = self._planner.parse_worker_actions(
                provider.complete(
                    model=payload.target_model,
                    prompt=self._planner.build_worker_prompt(
                        base_prompt=payload.prompt,
                        file_snapshot=self._planner.workspace_snapshot(root),
                        step=step,
                        max_steps=max_steps,
                        contract=contract,
                        runner=runner,
                        policy=policy,
                    ),
                    system_prompt=payload.system_prompt,
                    max_output_tokens=payload.max_output_tokens,
                    temperature=payload.temperature,
                ).output_text
            )
            if not actions:
                continue
            finished = self._dispatcher.dispatch_actions(
                task_id=payload.task_id,
                root=root,
                actions=actions,
                policy=policy,
                runner=runner,
                state=state,
            )
            if finished:
                step = max_steps
            if state.changed_files or state.command_results:
                self._verifier.ensure_required_verification_commands_run(
                    root=root,
                    command_results=state.command_results,
                    acceptance=self._verifier.merged_acceptance_criteria(
                        task_preferences=task_preferences,
                        contract=contract,
                        runbook=runbook,
                    ),
                    runner=runner,
                    policy=policy,
                )
                step_verification = self._verifier.verify_workspace_execution(
                    changed_files=state.changed_files,
                    command_results=list(state.command_results),
                    root=root,
                    task_preferences=task_preferences,
                    contract=contract,
                    runbook=runbook,
                    runner=runner,
                    policy=policy,
                )
                if step_verification["status"] == "ok":
                    if not state.finish_summary:
                        state.finish_summary = (
                            "Workspace execution loop completed after verification passed."
                        )
                    break

        self._record_event(
            task_id=payload.task_id,
            event_type="workspace.execution.state.changed",
            event_data={"state": "verifying", "profile": profile},
        )
        self._verifier.ensure_required_verification_commands_run(
            root=root,
            command_results=state.command_results,
            acceptance=self._verifier.merged_acceptance_criteria(
                task_preferences=task_preferences,
                contract=contract,
                runbook=runbook,
            ),
            runner=runner,
            policy=policy,
        )
        verification = self._verifier.verify_workspace_execution(
            changed_files=state.changed_files,
            command_results=state.command_results,
            root=root,
            task_preferences=task_preferences,
            contract=contract,
            runbook=runbook,
            runner=runner,
            policy=policy,
        )
        if str(verification.get("reason") or "") == "Required verification commands did not pass.":
            self._verifier.run_all_runner_test_commands(
                root=root,
                command_results=state.command_results,
                runner=runner,
                policy=policy,
            )
            verification = self._verifier.verify_workspace_execution(
                changed_files=state.changed_files,
                command_results=state.command_results,
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
            verification = {"status": "ok", "reason": "local_echo_noop_execution_accepted"}
            state.completed_work.append(
                "No-op local echo execution accepted for autonomy dry progression."
            )
        if verification["status"] != "ok":
            self._failure_handler.fail_verification(
                payload=payload,
                task=task,
                provider_name=provider_name,
                target_model=payload.target_model,
                profile=profile,
                planned_actions=planned_actions,
                state=state,
                verification=verification,
            )

        candidate_validation = self._finalizer.validate_meaningful_candidate_change(
            task_id=payload.task_id,
            task_preferences=task_preferences,
            changed_files=state.changed_files,
        )
        if candidate_validation["status"] != "ok":
            self._failure_handler.fail_meaningful_change(
                payload=payload,
                provider_name=provider_name,
                target_model=payload.target_model,
                profile=profile,
                planned_actions=planned_actions,
                state=state,
                verification=verification,
                candidate_validation=candidate_validation,
            )

        return self._finalizer.finalize_success(
            task_id=payload.task_id,
            workspace_id=task.workspace_id,
            from_agent=payload.target_agent,
            objective=payload.prompt,
            provider=provider_name,
            target_model=payload.target_model,
            profile=profile,
            changed_files=state.changed_files,
            diff_refs=state.diff_refs,
            read_refs=state.read_refs,
            planned_actions=planned_actions,
            command_results=state.command_results,
            verification=verification,
            finish_summary=state.finish_summary,
            completed_work=state.completed_work,
            next_action=state.next_action,
            policy=policy,
            runner=runner,
        )
