from datetime import datetime, timedelta, timezone
from uuid import uuid4

from packages.contracts.python.models import BatonPacket, BatonPayload, ProjectEvent
from services.analyst.digest import AnalystDigestService


def test_digest_for_no_events_is_actionable() -> None:
    service = AnalystDigestService()
    task_id = uuid4()

    digest = service.generate_digest(task_id=task_id, events=[])

    assert digest.task_id == task_id
    assert digest.total_events == 0
    assert digest.risk_level == "medium"
    assert "No project activity" in digest.headline
    assert "simple version" in digest.eli5_summary or "Nothing has happened yet" in digest.eli5_summary


def test_digest_includes_breakdown_and_highlights() -> None:
    service = AnalystDigestService()
    task_id = uuid4()
    now = datetime.now(timezone.utc)
    events = [
        ProjectEvent(
            id=uuid4(),
            task_id=task_id,
            event_type="task.updated",
            event_data={"title": "API wiring", "status": "in_progress"},
            created_at=now,
        ),
        ProjectEvent(
            id=uuid4(),
            task_id=task_id,
            event_type="task.created",
            event_data={"title": "Bootstrap"},
            created_at=now - timedelta(minutes=5),
        ),
    ]

    digest = service.generate_digest(task_id=task_id, events=events)

    assert digest.event_breakdown["task.updated"] == 1
    assert digest.event_breakdown["task.created"] == 1
    assert len(digest.highlights) >= 2
    assert "Latest milestone" in digest.headline
    assert "In plain language" in digest.eli5_summary


def test_digest_marks_high_risk_for_blocked_signals() -> None:
    service = AnalystDigestService()
    task_id = uuid4()
    now = datetime.now(timezone.utc)
    events = [
        ProjectEvent(
            id=uuid4(),
            task_id=task_id,
            event_type="task.blocked",
            event_data={"status": "blocked"},
            created_at=now,
        )
    ]

    digest = service.generate_digest(task_id=task_id, events=events)

    assert digest.risk_level == "high"


def test_digest_eli5_explains_functionality_and_impact() -> None:
    service = AnalystDigestService()
    task_id = uuid4()
    now = datetime.now(timezone.utc)
    events = [
        ProjectEvent(
            id=uuid4(),
            task_id=task_id,
            event_type="implementation.completed",
            event_data={
                "change": "Added OAuth callback state validation",
                "impact": "prevents CSRF in login flow",
                "status": "completed",
            },
            created_at=now,
        ),
        ProjectEvent(
            id=uuid4(),
            task_id=task_id,
            event_type="analyst.digest.generated",
            event_data={},
            created_at=now,
        ),
    ]

    digest = service.generate_digest(task_id=task_id, events=events)

    assert "What was done: Added OAuth callback state validation" in digest.eli5_summary
    assert "Why it matters: prevents CSRF in login flow" in digest.eli5_summary


def test_digest_eli5_uses_repo_specific_baton_artifact_context() -> None:
    service = AnalystDigestService()
    task_id = uuid4()
    now = datetime.now(timezone.utc)
    baton = BatonPacket(
        id=uuid4(),
        task_id=task_id,
        from_agent="coder",
        to_agent="analyst",
        summary="Workspace implementation batch completed",
        payload=BatonPayload(
            objective="Add a repo-specific Syncore contract",
            completed_work=["Updated syncore.yaml"],
            constraints=[],
            open_questions=[],
            next_best_action="Run the repo's verification checks for the changed files.",
            relevant_artifacts=["syncore.yaml"],
        ),
        created_at=now,
    )
    events = [
        ProjectEvent(
            id=uuid4(),
            task_id=task_id,
            event_type="workspace.execution.completed",
            event_data={"status": "completed"},
            created_at=now,
        )
    ]

    digest = service.generate_digest(task_id=task_id, events=events, latest_baton=baton)

    assert "What was done: Updated syncore.yaml" in digest.eli5_summary
    assert "repo-specific commands and safety rules" in digest.eli5_summary
    assert "rescan the workspace" in digest.eli5_summary
