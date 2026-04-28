from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.observability import get_slo_status, render_prometheus_metrics

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
