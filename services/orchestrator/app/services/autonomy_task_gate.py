from __future__ import annotations

from datetime import datetime
from uuid import UUID

from packages.contracts.python.models import ProjectEvent, ProjectEventCreate
from services.memory import MemoryStoreProtocol


class AutonomyTaskGate:
    def __init__(
        self,
        *,
        store: MemoryStoreProtocol,
        latest_event,
        event_int,
        event_bool,
    ) -> None:
        self._store = store
        self._latest_event = latest_event
        self._event_int = event_int
        self._event_bool = event_bool

    def current_cycle(self, events: list[ProjectEvent]) -> int:
        for event in reversed(events):
            if event.event_type != "autonomy.cycle.started":
                continue
            cycle = self._event_int(event.event_data.get("cycle"))
            if cycle is not None and cycle >= 1:
                return cycle
        return 1

    def total_step_events(self, events: list[ProjectEvent]) -> int:
        tracked = {"autonomy.stage.completed", "autonomy.stage.failed"}
        return sum(1 for event in events if event.event_type in tracked)

    def approval_gate_state(
        self,
        *,
        events: list[ProjectEvent],
        stage: str,
        requires_approval: bool,
    ) -> str:
        if not requires_approval or stage != "execute":
            return "not_required"
        approval = self._latest_event(events, "autonomy.approval")
        if approval is None:
            return "awaiting"
        approved = self._event_bool(approval.event_data.get("approved"))
        return "approved" if approved else "rejected"

    def ensure_approval_requested(self, *, task_id: UUID, events: list[ProjectEvent]) -> None:
        if self._latest_event(events, "autonomy.approval.requested") is not None:
            return
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task_id,
                event_type="autonomy.approval.requested",
                event_data={"stage": "execute"},
            )
        )

    def next_stage(
        self,
        events: list[ProjectEvent],
        *,
        cycle: int,
        stages: tuple[str, ...],
    ) -> str | None:
        completed: set[str] = set()
        for event in events:
            if event.event_type != "autonomy.stage.completed":
                continue
            event_cycle = self._event_int(event.event_data.get("cycle")) or 1
            if event_cycle != cycle:
                continue
            stage = str(event.event_data.get("stage") or "").strip().lower()
            if stage in stages:
                completed.add(stage)
        for stage in stages:
            if stage not in completed:
                return stage
        return None

    def scheduled_retry_epoch(
        self,
        events: list[ProjectEvent],
        stage: str,
        *,
        cycle: int,
    ) -> float | None:
        for event in reversed(events):
            if event.event_type != "autonomy.retry.scheduled":
                continue
            if str(event.event_data.get("stage") or "").strip().lower() != stage:
                continue
            event_cycle = self._event_int(event.event_data.get("cycle")) or 1
            if event_cycle != cycle:
                continue
            retry_epoch = event.event_data.get("retry_at_epoch")
            if isinstance(retry_epoch, (int, float)):
                return float(retry_epoch)
            if isinstance(retry_epoch, str):
                try:
                    return float(retry_epoch)
                except ValueError:
                    return None
        return None

    def stage_inflight(self, events: list[ProjectEvent], stage: str, *, cycle: int) -> bool:
        started_at: datetime | None = None
        terminal_at: datetime | None = None
        for event in events:
            event_cycle = self._event_int(event.event_data.get("cycle")) or 1
            if event_cycle != cycle:
                continue
            event_stage = str(event.event_data.get("stage") or "").strip().lower()
            if event_stage != stage:
                continue
            if event.event_type == "autonomy.stage.started":
                started_at = event.created_at
            elif event.event_type in {"autonomy.stage.completed", "autonomy.stage.failed"}:
                terminal_at = event.created_at
        return started_at is not None and (terminal_at is None or terminal_at < started_at)

    def failed_attempts(self, events: list[ProjectEvent], stage: str, *, cycle: int) -> int:
        count = 0
        for event in events:
            if event.event_type != "autonomy.stage.failed":
                continue
            event_cycle = self._event_int(event.event_data.get("cycle")) or 1
            if event_cycle != cycle:
                continue
            if str(event.event_data.get("stage") or "").strip().lower() == stage:
                count += 1
        return count
