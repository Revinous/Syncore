from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from packages.contracts.python.models import ProjectEvent, ProjectEventCreate, Task, TaskUpdate
from services.analyst.digest import AnalystDigestService
from services.memory import MemoryStoreProtocol


@dataclass(slots=True)
class TaskFinalizationService:
    store: MemoryStoreProtocol
    digest_service: AnalystDigestService

    def finalize_task(self, task_id: UUID) -> None:
        task = self.store.get_task(task_id)
        if task is not None and task.status != "completed":
            self.store.update_task(task_id, TaskUpdate(status="completed"))
        events = self.store.list_project_events(task_id=task_id, limit=500)
        if self._latest_event(events, "autonomy.completed") is None:
            latest_run_id = self.latest_stage_completion(events)
            self.store.save_project_event(
                ProjectEventCreate(
                    task_id=task_id,
                    event_type="autonomy.completed",
                    event_data={"run_id": str(latest_run_id) if latest_run_id else ""},
                )
            )
        self.generate_digest_event(task_id)

    def child_gate_status(self, *, task: Task, events: list[ProjectEvent]) -> dict[str, str]:
        spawned = self._latest_event(events, "autonomy.subtasks.spawned")
        if spawned is None:
            return {"mode": "none"}
        raw_ids = str(spawned.event_data.get("child_task_ids") or "").strip()
        if not raw_ids:
            return {"mode": "none"}
        child_ids = [item.strip() for item in raw_ids.split(",") if item.strip()]
        if not child_ids:
            return {"mode": "none"}

        blocked: list[str] = []
        completed = 0
        active = 0
        for raw in child_ids:
            try:
                child_id = UUID(raw)
            except ValueError:
                continue
            child = self.store.get_task(child_id)
            if child is None:
                continue
            if child.status == "completed":
                completed += 1
            elif child.status == "blocked":
                blocked.append(str(child.id))
            else:
                active += 1

        if blocked:
            return {
                "mode": "children_failed",
                "note": f"Child tasks blocked: {', '.join(blocked[:5])}.",
            }
        if completed >= len(child_ids) and len(child_ids) > 0:
            if self._latest_event(events, "autonomy.children.completed") is None:
                self.store.save_project_event(
                    ProjectEventCreate(
                        task_id=task.id,
                        event_type="autonomy.children.completed",
                        event_data={"count": len(child_ids)},
                    )
                )
            return {"mode": "children_completed", "note": "All child tasks completed."}
        return {
            "mode": "awaiting_children",
            "note": f"Waiting for child tasks: completed={completed}, active={active}.",
        }

    def generate_digest_event(self, task_id: UUID) -> None:
        events = self.store.list_project_events(task_id=task_id, limit=200)
        digest = self.digest_service.generate_digest(
            task_id=task_id,
            events=events,
            latest_baton=self.store.get_latest_baton_packet(task_id),
        )
        self.store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="analyst.digest.generated",
                event_data={
                    "headline": digest.headline[:250],
                    "risk_level": digest.risk_level,
                    "total_events": digest.total_events,
                },
            )
        )

    @staticmethod
    def latest_stage_completion(events: list[ProjectEvent]) -> UUID | None:
        for event in reversed(events):
            if event.event_type != "autonomy.stage.completed":
                continue
            raw = str(event.event_data.get("run_id") or "").strip()
            if not raw:
                continue
            try:
                return UUID(raw)
            except ValueError:
                return None
        return None

    @staticmethod
    def _latest_event(events: list[ProjectEvent], event_type: str) -> ProjectEvent | None:
        for event in reversed(events):
            if event.event_type == event_type:
                return event
        return None
