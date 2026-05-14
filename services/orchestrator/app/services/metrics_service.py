from __future__ import annotations

from app.config import Settings
from app.observability import get_slo_status
from app.store_factory import build_memory_store


class MetricsService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._store = build_memory_store(settings)

    def get_slo_payload(self) -> dict[str, object]:
        runtime_slo = get_slo_status(
            max_http_error_rate=self._settings.slo_max_http_error_rate,
            max_http_p95_latency_ms=self._settings.slo_max_http_p95_latency_ms,
            min_run_success_rate=self._settings.slo_min_run_success_rate,
        )
        context = self.get_context_efficiency_payload(limit=200)
        autonomy = self.get_autonomy_efficiency_payload(limit=1000)
        totals = context.get("totals", {})
        savings_pct = float(totals.get("savings_pct") or 0.0)
        layering = context.get("layering_modes", {})
        layered_count = int(layering.get("layered", 0) or 0)
        fallback_count = int(layering.get("fallback_legacy", 0) or 0)
        fallback_rate = (
            (fallback_count / (fallback_count + layered_count))
            if (fallback_count + layered_count) > 0
            else 0.0
        )

        context_checks = {
            "context_savings_pct": savings_pct >= self._settings.slo_min_context_savings_pct,
            "context_layering_fallback_rate": (
                fallback_rate <= self._settings.slo_max_context_layering_fallback_rate
            ),
        }
        return {
            "status": (
                "ok"
                if runtime_slo.get("status") == "ok" and all(context_checks.values())
                else "degraded"
            ),
            "checks": runtime_slo.get("checks", {}),
            "thresholds": runtime_slo.get("thresholds", {}),
            "metrics": runtime_slo.get("metrics", {}),
            "runtime": runtime_slo,
            "context_efficiency": {
                "checks": context_checks,
                "thresholds": {
                    "min_context_savings_pct": self._settings.slo_min_context_savings_pct,
                    "max_context_layering_fallback_rate": (
                        self._settings.slo_max_context_layering_fallback_rate
                    ),
                },
                "metrics": {
                    "savings_pct": round(savings_pct, 2),
                    "fallback_rate": round(fallback_rate, 4),
                    "layering_modes": layering,
                    "bundle_count": context.get("bundle_count", 0),
                },
            },
            "autonomy_efficiency": autonomy,
        }

    def get_context_efficiency_payload(self, *, limit: int) -> dict[str, object]:
        try:
            rows = self._store.list_recent_context_bundles(limit=limit)
        except Exception:
            rows = []

        total_raw = 0
        total_optimized = 0
        total_saved = 0
        total_cost_raw = 0.0
        total_cost_optimized = 0.0
        total_cost_saved = 0.0
        cost_rows = 0
        by_model: dict[str, dict[str, object]] = {}
        layering_mode_counts: dict[str, int] = {}
        layering_profiles: dict[str, dict[str, object]] = {}
        dual_mode_count = 0
        dual_legacy_total = 0
        dual_layered_total = 0
        recent: list[dict[str, object]] = []

        for row in rows:
            model = str(row.get("target_model") or "unknown")
            raw = int(row.get("raw_estimated_tokens") or 0)
            optimized = int(row.get("optimized_estimated_tokens") or 0)
            saved = int(row.get("token_savings_estimate") or (raw - optimized))
            total_raw += raw
            total_optimized += optimized
            total_saved += saved

            cost_raw = row.get("estimated_cost_raw_usd")
            cost_opt = row.get("estimated_cost_optimized_usd")
            cost_saved = row.get("estimated_cost_saved_usd")
            if isinstance(cost_raw, (float, int)) and isinstance(cost_opt, (float, int)):
                total_cost_raw += float(cost_raw)
                total_cost_optimized += float(cost_opt)
                total_cost_saved += float(cost_saved or (float(cost_raw) - float(cost_opt)))
                cost_rows += 1

            model_bucket = by_model.setdefault(
                model,
                {
                    "bundle_count": 0,
                    "raw_tokens": 0,
                    "optimized_tokens": 0,
                    "saved_tokens": 0,
                },
            )
            model_bucket["bundle_count"] = int(model_bucket["bundle_count"]) + 1
            model_bucket["raw_tokens"] = int(model_bucket["raw_tokens"]) + raw
            model_bucket["optimized_tokens"] = int(model_bucket["optimized_tokens"]) + optimized
            model_bucket["saved_tokens"] = int(model_bucket["saved_tokens"]) + saved

            recent.append(
                {
                    "bundle_id": str(row.get("bundle_id")),
                    "task_id": str(row.get("task_id")),
                    "target_model": model,
                    "raw_estimated_tokens": raw,
                    "optimized_estimated_tokens": optimized,
                    "token_savings_estimate": saved,
                    "token_savings_pct": float(row.get("token_savings_pct") or 0.0),
                    "estimated_cost_saved_usd": row.get("estimated_cost_saved_usd"),
                    "created_at": row.get("created_at"),
                }
            )

            optimized_context = row.get("optimized_context")
            if isinstance(optimized_context, dict):
                self._accumulate_layering_data(
                    optimized_context=optimized_context,
                    model_profile_buckets=layering_profiles,
                    layering_mode_counts=layering_mode_counts,
                    dual_totals={
                        "count": dual_mode_count,
                        "legacy": dual_legacy_total,
                        "layered": dual_layered_total,
                    },
                )
                comparison = optimized_context.get("layering_comparison")
                if isinstance(comparison, dict):
                    legacy = comparison.get("legacy_estimated_tokens")
                    layered = comparison.get("layered_estimated_tokens")
                    if isinstance(legacy, int) and isinstance(layered, int):
                        dual_mode_count += 1
                        dual_legacy_total += legacy
                        dual_layered_total += layered

        savings_pct = round((total_saved / total_raw) * 100.0, 2) if total_raw > 0 else 0.0
        payload: dict[str, object] = {
            "bundle_count": len(rows),
            "totals": {
                "raw_tokens": total_raw,
                "optimized_tokens": total_optimized,
                "saved_tokens": total_saved,
                "savings_pct": savings_pct,
            },
            "by_model": by_model,
            "layering_modes": layering_mode_counts,
            "layering_profiles": layering_profiles,
            "recent_bundles": recent[:50],
        }
        if cost_rows > 0:
            payload["cost_totals"] = {
                "raw_usd": round(total_cost_raw, 8),
                "optimized_usd": round(total_cost_optimized, 8),
                "saved_usd": round(total_cost_saved, 8),
            }
        if dual_mode_count > 0:
            dual_saved = dual_legacy_total - dual_layered_total
            dual_pct = (
                round((dual_saved / dual_legacy_total) * 100.0, 2) if dual_legacy_total > 0 else 0.0
            )
            payload["layering_comparison"] = {
                "bundle_count": dual_mode_count,
                "legacy_tokens": dual_legacy_total,
                "layered_tokens": dual_layered_total,
                "saved_tokens": dual_saved,
                "savings_pct": dual_pct,
            }
        return payload

    def _accumulate_layering_data(
        self,
        *,
        optimized_context: dict[str, object],
        model_profile_buckets: dict[str, dict[str, object]],
        layering_mode_counts: dict[str, int],
        dual_totals: dict[str, int],
    ) -> None:
        layering_mode = str(optimized_context.get("layering_mode") or "unknown")
        layering_mode_counts[layering_mode] = layering_mode_counts.get(layering_mode, 0) + 1
        rollout_profile = str(optimized_context.get("rollout_profile") or "").strip()
        if rollout_profile:
            profile_bucket = model_profile_buckets.setdefault(
                rollout_profile,
                {
                    "bundle_count": 0,
                    "layering_modes": {},
                    "legacy_tokens": 0,
                    "layered_tokens": 0,
                    "comparison_count": 0,
                },
            )
            profile_bucket["bundle_count"] = int(profile_bucket["bundle_count"]) + 1
            modes = profile_bucket["layering_modes"]
            if isinstance(modes, dict):
                modes[layering_mode] = int(modes.get(layering_mode, 0)) + 1
            comparison = optimized_context.get("layering_comparison")
            if isinstance(comparison, dict):
                legacy = comparison.get("legacy_estimated_tokens")
                layered = comparison.get("layered_estimated_tokens")
                if isinstance(legacy, int) and isinstance(layered, int):
                    profile_bucket["legacy_tokens"] = int(profile_bucket["legacy_tokens"]) + legacy
                    profile_bucket["layered_tokens"] = (
                        int(profile_bucket["layered_tokens"]) + layered
                    )
                    profile_bucket["comparison_count"] = int(profile_bucket["comparison_count"]) + 1

    def get_autonomy_efficiency_payload(self, *, limit: int) -> dict[str, object]:
        try:
            events = self._store.list_project_events(task_id=None, limit=limit)
            tasks = self._store.list_tasks(limit=limit)
        except Exception:
            events = []
            tasks = []

        counts = {
            "retry_scheduled": 0,
            "replan_started": 0,
            "provider_switches": 0,
            "low_information_stops": 0,
            "execute_plans_created": 0,
            "execute_plans_reused": 0,
        }
        completed_tasks = sum(1 for task in tasks if task.status == "completed")
        tasks_with_execute_success: set[str] = set()
        first_pass_tasks: set[str] = set()
        retry_tasks: set[str] = set()
        for event in events:
            if event.event_type == "autonomy.retry.scheduled":
                counts["retry_scheduled"] += 1
                retry_tasks.add(str(event.task_id))
            elif (
                event.event_type == "autonomy.cycle.started"
                and str(event.event_data.get("mode") or "") == "replan"
            ):
                counts["replan_started"] += 1
            elif event.event_type == "model.switch.completed":
                from_provider = str(event.event_data.get("from_provider") or "").strip().lower()
                to_provider = str(event.event_data.get("to_provider") or "").strip().lower()
                if from_provider and to_provider and from_provider != to_provider:
                    counts["provider_switches"] += 1
            elif event.event_type == "autonomy.stopped.low_information_gain":
                counts["low_information_stops"] += 1
            elif event.event_type == "autonomy.execute_plan.created":
                counts["execute_plans_created"] += 1
            elif event.event_type == "autonomy.execute_plan.reused":
                counts["execute_plans_reused"] += 1
            elif event.event_type == "workspace.execution.completed":
                tasks_with_execute_success.add(str(event.task_id))
        for task_id in tasks_with_execute_success:
            if task_id not in retry_tasks:
                first_pass_tasks.add(task_id)

        completed_with_execute = len(tasks_with_execute_success)
        return {
            "status": "ok",
            "counts": counts,
            "completed_tasks": completed_tasks,
            "completed_with_execute": completed_with_execute,
            "first_pass_execute_rate": round((len(first_pass_tasks) / completed_with_execute), 4)
            if completed_with_execute
            else 0.0,
            "retry_per_completed_task": round((counts["retry_scheduled"] / completed_tasks), 4)
            if completed_tasks
            else 0.0,
        }
