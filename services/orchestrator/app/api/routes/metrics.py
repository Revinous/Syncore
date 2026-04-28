from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.observability import render_prometheus_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> PlainTextResponse:
    return PlainTextResponse(
        content=render_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
