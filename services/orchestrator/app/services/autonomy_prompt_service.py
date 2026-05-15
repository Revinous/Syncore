from __future__ import annotations

from packages.contracts.python.models import ProjectEventCreate, Task


class AutonomyPromptService:
    def __init__(
        self,
        *,
        store,
        review_pass_keyword: str,
        strategy_guidance,
        latest_execute_plan,
        recommendation_service,
        string_list,
    ) -> None:
        self._store = store
        self._review_pass_keyword = review_pass_keyword
        self._strategy_guidance = strategy_guidance
        self._latest_execute_plan = latest_execute_plan
        self._recommendations = recommendation_service
        self._string_list = string_list

    def role_for_stage(self, *, stage: str, execute_role: str, strategy: str) -> str:
        if stage == "plan":
            return "planner"
        if stage == "execute":
            if strategy == "switch_execution_role":
                return "analyst" if execute_role == "coder" else "coder"
            return _normalize_agent_role(execute_role)
        return "reviewer"

    def prompt_for_stage(
        self,
        *,
        stage: str,
        task: Task,
        prefs: dict[str, str],
        cycle: int,
        strategy: str,
        enforce_sdlc: bool,
    ) -> str:
        guidance = self._strategy_guidance(strategy)
        sdlc_instruction = ""
        if enforce_sdlc:
            sdlc_instruction = (
                "\nSDLC enforcement is ON. Use this exact checklist and mark status explicitly:\n"
                "- [ ] requirements\n"
                "- [ ] design\n"
                "- [ ] implementation\n"
                "- [ ] tests\n"
                "- [ ] docs\n"
                "- [ ] release\n"
                "Use [x] only when done with concrete evidence."
            )
        if stage == "plan":
            mode = "Replan" if cycle > 1 else "Plan"
            return (
                f"You are Syncore planner ({mode}).\n"
                f"Task title: {task.title}\n"
                f"Task type: {task.task_type}\n"
                f"Complexity: {task.complexity}\n"
                f"Strategy: {strategy}.\n"
                f"Guidance: {guidance}\n"
                f"{sdlc_instruction}\n"
                "Produce a short implementation plan with clear first action, risks, checkpoints, "
                "target files, verification commands, acceptance checks, and fallback strategy."
            )
        if stage == "execute":
            preferred = prefs.get("execution_prompt", "").strip()
            recommendation_context = self._recommendations.selected_candidate_prompt_context(
                task=task,
                prefs=prefs,
            )
            execute_plan_context = self.execute_plan_prompt_context(task)
            analysis_context = self._recommendations.workspace_analysis_prompt_context(task)
            if preferred:
                suffix_parts = []
                if analysis_context:
                    suffix_parts.append(analysis_context)
                if execute_plan_context:
                    suffix_parts.append(execute_plan_context)
                if recommendation_context:
                    suffix_parts.append(recommendation_context)
                suffix_parts.append(f"Strategy: {strategy}. Guidance: {guidance}")
                return f"{preferred}\n\n" + "\n\n".join(suffix_parts)
            if recommendation_context:
                return (
                    "You are the Syncore implementation worker.\n"
                    f"Task title: {task.title}\n"
                    f"Task type: {task.task_type}\n"
                    f"Complexity: {task.complexity}\n"
                    f"{execute_plan_context}\n\n"
                    f"{recommendation_context}\n\n"
                    f"Strategy: {strategy}. Guidance: {guidance}\n"
                    "Apply the recommended improvement directly. Make the smallest safe change, "
                    "then verify it with the recommended command or the repo runbook."
                )
            if execute_plan_context:
                return (
                    "You are the Syncore implementation worker.\n"
                    f"Task title: {task.title}\n"
                    f"Task type: {task.task_type}\n"
                    f"Complexity: {task.complexity}\n"
                    f"{execute_plan_context}\n\n"
                    f"Strategy: {strategy}. Guidance: {guidance}\n"
                    "Execute only against this plan. Do not broaden scope. If the plan is invalid, "
                    "return the precise blocker and stop."
                )
            if analysis_context:
                return (
                    "You are the Syncore repository analyst.\n"
                    f"Task title: {task.title}\n"
                    f"Task type: {task.task_type}\n"
                    f"Complexity: {task.complexity}\n"
                    f"{analysis_context}\n\n"
                    f"Strategy: {strategy}. Guidance: {guidance}\n"
                    "Choose exactly one safe, high-confidence improvement. Return: candidate "
                    "improvement, required implementation, target files, risks, and "
                    "verification command."
                )
            return _default_prompt(task, strategy=strategy, guidance=guidance)
        return (
            "You are Syncore reviewer.\n"
            f"Review task outcome for: {task.title}\n"
            f"Strategy used: {strategy}. Guidance: {guidance}\n"
            f"{sdlc_instruction}\n"
            f"If acceptable, include exact token: {self._review_pass_keyword}\n"
            "Return pass/fail with key risks, coverage notes, next verification step, and include "
            "exact marker `meaningful_change=true` or `meaningful_change=false`."
        )

    def execute_plan_prompt_context(self, task: Task) -> str:
        plan = self._latest_execute_plan(task.id)
        if plan is None:
            return ""
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.execute_plan.reused",
                event_data={
                    "cycle": int(plan.get("cycle") or 1),
                    "signature": str(plan.get("signature") or "")[:120],
                },
            )
        )
        lines = ["Execute plan:"]
        lines.append(f"- Objective: {str(plan.get('objective') or '').strip()}")
        target_files = self._string_list(plan.get("target_files"))
        actions = self._string_list(plan.get("actions"))
        if actions:
            lines.append(f"- Actions: {'; '.join(actions[:6])}")
        if target_files:
            lines.append(f"- Target files: {', '.join(target_files[:12])}")
        verification_commands = self._string_list(plan.get("verification_commands"))
        if verification_commands:
            lines.append(f"- Verification commands: {', '.join(verification_commands[:6])}")
        acceptance_checks = self._string_list(plan.get("acceptance_checks"))
        if acceptance_checks:
            lines.append(f"- Acceptance checks: {'; '.join(acceptance_checks[:6])}")
        fallback = str(plan.get("fallback_strategy") or "").strip()
        if fallback:
            lines.append(f"- Fallback strategy: {fallback}")
        risk_level = str(plan.get("risk_level") or "").strip()
        if risk_level:
            lines.append(f"- Risk level: {risk_level}")
        return "\n".join(lines)


def _normalize_agent_role(candidate: str) -> str:
    normalized = candidate.strip().lower()
    if normalized in {"planner", "coder", "reviewer", "analyst", "memory"}:
        return normalized
    if normalized == "orchestrator":
        return "coder"
    return "coder"


def _default_prompt(task: Task, *, strategy: str, guidance: str) -> str:
    return (
        "You are the autonomous implementation worker.\n"
        f"Task title: {task.title}\n"
        f"Task type: {task.task_type}\n"
        f"Complexity: {task.complexity}\n"
        f"Strategy: {strategy}. Guidance: {guidance}\n"
        "Perform the next concrete step, explain what changed, and include how you verified it."
    )
