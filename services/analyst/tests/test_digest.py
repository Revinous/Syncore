from datetime import datetime, timedelta, timezone
from uuid import uuid4

from packages.contracts.python.models import ProjectEvent
from services.analyst.digest import AnalystDigestService


def test_digest_for_no_events_is_actionable() -> None:
    service = AnalystDigestService()
    task_id = uuid4()

    digest = service.generate_digest(task_id=task_id, events=[])

    assert digest.task_id == task_id
    assert digest.total_events == 0
    assert digest.risk_level == "medium"
    assert "No project activity" in digest.headline


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
