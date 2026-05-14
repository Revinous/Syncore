from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from packages.contracts.python.models import ProjectEvent, Task
from services.memory import MemoryStoreProtocol

ParseUUIDFunc = Callable[[str | None], UUID | None]


@dataclass(slots=True)
class CandidateStateService:
    store: MemoryStoreProtocol
    parse_uuid: ParseUUIDFunc

    def selected_candidate_prompt_context(
        self,
        *,
        task: Task,
        prefs: dict[str, str],
    ) -> str:
        if task.task_type != "implementation":
            return ""
        parent_id = self.parse_uuid(prefs.get("parent_task_id"))
        if parent_id is None:
            return ""
        sibling_state = self.selected_candidate_state(parent_id)
        if sibling_state["status"] != "ready":
            return ""
        event = sibling_state["event"]
        summary = str(event.event_data.get("summary") or "").strip()
        action = str(event.event_data.get("action") or "").strip()
        target_files = str(event.event_data.get("target_files") or "").strip()
        verification = str(event.event_data.get("verification_command") or "").strip()
        risks = str(event.event_data.get("risks") or "").strip()
        confidence = str(event.event_data.get("confidence") or "").strip()
        candidate_type = str(event.event_data.get("candidate_type") or "").strip()
        context_lines = ["Selected improvement candidate from analysis child:"]
        if candidate_type:
            context_lines.append(f"- Candidate type: {candidate_type}")
        if summary:
            context_lines.append(f"- Candidate improvement: {summary}")
        if action:
            context_lines.append(f"- Required implementation: {action}")
        if target_files:
            context_lines.append(f"- Suggested files: {target_files}")
        if verification:
            context_lines.append(f"- Verification command: {verification}")
        if confidence:
            context_lines.append(f"- Confidence: {confidence}")
        if risks:
            context_lines.append(f"- Risks/constraints: {risks}")
        context_lines.append(
            "- Do not re-scope the task. "
            "Act on this recommendation unless the repo state proves it invalid."
        )
        return "\n".join(context_lines)

    def selected_candidate_state(self, parent_id: UUID) -> dict[str, object]:
        child_ids = self.spawned_child_ids(parent_id)
        for child_id in child_ids:
            child = self.store.get_task(child_id)
            if child is None or child.task_type != "analysis":
                continue
            child_events = self.store.list_project_events(task_id=child.id, limit=250)
            selected = self._latest_event(child_events, "autonomy.candidate.selected")
            if selected is not None:
                return {"status": "ready", "event": selected, "task": child}
        return self.recommended_improvement_state(parent_id)

    def recommended_improvement_state(self, parent_id: UUID) -> dict[str, object]:
        child_ids = self.spawned_child_ids(parent_id)
        analysis_children: list[Task] = []
        for child_id in child_ids:
            child = self.store.get_task(child_id)
            if child is None or child.task_type != "analysis":
                continue
            analysis_children.append(child)
            child_events = self.store.list_project_events(task_id=child.id, limit=200)
            recommendation = self._latest_event(
                child_events, "autonomy.recommended_improvement"
            )
            if recommendation is not None:
                return {"status": "ready", "event": recommendation, "task": child}
        if not analysis_children:
            return {"status": "ready", "note": "No analysis sibling present."}
        blocked = [child for child in analysis_children if child.status == "blocked"]
        if blocked:
            return {
                "status": "blocked",
                "note": "Analysis child blocked before producing a recommended improvement baton.",
            }
        pending = [child for child in analysis_children if child.status != "completed"]
        if pending:
            return {
                "status": "waiting",
                "note": "Waiting for analysis child to produce a recommended improvement baton.",
            }
        for child in analysis_children:
            baton = self.store.get_latest_baton_packet(child.id)
            if baton is not None:
                summary = baton.summary.strip()
                action = baton.payload.next_best_action.strip()
                target_files = ", ".join(baton.payload.relevant_artifacts[:10])
                event = ProjectEvent(
                    id=UUID(int=0),
                    task_id=child.id,
                    event_type="autonomy.recommended_improvement",
                    event_data={
                        "summary": summary[:250],
                        "action": action[:250],
                        "target_files": target_files[:250],
                        "verification_command": "",
                        "risks": "; ".join(baton.payload.constraints[:6])[:250],
                    },
                    created_at=datetime.now(timezone.utc),
                )
                return {"status": "ready", "event": event, "task": child}
        return {
            "status": "blocked",
            "note": "Analysis child completed without a concrete recommended improvement baton.",
        }

    def spawned_child_ids(self, parent_id: UUID) -> list[UUID]:
        events = self.store.list_project_events(task_id=parent_id, limit=500)
        spawned = self._latest_event(events, "autonomy.subtasks.spawned")
        if spawned is None:
            return []
        raw_ids = str(spawned.event_data.get("child_task_ids") or "").strip()
        ids: list[UUID] = []
        for raw in (item.strip() for item in raw_ids.split(",") if item.strip()):
            parsed = self.parse_uuid(raw)
            if parsed is not None:
                ids.append(parsed)
        return ids

    @staticmethod
    def _latest_event(events: list[ProjectEvent], event_type: str) -> ProjectEvent | None:
        for event in reversed(events):
            if event.event_type == event_type:
                return event
        return None
