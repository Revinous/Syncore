from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from packages.contracts.python.models import BatonPacket, BatonPayload, ProjectEvent, Task

from app.services.context_service import ContextService


@dataclass
class InMemoryContextStore:
    task: Task
    baton_packets: list[BatonPacket] = field(default_factory=list)
    events: list[ProjectEvent] = field(default_factory=list)
    context_references: dict[str, dict[str, object]] = field(default_factory=dict)
    context_reference_layers: dict[tuple[str, str], dict[str, object]] = field(
        default_factory=dict
    )
    context_bundles: list[dict[str, object]] = field(default_factory=list)

    def get_task(self, task_id: UUID) -> Task | None:
        if self.task.id == task_id:
            return self.task
        return None

    def get_latest_baton_packet(self, task_id: UUID) -> BatonPacket | None:
        packets = [packet for packet in self.baton_packets if packet.task_id == task_id]
        return packets[-1] if packets else None

    def list_project_events(self, task_id: UUID, limit: int = 50) -> list[ProjectEvent]:
        events = [event for event in self.events if event.task_id == task_id]
        return events[:limit]

    def get_latest_context_bundle(self, task_id: UUID) -> dict[str, object] | None:
        bundles = [bundle for bundle in self.context_bundles if bundle["task_id"] == task_id]
        return bundles[-1] if bundles else None

    def upsert_context_reference(
        self,
        *,
        ref_id: str,
        task_id: UUID,
        content_type: str,
        original_content: str,
        summary: str,
        retrieval_hint: str,
    ) -> dict[str, object]:
        if ref_id in self.context_references:
            return self.context_references[ref_id]

        record = {
            "ref_id": ref_id,
            "task_id": task_id,
            "content_type": content_type,
            "original_content": original_content,
            "summary": summary,
            "retrieval_hint": retrieval_hint,
            "created_at": datetime.now(timezone.utc),
        }
        self.context_references[ref_id] = record
        return record

    def get_context_reference(self, ref_id: str) -> dict[str, object] | None:
        return self.context_references.get(ref_id)

    def upsert_context_reference_layer(
        self,
        *,
        ref_id: str,
        layer: str,
        content: str,
    ) -> dict[str, object]:
        key = (ref_id, layer)
        record = self.context_reference_layers.get(key)
        if record is None:
            record = {
                "layer_id": str(uuid4()),
                "ref_id": ref_id,
                "layer": layer,
                "content": content,
                "created_at": datetime.now(timezone.utc),
            }
        else:
            record["content"] = content
        self.context_reference_layers[key] = record
        return record

    def get_context_reference_layer(
        self, *, ref_id: str, layer: str
    ) -> dict[str, object] | None:
        return self.context_reference_layers.get((ref_id, layer))

    def save_context_bundle(
        self,
        *,
        task_id: UUID,
        target_agent: str,
        target_model: str,
        token_budget: int,
        raw_estimated_tokens: int,
        optimized_estimated_tokens: int,
        token_savings_estimate: int,
        token_savings_pct: float,
        estimated_cost_raw_usd: float | None,
        estimated_cost_optimized_usd: float | None,
        estimated_cost_saved_usd: float | None,
        optimized_context: dict[str, object],
        included_refs: list[str],
    ) -> dict[str, object]:
        record = {
            "bundle_id": uuid4(),
            "task_id": task_id,
            "target_agent": target_agent,
            "target_model": target_model,
            "token_budget": token_budget,
            "raw_estimated_tokens": raw_estimated_tokens,
            "optimized_estimated_tokens": optimized_estimated_tokens,
            "token_savings_estimate": token_savings_estimate,
            "token_savings_pct": token_savings_pct,
            "estimated_cost_raw_usd": estimated_cost_raw_usd,
            "estimated_cost_optimized_usd": estimated_cost_optimized_usd,
            "estimated_cost_saved_usd": estimated_cost_saved_usd,
            "optimized_context": optimized_context,
            "included_refs": included_refs,
            "created_at": datetime.now(timezone.utc),
        }
        self.context_bundles.append(record)
        return record

    def list_recent_context_bundles(self, limit: int = 200) -> list[dict[str, object]]:
        return list(reversed(self.context_bundles))[:limit]


def _build_task(task_id: UUID | None = None) -> Task:
    now = datetime.now(timezone.utc)
    return Task(
        id=task_id or uuid4(),
        title="Ship internal context optimizer",
        status="in_progress",
        task_type="implementation",
        complexity="high",
        created_at=now,
        updated_at=now,
    )


def _build_baton(task_id: UUID, constraints: list[str]) -> BatonPacket:
    return BatonPacket(
        id=uuid4(),
        task_id=task_id,
        from_agent="planner",
        to_agent="coder",
        summary="latest handoff",
        payload=BatonPayload(
            objective="Build deterministic local context optimization",
            completed_work=["Defined architecture"],
            constraints=constraints,
            open_questions=["Need tests for resume"],
            next_best_action="Implement optimizer + retrieval references",
            relevant_artifacts=["services/orchestrator/app/context"],
        ),
        created_at=datetime.now(timezone.utc),
    )


