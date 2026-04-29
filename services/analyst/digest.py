from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from packages.contracts.python.models import ExecutiveDigest, ProjectEvent


class AnalystDigestService:
    _EXCLUDED_PREFIXES = (
        "analyst.",
        "autonomy.",
        "routing.",
        "context.",
        "memory.lookup",
        "model.switch.",
    )

    def generate_digest(
        self, task_id: UUID, events: list[ProjectEvent]
    ) -> ExecutiveDigest:
        meaningful_events = [
            event
            for event in events
            if not self._is_excluded_event(event.event_type)
        ]
        ordered_events = sorted(
            meaningful_events, key=lambda event: event.created_at, reverse=True
        )
        event_breakdown = dict(Counter(event.event_type for event in ordered_events))

        headline = self._build_headline(ordered_events)
        highlights = self._build_highlights(ordered_events)
        risk_level = self._assess_risk(ordered_events)
        summary = self._build_summary(
            total_events=len(ordered_events),
            risk_level=risk_level,
            event_breakdown=event_breakdown,
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
            eli5_summary=self._build_eli5_summary(
                total_events=len(ordered_events),
                risk_level=risk_level,
                headline=headline,
                event_breakdown=event_breakdown,
                highlights=highlights,
                events=ordered_events,
            ),
        )

    def _is_excluded_event(self, event_type: str) -> bool:
        normalized = event_type.strip().lower()
        return normalized.startswith(self._EXCLUDED_PREFIXES)

    def _build_headline(self, events: list[ProjectEvent]) -> str:
        if not events:
            return "No project activity recorded yet"

        newest_event = events[0]
        return f"Latest milestone: {newest_event.event_type}"

    def _build_summary(
        self, total_events: int, risk_level: str, event_breakdown: dict[str, int]
    ) -> str:
        if total_events == 0:
            return "No events available. The team can start tracking execution to enable reporting."

        top_event = "unknown"
        top_count = 0
        if event_breakdown:
            top_event, top_count = max(
                event_breakdown.items(),
                key=lambda item: item[1],
            )

        return (
            f"Observed {total_events} tracked events across the current task stream. "
            f"Most frequent signal: {top_event} ({top_count}). "
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

    def _build_eli5_summary(
        self,
        *,
        total_events: int,
        risk_level: str,
        headline: str,
        event_breakdown: dict[str, int],
        highlights: list[str],
        events: list[ProjectEvent] | None = None,
    ) -> str:
        if total_events == 0:
            return (
                "Nothing has happened yet. Start one small step, log it, and I can explain progress simply."
            )
        top_events = sorted(
            event_breakdown.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:2]
        top_text = ", ".join(f"{name} ({count})" for name, count in top_events) or "no dominant signals"
        latest = highlights[0] if highlights else "no latest highlight"
        what_changed = self._extract_what_changed(events or [])
        why_matter = self._extract_why_it_matters(events or [], risk_level)
        return (
            f"Here is the simple version: {headline}. "
            f"What changed: {what_changed}. "
            f"Why it matters: {why_matter}. "
            f"We saw {total_events} updates. "
            f"Main signals were {top_text}. "
            f"Most recent update: {latest}."
        )

    def _extract_what_changed(self, events: list[ProjectEvent]) -> str:
        for event in events:
            data = event.event_data
            for key in ("change", "feature", "functionality", "summary", "title", "notes"):
                value = str(data.get(key, "")).strip()
                if value:
                    return value
            if event.event_type in {"run.completed", "review.completed"}:
                output = str(data.get("output_summary", "")).strip()
                if output:
                    return output
        if events:
            return f"latest activity was {events[0].event_type}"
        return "no implementation change logged yet"

    def _extract_why_it_matters(self, events: list[ProjectEvent], risk_level: str) -> str:
        for event in events:
            data = event.event_data
            for key in ("impact", "reason", "user_impact", "business_impact"):
                value = str(data.get(key, "")).strip()
                if value:
                    return value
            if str(data.get("status", "")).lower() == "blocked":
                reason = str(data.get("reason", "")).strip()
                if reason:
                    return f"it removes a blocker: {reason}"
                return "it unblocks delivery progress"
        if risk_level == "high":
            return "there is delivery risk, so this change reduces failure or blocker exposure"
        if risk_level == "medium":
            return "it helps keep the task moving toward completion with fewer surprises"
        return "it improves completion confidence and quality for the task"
