from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.observability import render_prometheus_metrics
from app.services.metrics_service import MetricsService

router = APIRouter(tags=["metrics"])


def get_metrics_service(settings: Settings = Depends(get_settings)) -> MetricsService:
    return MetricsService(settings)


@router.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> PlainTextResponse:
    return PlainTextResponse(
        content=render_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/metrics/slo")
def get_metrics_slo(service: MetricsService = Depends(get_metrics_service)) -> dict[str, object]:
    return service.get_slo_payload()


@router.get("/metrics/context-efficiency")
def get_context_efficiency_metrics(
    limit: int = 200,
    service: MetricsService = Depends(get_metrics_service),
) -> dict[str, object]:
    return service.get_context_efficiency_payload(limit=limit)


@router.get("/metrics/autonomy-efficiency")
def get_autonomy_efficiency_metrics(
    limit: int = 1000,
    service: MetricsService = Depends(get_metrics_service),
) -> dict[str, object]:
    return service.get_autonomy_efficiency_payload(limit=limit)
