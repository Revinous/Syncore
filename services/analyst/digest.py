from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from packages.contracts.python.models import ExecutiveDigest, ProjectEvent


class AnalystDigestService:
    def generate_digest(
        self, task_id: UUID, events: list[ProjectEvent]
    ) -> ExecutiveDigest:
        ordered_events = sorted(
            events, key=lambda event: event.created_at, reverse=True
        )
        event_breakdown = dict(Counter(event.event_type for event in ordered_events))

        headline = self._build_headline(ordered_events)
        highlights = self._build_highlights(ordered_events)
        risk_level = self._assess_risk(ordered_events)
        summary = self._build_summary(
            total_events=len(ordered_events), risk_level=risk_level
        )

        return ExecutiveDigest(
            task_id=task_id,
            generated_at=datetime.now(timezone.utc),
            headline=headline,
            summary=summary,
            highlights=highlights,
            event_breakdown=event_breakdown,
            risk_level=risk_level,
            total_events=len(ordered_events),
        )

    def _build_headline(self, events: list[ProjectEvent]) -> str:
        if not events:
            return "No project activity recorded yet"

        newest_event = events[0]
        return f"Latest milestone: {newest_event.event_type}"

    def _build_summary(self, total_events: int, risk_level: str) -> str:
        if total_events == 0:
            return "No events available. The team can start tracking execution to enable reporting."

        return (
            f"Observed {total_events} tracked events across the current task stream. "
            f"Current delivery risk is assessed as {risk_level}."
        )

    def _build_highlights(self, events: list[ProjectEvent]) -> list[str]:
        highlights: list[str] = []

        for event in events[:3]:
            title = event.event_data.get("title")
            status = event.event_data.get("status")
            timestamp = event.created_at.isoformat()
            details: list[str] = [event.event_type]
            if title:
                details.append(f"title={title}")
            if status:
                details.append(f"status={status}")
            highlights.append(f"[{timestamp}] " + "; ".join(details))

        if not highlights:
            highlights.append("No highlights available.")

        return highlights

    def _assess_risk(self, events: list[ProjectEvent]) -> str:
        if not events:
            return "medium"

        for event in events:
            normalized_type = event.event_type.lower()
            status = str(event.event_data.get("status", "")).lower()
            if any(
                keyword in normalized_type for keyword in ["blocked", "failed", "error"]
            ):
                return "high"
            if status in {"blocked", "failed", "error"}:
                return "high"

        for event in events:
            normalized_type = event.event_type.lower()
            status = str(event.event_data.get("status", "")).lower()
            if "review" in normalized_type or status in {"in_progress", "review"}:
                return "medium"

        return "low"
