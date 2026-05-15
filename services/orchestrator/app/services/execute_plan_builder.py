from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable
from uuid import UUID

from packages.contracts.python.models import ProjectEvent, Task
from services.memory import MemoryStoreProtocol

StringListFunc = Callable[[object], list[str]]
RecommendationContextFunc = Callable[[Task, dict[str, str]], str]
RecommendationStateFunc = Callable[[UUID], dict[str, object]]
ExtractListFunc = Callable[[str], list[str]]
PlanLinesFunc = Callable[[str], list[str]]
StrategyGuidanceFunc = Callable[[str], str]
ParseUUIDFunc = Callable[[str | None], UUID | None]


@dataclass(slots=True)
class ExecutePlanBuilder:
    store: MemoryStoreProtocol
    recommendation_context: RecommendationContextFunc
    recommendation_state: RecommendationStateFunc
    extract_paths: ExtractListFunc
    extract_command_candidates: ExtractListFunc
    extract_acceptance_checks: ExtractListFunc
    parse_plan_lines: PlanLinesFunc
    strategy_guidance: StrategyGuidanceFunc
    string_list: StringListFunc
    parse_uuid: ParseUUIDFunc

    def build(
        self,
        *,
        task: Task,
        prefs: dict[str, str],
        output_text: str,
        strategy: str,
    ) -> dict[str, object]:
        recommendation_context = self.recommendation_context(task, prefs)
        target_files = self.extract_paths(output_text)
        verification_commands = self.extract_command_candidates(output_text)
        acceptance_checks = self.extract_acceptance_checks(output_text)
        proposed_actions = self.parse_plan_lines(output_text)[:8]
        if recommendation_context and not target_files:
            recommendation_state = self.recommendation_state(
                self.parse_uuid(prefs.get("parent_task_id")) or task.id
            )
            event = recommendation_state.get("event")
            if isinstance(event, ProjectEvent):
                target_files = self.string_list(event.event_data.get("target_files"))
                if not verification_commands:
                    verification = str(event.event_data.get("verification_command") or "").strip()
                    if verification:
                        verification_commands = [verification]
        if not verification_commands and task.workspace_id is not None:
            workspace = self.store.get_workspace(task.workspace_id)
            if workspace is not None:
                runbook = dict(workspace.metadata.get("workspace_runbook") or {})
                verification_commands = self.string_list(runbook.get("test_commands"))[:2]
        if not acceptance_checks:
            acceptance_checks = [
                "Produce a concrete artifact or code change.",
                "Run verification commands and confirm success.",
            ]
        if not proposed_actions:
            proposed_actions = [
                "Inspect the repo state relevant to the task.",
                "Apply the smallest safe change required.",
                "Run verification and summarize the result.",
            ]
        risk_level = "medium"
        lowered = output_text.lower()
        if any(
            token in lowered
            for token in ("migration", "auth", "secret", "credential", "deploy")
        ):
            risk_level = "high"
        elif any(token in lowered for token in ("docs", "config", "test", "yaml", "readme")):
            risk_level = "low"
        payload = {
            "objective": task.title,
            "target_files": target_files[:12],
            "proposed_actions": proposed_actions[:8],
            "verification_commands": verification_commands[:4],
            "acceptance_checks": acceptance_checks[:8],
            "fallback_strategy": self.strategy_guidance(strategy),
            "risk_level": risk_level,
        }
        signature = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        payload["signature"] = signature
        return payload
