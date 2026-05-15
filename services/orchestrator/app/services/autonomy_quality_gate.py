from __future__ import annotations

import hashlib
import json

from packages.contracts.python.models import ProjectEventCreate, Task
from services.memory import MemoryStoreProtocol


class AutonomyQualityGate:
    def __init__(
        self,
        *,
        store: MemoryStoreProtocol,
        review_pass_keyword: str,
        plan_min_chars: int,
        execute_min_chars: int,
        review_min_chars: int,
        low_info_threshold: int,
        string_list,
        latest_execute_plan,
        selected_candidate_state,
        latest_event,
    ) -> None:
        self._store = store
        self._review_pass_keyword = review_pass_keyword
        self._plan_min_chars = plan_min_chars
        self._execute_min_chars = execute_min_chars
        self._review_min_chars = review_min_chars
        self._low_info_threshold = low_info_threshold
        self._string_list = string_list
        self._latest_execute_plan = latest_execute_plan
        self._selected_candidate_state = selected_candidate_state
        self._latest_event = latest_event

    def stage_quality_gate(
        self,
        *,
        stage: str,
        output_text: str,
        strategy: str,
        enforce_sdlc: bool,
        sdlc_checklist_items: tuple[str, ...],
        missing_sdlc_topics,
        extract_sdlc_checklist_status,
    ) -> dict[str, object]:
        text = (output_text or "").strip()
        minimum = self._execute_min_chars
        if stage == "plan":
            minimum = self._plan_min_chars
        elif stage == "review":
            minimum = self._review_min_chars

        reasons: list[str] = []
        score = 100
        if len(text) < minimum:
            reasons.append(f"Too short ({len(text)} < {minimum}).")
            score -= 45
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if stage == "plan":
            has_step_shape = any(
                line.startswith(("-", "*")) or line[:2].isdigit() for line in lines
            )
            if not has_step_shape:
                reasons.append("Plan missing explicit step list.")
                score -= 20
            if "risk" not in text.lower():
                reasons.append("Plan missing risk notes.")
                score -= 10
            if enforce_sdlc:
                missing = missing_sdlc_topics(text)
                if missing:
                    reasons.append(f"Plan missing SDLC coverage for: {', '.join(missing)}.")
                    score -= min(10 + (len(missing) * 5), 35)
        if stage == "execute":
            has_actionable = (
                ("```" in text)
                or ("$ " in text)
                or ("def " in text)
                or ("class " in text)
            )
            if not has_actionable:
                reasons.append("Execute output missing concrete code/command artifacts.")
                score -= 25
            if enforce_sdlc and "test" not in text.lower() and "verify" not in text.lower():
                reasons.append("Execute output missing test/verification evidence.")
                score -= 20
        if stage == "review":
            lowered = text.lower()
            if "pass" not in lowered and "fail" not in lowered:
                reasons.append("Review missing explicit pass/fail.")
                score -= 20
            if "risk" not in lowered:
                reasons.append("Review missing risk analysis.")
                score -= 10
            if "meaningful_change=true" not in lowered and "meaningful_change=false" not in lowered:
                reasons.append("Review missing meaningful_change marker.")
                score -= 10
            if self._review_pass_keyword and self._review_pass_keyword.upper() not in text.upper():
                reasons.append(f"Missing review pass keyword '{self._review_pass_keyword}'.")
                score -= 40
            if enforce_sdlc:
                checklist_status = extract_sdlc_checklist_status(text)
                missing_checks = [
                    item
                    for item in sdlc_checklist_items
                    if not checklist_status.get(item, False)
                ]
                if missing_checks:
                    reasons.append(f"Review checklist incomplete: {', '.join(missing_checks)}.")
                    score -= min(12 + (len(missing_checks) * 4), 45)
        if strategy == "raise_verification":
            if "test" not in text.lower() and "verify" not in text.lower():
                reasons.append("Verification-focused strategy requires tests/verification notes.")
                score -= 15

        score = max(score, 0)
        return {"passed": score >= 70, "score": score, "reasons": reasons}

    def record_meaningful_change_assessment(
        self,
        *,
        task: Task,
        prefs: dict[str, str],
        review_output: str,
        parse_uuid,
    ) -> None:
        lowered = review_output.lower()
        marker = "unknown"
        if "meaningful_change=true" in lowered:
            marker = "true"
        elif "meaningful_change=false" in lowered:
            marker = "false"
        evidence = "review_output"
        if marker == "unknown":
            parent_id = parse_uuid(prefs.get("parent_task_id"))
            if parent_id is not None:
                candidate_state = self._selected_candidate_state(parent_id)
                if candidate_state.get("status") == "ready":
                    marker = "true"
                    evidence = "selected_candidate"
        self._store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.meaningful_change.assessed",
                event_data={"meaningful_change": marker, "evidence": evidence},
            )
        )

    def quality_failure_signature(self, *, task_id, stage: str, reason: str) -> str:
        plan = self._latest_execute_plan(task_id)
        payload = {
            "stage": stage,
            "reason": reason.lower()[:160],
            "plan_signature": str((plan or {}).get("signature") or ""),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]

    def is_low_information_quality_failure(self, *, task_id, stage: str, signature: str) -> bool:
        if not signature:
            return False
        events = self._store.list_project_events(task_id=task_id, limit=200)
        count = 0
        for event in reversed(events):
            if event.event_type != "autonomy.quality.failed":
                continue
            if str(event.event_data.get("stage") or "").strip().lower() != stage:
                break
            if str(event.event_data.get("signature") or "").strip() == signature:
                count += 1
            else:
                break
        return count >= (self._low_info_threshold - 1)
