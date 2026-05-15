from __future__ import annotations

import hashlib
import json

from services.memory import MemoryStoreProtocol


class AutonomyFailureHandler:
    def __init__(
        self,
        *,
        store: MemoryStoreProtocol,
        low_info_threshold: int,
        failure_taxonomy_v2_enabled: bool,
        latest_execute_plan,
    ) -> None:
        self._store = store
        self._low_info_threshold = low_info_threshold
        self._failure_taxonomy_v2_enabled = failure_taxonomy_v2_enabled
        self._latest_execute_plan = latest_execute_plan

    def classify_failure(
        self,
        *,
        task_id,
        stage: str,
        cycle: int,
        error: Exception,
    ) -> dict[str, object]:
        reason = str(error).strip() or f"{stage} failure"
        category = "stage_failure"
        strategy = "replan"
        retry_allowed = True
        should_replan = False
        events = self._store.list_project_events(task_id=task_id, limit=300)
        for event in reversed(events):
            event_cycle = _event_int(event.event_data.get("cycle")) or cycle
            if event_cycle != cycle:
                continue
            if event.event_type in {
                "workspace.execution.preflight.failed",
                "workspace.execution.verification.failed",
            }:
                category = str(event.event_data.get("failure_category") or category)
                strategy = str(event.event_data.get("recommended_strategy") or strategy)
                reason = str(event.event_data.get("reason") or reason)
                break
            if event.event_type == "run.failed":
                category = "provider_failure"
                strategy = "switch_model_or_provider"
                reason = str(event.event_data.get("error") or reason)
                break
        lowered = reason.lower()
        if category == "environment_failure":
            retry_allowed = False
        elif category == "provider_failure":
            retry_allowed = True
        elif category in {"policy_block", "risk_guardrail"}:
            retry_allowed = False
        elif category in {"verification_failure", "acceptance_failure"}:
            retry_allowed = False
            should_replan = True
        elif "no changes or verification commands were produced" in lowered:
            category = "no_artifact_change"
            strategy = "tighten_implementation_scope"
            retry_allowed = False
            should_replan = True
        elif "required verification commands did not pass" in lowered:
            category = "verification_failure"
            strategy = "raise_verification"
            retry_allowed = False
            should_replan = True
        elif "provider" in lowered:
            category = "provider_failure"
            strategy = "switch_model_or_provider"
            retry_allowed = True
        elif "approval" in lowered:
            category = "policy_block"
            strategy = "request_approval"
            retry_allowed = False
        plan = self._latest_execute_plan(task_id)
        signature_payload = {
            "stage": stage,
            "category": category,
            "reason": lowered[:160],
            "plan_signature": str((plan or {}).get("signature") or ""),
        }
        signature = hashlib.sha256(
            json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        return {
            "category": category,
            "strategy": strategy,
            "retry_allowed": retry_allowed if self._failure_taxonomy_v2_enabled else True,
            "should_replan": should_replan if self._failure_taxonomy_v2_enabled else False,
            "reason": reason,
            "signature": signature,
        }

    def is_low_information_failure(self, *, task_id, stage: str, failure_signature: str) -> bool:
        if not failure_signature:
            return False
        events = self._store.list_project_events(task_id=task_id, limit=200)
        count = 0
        for event in reversed(events):
            if event.event_type != "autonomy.stage.failed":
                continue
            if str(event.event_data.get("stage") or "").strip().lower() != stage:
                break
            if str(event.event_data.get("signature") or "").strip() == failure_signature:
                count += 1
            else:
                break
        return count >= (self._low_info_threshold - 1)


def _event_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
