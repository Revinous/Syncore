import json
from typing import Any
from uuid import UUID

from packages.contracts.python.models import BatonPacket, ProjectEvent, Task
from services.memory import MemoryStoreProtocol

from app.context.schemas import ContextSection, RawContextBundle


class ContextAssembler:
    def __init__(self, store: MemoryStoreProtocol, event_limit: int = 80) -> None:
        self._store = store
        self._event_limit = max(10, min(event_limit, 200))

    def assemble(
        self,
        task_id: UUID,
        target_agent: str,
        target_model: str,
        token_budget: int,
    ) -> RawContextBundle:
        task = self._store.get_task(task_id)
        if task is None:
            raise LookupError("Task not found")

        latest_packet = self._store.get_latest_baton_packet(task_id)
        events = self._store.list_project_events(task_id=task_id, limit=self._event_limit)
        prior_bundle = self._store.get_latest_context_bundle(task_id)

        sections: list[ContextSection] = [self._task_section(task)]

        if latest_packet is not None:
            sections.extend(self._baton_sections(latest_packet))

        routing_decision = self._extract_routing_decision(events)
        if routing_decision is not None:
            sections.append(
                ContextSection(
                    section_id="routing-decision",
                    title="Routing Decision",
                    section_type="routing",
                    content=routing_decision,
                    source="project_events",
                    priority=70,
                )
            )

        memory_events = [event for event in events if event.event_type.startswith("memory.")]
        if memory_events:
            sections.append(self._memory_summary_section(memory_events))

        for index, event in enumerate(events):
            sections.append(self._event_section(event, index=index, total=len(events)))

        if prior_bundle is not None:
            sections.append(
                ContextSection(
                    section_id=f"prior-bundle-{prior_bundle['bundle_id']}",
                    title="Prior Optimized Bundle",
                    section_type="prior_bundle",
                    content=(
                        f"bundle_id={prior_bundle['bundle_id']} "
                        f"target_agent={prior_bundle['target_agent']} "
                        f"target_model={prior_bundle['target_model']} "
                        f"included_refs={len(prior_bundle.get('included_refs', []))}"
                    ),
                    source="context_bundles",
                    priority=60,
                    metadata={"bundle_id": str(prior_bundle["bundle_id"])},
                )
            )

        return RawContextBundle(
            task_id=task_id,
            target_agent=target_agent,
            target_model=target_model,
            token_budget=token_budget,
            sections=sections,
            metadata={
                "event_count": len(events),
                "has_latest_baton": latest_packet is not None,
                "has_routing_decision": routing_decision is not None,
                "memory_event_count": len(memory_events),
            },
        )

    def _task_section(self, task: Task) -> ContextSection:
        content = "\n".join(
            [
                f"id: {task.id}",
                f"title: {task.title}",
                f"status: {task.status}",
                f"task_type: {task.task_type}",
                f"complexity: {task.complexity}",
            ]
        )
        return ContextSection(
            section_id=f"task-{task.id}",
            title="Task Snapshot",
            section_type="task",
            content=content,
            source="tasks",
            priority=100,
            is_critical=True,
        )

    def _baton_sections(self, packet: BatonPacket) -> list[ContextSection]:
        payload = packet.payload
        sections: list[ContextSection] = []

        baton_lines = [
            f"from_agent: {packet.from_agent}",
            f"to_agent: {packet.to_agent or 'any'}",
            f"summary: {packet.summary}",
            f"objective: {payload.objective}",
            "completed_work:",
            *[f"- {item}" for item in payload.completed_work],
            "open_questions:",
            *[f"- {item}" for item in payload.open_questions],
            f"next_best_action: {payload.next_best_action}",
            "relevant_artifacts:",
            *[f"- {item}" for item in payload.relevant_artifacts],
        ]
        sections.append(
            ContextSection(
                section_id=f"baton-{packet.id}",
                title="Latest Baton Packet",
                section_type="baton",
                content="\n".join(baton_lines),
                source="baton_packets",
                priority=95,
            )
        )

        if payload.constraints:
            sections.append(
                ContextSection(
                    section_id=f"constraints-{packet.id}",
                    title="Critical Constraints",
                    section_type="constraint",
                    content="\n".join(payload.constraints),
                    source="baton_packets",
                    is_critical=True,
                    priority=100,
                )
            )

        return sections

    def _memory_summary_section(self, memory_events: list[ProjectEvent]) -> ContextSection:
        lines = []
        for event in memory_events[-5:]:
            summary = self._event_summary(event.event_type, event.event_data, max_chars=130)
            lines.append(f"{event.created_at.isoformat()} {summary}")
        return ContextSection(
            section_id="memory-summary",
            title="Relevant Memory",
            section_type="memory",
            content="\n".join(lines),
            source="project_events",
            priority=75,
        )

    def _extract_routing_decision(self, events: list[ProjectEvent]) -> str | None:
        for event in reversed(events):
            if not event.event_type.startswith("routing."):
                continue
            worker_role = event.event_data.get("worker_role")
            model_tier = event.event_data.get("model_tier")
            reasoning = event.event_data.get("reasoning")
            if worker_role and model_tier:
                parts = [
                    f"worker_role: {worker_role}",
                    f"model_tier: {model_tier}",
                ]
                if reasoning:
                    parts.append(f"reasoning: {reasoning}")
                return "\n".join(parts)
        return None

    def _event_section(self, event: ProjectEvent, *, index: int, total: int) -> ContextSection:
        serialized = json.dumps(event.event_data, sort_keys=True, ensure_ascii=True)
        section_type = self._classify_event_type(event.event_type, event.event_data, serialized)
        is_critical = section_type in {"constraint", "error", "schema", "code_patch"} or (
            self._contains_critical_marker(event.event_type)
            or self._contains_critical_marker(serialized)
        )
        priority = 40 + int((index / max(total, 1)) * 30)
        content = "\n".join(
            [
                f"event_type: {event.event_type}",
                f"created_at: {event.created_at.isoformat()}",
                f"event_data: {serialized}",
            ]
        )
        return ContextSection(
            section_id=f"event-{event.id}",
            title=f"Event: {event.event_type}",
            section_type=section_type,
            content=content,
            source="project_events",
            is_critical=is_critical,
            priority=priority,
            created_at=event.created_at,
            metadata={"event_id": str(event.id)},
        )

    def _event_summary(
        self, event_type: str, event_data: dict[str, Any], *, max_chars: int = 180
    ) -> str:
        serialized = json.dumps(event_data, sort_keys=True, ensure_ascii=True)
        if len(serialized) > max_chars:
            serialized = f"{serialized[: max_chars - 3]}..."
        return f"{event_type}: {serialized}"

    def _contains_critical_marker(self, content: str) -> bool:
        lowered = content.lower()
        markers = (
            "do not",
            "must",
            "required",
            "error",
            "exception",
            "traceback",
            "schema",
            "diff --git",
            "patch",
        )
        return any(marker in lowered for marker in markers)

    def _classify_event_type(
        self, event_type: str, event_data: dict[str, Any], serialized: str
    ) -> str:
        lower_type = event_type.lower()
        keys = {key.lower() for key in event_data.keys()}
        lower_payload = serialized.lower()

        if any(marker in lower_type for marker in ("schema", "json_schema")) or any(
            key in keys for key in ("schema", "json_schema")
        ):
            return "schema"
        if any(marker in lower_type for marker in ("patch", "diff")) or any(
            key in keys for key in ("patch", "diff", "active_patch")
        ):
            return "code_patch"
        if any(marker in lower_payload for marker in ("traceback", "exception", "error:")):
            return "error"
        if any(key in keys for key in ("stdout", "stderr", "log", "logs")):
            return "log_output"
        if any(key in keys for key in ("tool_output", "output", "command_output")):
            return "tool_output"
        if any(key in keys for key in ("file_content", "file_dump", "source_blob")):
            return "file_content"
        return "project_event"