def _build_event(task_id: UUID, *, event_type: str, event_data: dict[str, object]) -> ProjectEvent:
    return ProjectEvent(
        id=uuid4(),
        task_id=task_id,
        event_type=event_type,
        event_data=event_data,
        created_at=datetime.now(timezone.utc),
    )


def test_critical_constraints_are_preserved_verbatim() -> None:
    task = _build_task()
    critical_constraint = "DO NOT compress exact SQL schema text in active migration reviews."
    store = InMemoryContextStore(
        task=task,
        baton_packets=[_build_baton(task.id, [critical_constraint])],
    )
    service = ContextService(store)  # type: ignore[arg-type]

    bundle = service.assemble_optimized_context(
        task_id=task.id,
        target_agent="coder",
        target_model="gpt-4o-mini",
        token_budget=2_000,
    )

    constraint_sections = [
        section for section in bundle.sections if section.section_type == "constraint"
    ]
    assert constraint_sections
    assert constraint_sections[0].content == critical_constraint


def test_large_content_replaced_with_retrievable_reference() -> None:
    task = _build_task()
    huge_log = "\n".join(
        [
            "build step started",
            "FATAL: missing symbol in worker bootstrap",
            *[f"log line {idx} lorem ipsum dolor sit amet" for idx in range(700)],
        ]
    )
    store = InMemoryContextStore(
        task=task,
        baton_packets=[_build_baton(task.id, ["No proxy layer"])],
        events=[
            _build_event(
                task.id,
                event_type="tool.exec",
                event_data={"stderr": huge_log, "command": "pytest -q"},
            )
        ],
    )
    service = ContextService(store)  # type: ignore[arg-type]

    bundle = service.assemble_optimized_context(
        task_id=task.id,
        target_agent="coder",
        target_model="gpt-4o-mini",
        token_budget=1_600,
    )

    assert bundle.included_refs
    ref_id = bundle.included_refs[0]
    assert ref_id in bundle.optimized_context["rendered_prompt"]
    assert "log line 699" not in bundle.optimized_context["rendered_prompt"]

    recovered = service.retrieve_context_reference(ref_id)
    assert "FATAL: missing symbol in worker bootstrap" in recovered.original_content
    assert "log line 699 lorem ipsum dolor sit amet" in recovered.original_content


def test_error_like_stderr_is_treated_as_log_and_compressed() -> None:
    task = _build_task()
    huge_stderr = "\n".join(
        [
            "Traceback: ValueError at step 4",
            "ERROR: critical failure in pipeline",
            *[f"stderr line {idx} repetitive payload block" for idx in range(1500)],
        ]
    )
    store = InMemoryContextStore(
        task=task,
        baton_packets=[_build_baton(task.id, ["Keep hard constraints verbatim"])],
        events=[
            _build_event(
                task.id,
                event_type="tool.exec.stderr",
                event_data={"stderr": huge_stderr, "command": "pytest -q"},
            )
        ],
    )
    service = ContextService(store)  # type: ignore[arg-type]

    bundle = service.assemble_optimized_context(
        task_id=task.id,
        target_agent="coder",
        target_model="gpt-4o-mini",
        token_budget=1200,
    )

    assert bundle.included_refs
    rendered = bundle.optimized_context["rendered_prompt"]
    assert "stderr line 1499" not in rendered
    assert "ctxref_" in rendered


def test_optimized_context_stays_under_budget() -> None:
    task = _build_task()
    noisy_events = [
        _build_event(
            task.id,
            event_type=f"build.step.{index}",
            event_data={"stdout": "x" * 700, "index": index},
        )
        for index in range(25)
    ]
    store = InMemoryContextStore(
        task=task,
        baton_packets=[_build_baton(task.id, ["Keep deterministic behavior"])],
        events=noisy_events,
    )
    service = ContextService(store)  # type: ignore[arg-type]

    bundle = service.assemble_optimized_context(
        task_id=task.id,
        target_agent="coder",
        target_model="gpt-4o-mini",
        token_budget=900,
    )

    assert bundle.estimated_token_count <= bundle.token_budget
    assert bundle.raw_estimated_token_count >= bundle.estimated_token_count
    assert bundle.token_savings_estimate >= 0


def test_second_worker_can_resume_using_previous_optimized_bundle() -> None:
    task = _build_task()
    store = InMemoryContextStore(
        task=task,
        baton_packets=[_build_baton(task.id, ["Keep local-first architecture"])],
        events=[
            _build_event(
                task.id,
                event_type="routing.decision",
                event_data={"worker_role": "coder", "model_tier": "balanced"},
            )
        ],
    )
    service = ContextService(store)  # type: ignore[arg-type]

    first_bundle = service.assemble_optimized_context(
        task_id=task.id,
        target_agent="coder",
        target_model="gpt-4.1-mini",
        token_budget=1_600,
    )
    second_bundle = service.assemble_optimized_context(
        task_id=task.id,
        target_agent="reviewer",
        target_model="gpt-4.1",
        token_budget=1_600,
    )

    resume_sections = [
        section for section in second_bundle.sections if section.section_type == "prior_bundle"
    ]
    assert resume_sections
    assert str(first_bundle.bundle_id) in resume_sections[0].content
