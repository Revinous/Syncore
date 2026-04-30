from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from packages.contracts.python.models import BatonPacket, ExecutiveDigest, ProjectEvent


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
        self,
        task_id: UUID,
        events: list[ProjectEvent],
        latest_baton: BatonPacket | None = None,
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
                latest_baton=latest_baton,
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
        latest_baton: BatonPacket | None = None,
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
        what_changed = self._extract_what_changed(events or [], latest_baton)
        why_matter = self._extract_why_it_matters(events or [], risk_level)
        next_step = self._extract_next_step(latest_baton, events or [])
        return (
            f"In plain language: {headline}. "
            f"What was done: {what_changed}. "
            f"Why it matters: {why_matter}. "
            f"What happens next: {next_step}. "
            f"Signals: {top_text}. "
            f"Latest: {latest}."
        )

    def _extract_what_changed(
        self, events: list[ProjectEvent], latest_baton: BatonPacket | None
    ) -> str:
        if latest_baton is not None:
            completed_work = [item.strip() for item in latest_baton.payload.completed_work if item.strip()]
            if completed_work:
                return "; ".join(completed_work[:3])
            summary = latest_baton.summary.strip()
            if summary:
                return summary
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
                    if key == "reason":
                        return self._humanize_reason(value)
                    return value
            if str(data.get("status", "")).lower() == "blocked":
                reason = str(data.get("reason", "")).strip()
                if reason:
                    return f"it removes a blocker: {self._humanize_reason(reason)}"
                return "it unblocks delivery progress"
        if risk_level == "high":
            return "there is delivery risk, so this change reduces failure or blocker exposure"
        if risk_level == "medium":
            return "it helps keep the task moving toward completion with fewer surprises"
        return "it improves completion confidence and quality for the task"

    def _extract_next_step(
        self, latest_baton: BatonPacket | None, events: list[ProjectEvent]
    ) -> str:
        if latest_baton is not None:
            action = latest_baton.payload.next_best_action.strip()
            if action:
                return action
            questions = [q.strip() for q in latest_baton.payload.open_questions if q.strip()]
            if questions:
                return f"resolve open question: {questions[0]}"
        for event in events:
            note = str(event.event_data.get("next_step", "")).strip()
            if note:
                return note
        return "continue implementation and run verification checks"

    def _humanize_reason(self, reason: str) -> str:
        cleaned = reason.strip()
        if not cleaned:
            return "a technical risk was found"
        lowered = cleaned.lower()
        if "missing" in lowered:
            return f"there was a missing required check ({cleaned})"
        return cleaned
