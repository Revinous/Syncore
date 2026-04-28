from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.observability import get_slo_status, render_prometheus_metrics
from app.store_factory import build_memory_store

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> PlainTextResponse:
    return PlainTextResponse(
        content=render_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/metrics/slo")
def get_metrics_slo(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return get_slo_status(
        max_http_error_rate=settings.slo_max_http_error_rate,
        max_http_p95_latency_ms=settings.slo_max_http_p95_latency_ms,
        min_run_success_rate=settings.slo_min_run_success_rate,
    )


@router.get("/metrics/context-efficiency")
def get_context_efficiency_metrics(
    limit: int = 200,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    store = build_memory_store(settings)
    rows = store.list_recent_context_bundles(limit=limit)

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
            layering_mode = str(optimized_context.get("layering_mode") or "unknown")
            layering_mode_counts[layering_mode] = layering_mode_counts.get(layering_mode, 0) + 1
            rollout_profile = str(optimized_context.get("rollout_profile") or "").strip()
            if rollout_profile:
                profile_bucket = layering_profiles.setdefault(
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
                    dual_mode_count += 1
                    dual_legacy_total += legacy
                    dual_layered_total += layered
                    if rollout_profile:
                        profile_bucket = layering_profiles[rollout_profile]
                        profile_bucket["legacy_tokens"] = (
                            int(profile_bucket["legacy_tokens"]) + legacy
                        )
                        profile_bucket["layered_tokens"] = (
                            int(profile_bucket["layered_tokens"]) + layered
                        )
                        profile_bucket["comparison_count"] = int(
                            profile_bucket["comparison_count"]
                        ) + 1

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
            round((dual_saved / dual_legacy_total) * 100.0, 2)
            if dual_legacy_total > 0
            else 0.0
        )
        payload["layering_comparison"] = {
            "bundle_count": dual_mode_count,
            "legacy_tokens": dual_legacy_total,
            "layered_tokens": dual_layered_total,
            "saved_tokens": dual_saved,
            "savings_pct": dual_pct,
        }
    return payload
