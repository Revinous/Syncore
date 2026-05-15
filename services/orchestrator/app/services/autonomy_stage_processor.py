from __future__ import annotations

from typing import Any

from packages.contracts.python.models import ProjectEventCreate, RunExecutionRequest
from services.memory import MemoryStoreProtocol

from app.services.autonomy_stage_executor import AutonomyStageExecutor
from app.services.autonomy_stage_models import AutonomyStageContext
from app.services.autonomy_stage_outcomes import AutonomyStageOutcomeHandler


class AutonomyStageProcessor:
    def __init__(
        self,
        *,
        store: MemoryStoreProtocol,
        run_execution_service,
        runtime_selector,
        quality_gate,
        failure_handler,
        task_gate,
        workspace_execution_enabled: bool,
        workspace_execution_profile: str,
        workspace_max_steps: int,
        retry_base_seconds: float,
        review_pass_keyword: str,
        low_info_stop_enabled: bool,
        parse_positive_int,
        parse_uuid,
        role_for_stage,
        prompt_for_stage,
        select_replan_strategy,
        save_snapshot,
        record_feedback,
        persist_execute_plan,
        persist_stage_handoff_artifacts,
        spawn_subtasks_once,
        child_gate_status,
        finalize_task,
        record_mutation_intent,
        missing_sdlc_topics,
        extract_sdlc_checklist_status,
    ) -> None:
        self._store = store
        self._runtime_selector = runtime_selector
        self._quality_gate = quality_gate
        self._executor = AutonomyStageExecutor(
            store=store,
            run_execution_service=run_execution_service,
            workspace_execution_enabled=workspace_execution_enabled,
            workspace_execution_profile=workspace_execution_profile,
            workspace_max_steps=workspace_max_steps,
            parse_positive_int=parse_positive_int,
        )
        self._outcomes = AutonomyStageOutcomeHandler(
            store=store,
            quality_gate=quality_gate,
            failure_handler=failure_handler,
            task_gate=task_gate,
            retry_base_seconds=retry_base_seconds,
            review_pass_keyword=review_pass_keyword,
            low_info_stop_enabled=low_info_stop_enabled,
            parse_uuid=parse_uuid,
            record_feedback=record_feedback,
            persist_execute_plan=persist_execute_plan,
            persist_stage_handoff_artifacts=persist_stage_handoff_artifacts,
            spawn_subtasks_once=spawn_subtasks_once,
            child_gate_status=child_gate_status,
            finalize_task=finalize_task,
            save_snapshot=save_snapshot,
        )
        self._role_for_stage = role_for_stage
        self._prompt_for_stage = prompt_for_stage
        self._select_replan_strategy = select_replan_strategy
        self._record_mutation_intent = record_mutation_intent
        self._missing_sdlc_topics = missing_sdlc_topics
        self._extract_sdlc_checklist_status = extract_sdlc_checklist_status

    def process(self, *, context: AutonomyStageContext, events: list[Any]) -> dict[str, Any]:
        task = context.task
        task_id = task.id
        prefs = dict(context.prefs)
        stage = context.stage
        cycle = context.cycle
        strategy = self._select_replan_strategy(
            events=events,
            stage=stage,
            cycle=cycle,
            execute_role=context.execute_role,
        )
        effective_prefs = self._effective_prefs(events=events, prefs=prefs)
        previous_provider, previous_model = self._runtime_selector.latest_run_provider_model(
            task.id
        )
        provider = self._runtime_selector.resolve_provider(
            stage=stage,
            task=task,
            prefs=effective_prefs,
            previous_provider=previous_provider,
        )
        model = self._runtime_selector.resolve_model(
            stage=stage,
            task=task,
            provider=provider,
            prefs=effective_prefs,
        )
        prompt = self._prompt_for_stage(
            stage=stage,
            task=task,
            prefs=effective_prefs,
            cycle=cycle,
            strategy=strategy,
            enforce_sdlc=context.enforce_sdlc,
        )
        stage_role = self._role_for_stage(
            stage=stage,
            execute_role=context.execute_role,
            strategy=strategy,
        )
        self._record_stage_started(
            task_id=task_id,
            cycle=cycle,
            stage=stage,
            strategy=strategy,
            stage_role=stage_role,
            provider=provider,
            model=model,
            previous_provider=previous_provider,
            previous_model=previous_model,
            prefs=prefs,
        )
        if stage == "execute":
            self._record_mutation_intent(task=task, prefs=prefs)

        request = RunExecutionRequest(
            task_id=task_id,
            prompt=prompt,
            target_agent=stage_role,
            target_model=model,
            provider=provider,
            agent_role=stage_role,
            token_budget=8_000,
            max_output_tokens=1_200,
            temperature=0.2,
        )
        run = self._executor.execute(
            context=context,
            request=request,
            provider=provider,
            model=model,
        )
        self._runtime_selector.record_model_switch_if_needed(
            task_id=task_id,
            previous_provider=previous_provider,
            previous_model=previous_model,
            next_provider=run.provider,
            next_model=run.target_model,
            stage_role=stage_role,
            continuity_enabled=(prefs.get("maintain_context_continuity") or "true").lower()
            != "false",
            context_bundle_id=str(getattr(run, "optimized_bundle_id", "") or ""),
        )
        quality = self._quality_gate.stage_quality_gate(
            stage=stage,
            output_text=run.output_text,
            strategy=strategy,
            enforce_sdlc=context.enforce_sdlc,
            sdlc_checklist_items=(
                "requirements",
                "design",
                "implementation",
                "tests",
                "docs",
                "release",
            ),
            missing_sdlc_topics=self._missing_sdlc_topics,
            extract_sdlc_checklist_status=self._extract_sdlc_checklist_status,
        )
        local_echo_mode = self._runtime_selector.is_local_echo_mode(
            provider=run.provider,
            model=run.target_model,
        )
        if local_echo_mode and stage in {"execute", "review"} and not bool(quality["passed"]):
            quality = {
                "passed": True,
                "score": max(int(quality.get("score") or 0), 75),
                "reasons": ["local_echo_relaxed_gate"],
            }
        checklist_status = self._extract_sdlc_checklist_status(run.output_text)
        self._outcomes.record_stage_completed(
            context=context,
            run=run,
            strategy=strategy,
            checklist_status=checklist_status,
            quality=quality,
        )
        quality_result = self._outcomes.handle_quality_outcome(
            context=context,
            run=run,
            quality=quality,
            strategy=strategy,
        )
        if quality_result is not None:
            return quality_result
        if stage == "review":
            review_result = self._outcomes.handle_review_outcome(
                context=context,
                run=run,
                strategy=strategy,
                local_echo_mode=local_echo_mode,
            )
            if review_result is not None:
                return review_result
        return self._outcomes.handle_stage_success(
            context=context,
            run=run,
            strategy=strategy,
        )

    def handle_failure(
        self,
        *,
        context: AutonomyStageContext,
        events: list[Any],
        error: Exception,
    ) -> dict[str, Any]:
        strategy = self._select_replan_strategy(
            events=events,
            stage=context.stage,
            cycle=context.cycle,
            execute_role=context.execute_role,
        )
        return self._outcomes.handle_stage_failure(
            context=context,
            events=events,
            strategy=strategy,
            error=error,
        )

    def _effective_prefs(self, *, events: list[Any], prefs: dict[str, str]) -> dict[str, str]:
        effective = dict(prefs)
        switch_count = sum(
            1
            for event in events
            if getattr(event, "event_type", "") == "model.switch.completed"
        )
        if switch_count >= self._runtime_selector.resolve_provider_switch_budget(prefs):
            effective["allow_cross_provider_switching"] = "false"
        return effective

    def _record_stage_started(
        self,
        *,
        task_id,
        cycle: int,
        stage: str,
        strategy: str,
        stage_role: str,
        provider: str | None,
        model: str,
        previous_provider: str | None,
        previous_model: str | None,
        prefs: dict[str, str],
    ) -> None:
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="autonomy.stage.started",
                event_data={"stage": stage, "cycle": cycle, "strategy": strategy},
            )
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="autonomy.strategy.selected",
                event_data={"stage": stage, "cycle": cycle, "strategy": strategy},
            )
        )
        self._outcomes.record_stage_started_snapshot(
            task_id=task_id,
            cycle=cycle,
            stage=stage,
            strategy=strategy,
            stage_role=stage_role,
            provider=provider,
            model=model,
            previous_provider=previous_provider,
            previous_model=previous_model,
        )
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="model.routing.selected",
                event_data={
                    "stage": stage,
                    "provider": provider or "",
                    "target_model": model,
                    "previous_provider": previous_provider or "",
                    "previous_model": previous_model or "",
                    "continuity_mode": prefs.get("maintain_context_continuity") or "true",
                    "optimization_goal": prefs.get("model_optimization_goal") or "balanced",
                },
            )
        )
