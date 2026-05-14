from __future__ import annotations

from dataclasses import dataclass

from packages.contracts.python.models import ProjectEvent
from services.memory import MemoryStoreProtocol

AUTONOMY_STRATEGIES = (
    "default",
    "tighten_scope",
    "increase_detail",
    "raise_verification",
    "switch_execution_role",
)


@dataclass(slots=True)
class FailurePolicy:
    store: MemoryStoreProtocol

    def select_replan_strategy(
        self,
        *,
        events: list[ProjectEvent],
        stage: str,
        cycle: int,
        execute_role: str,
    ) -> str:
        if cycle <= 1:
            return "default"
        recent_fail = self._latest_event(events, "autonomy.quality.failed")
        reason = str((recent_fail.event_data.get("reason") if recent_fail else "") or "").lower()
        candidates = [
            "tighten_scope",
            "increase_detail",
            "raise_verification",
            "switch_execution_role",
        ]
        if "short" in reason:
            candidates = [
                "increase_detail",
                "tighten_scope",
                "raise_verification",
                "switch_execution_role",
            ]
        elif "risk" in reason or stage == "review":
            candidates = [
                "raise_verification",
                "increase_detail",
                "tighten_scope",
                "switch_execution_role",
            ]
        elif execute_role == "coder":
            candidates = [
                "switch_execution_role",
                "increase_detail",
                "tighten_scope",
                "raise_verification",
            ]
        return self.best_strategy_from_feedback(candidates)

    def best_strategy_from_feedback(self, candidates: list[str]) -> str:
        feedback = self.store.list_project_events(task_id=None, limit=500)
        scores: dict[str, int] = {name: 0 for name in AUTONOMY_STRATEGIES}
        for event in feedback:
            if event.event_type != "autonomy.feedback":
                continue
            strategy = str(event.event_data.get("strategy") or "").strip()
            outcome = str(event.event_data.get("outcome") or "").strip()
            if strategy not in scores:
                continue
            if outcome == "success":
                scores[strategy] += 3
            elif outcome == "quality_failed":
                scores[strategy] -= 2
            elif outcome == "failed":
                scores[strategy] -= 3
        best = max(candidates, key=lambda item: scores.get(item, 0))
        return best if best in AUTONOMY_STRATEGIES else "default"

    @staticmethod
    def strategy_guidance(strategy: str) -> str:
        if strategy == "tighten_scope":
            return "Break work into smaller validated increments and avoid broad refactors."
        if strategy == "increase_detail":
            return "Increase implementation detail and include explicit step-by-step artifacts."
        if strategy == "raise_verification":
            return "Prioritize tests, checks, and explicit verification evidence."
        if strategy == "switch_execution_role":
            return "Shift execution perspective to reduce repeated blind spots."
        return "Deliver concise, actionable, and verifiable output."

    @staticmethod
    def _latest_event(events: list[ProjectEvent], event_type: str) -> ProjectEvent | None:
        for event in reversed(events):
            if event.event_type == event_type:
                return event
        return None
