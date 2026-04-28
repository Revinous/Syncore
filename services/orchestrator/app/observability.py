import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import Request, Response

_metrics_lock = threading.Lock()
_request_count = 0
_request_error_count = 0
_request_latency_ms_sum = 0.0
_request_latency_ms_max = 0.0


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")


def log_event(event: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    logging.getLogger("orchestrator").info(json.dumps(payload, default=str))


async def request_observability_middleware(request: Request, call_next) -> Response:
    request_id = request.headers.get("x-request-id", str(uuid4()))
    request.state.request_id = request_id

    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    response.headers["x-request-id"] = request_id
    log_event(
        "http.request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    _record_metrics(response.status_code, duration_ms)
    return response


def _record_metrics(status_code: int, duration_ms: float) -> None:
    global _request_count, _request_error_count, _request_latency_ms_sum, _request_latency_ms_max
    with _metrics_lock:
        _request_count += 1
        if status_code >= 500:
            _request_error_count += 1
        _request_latency_ms_sum += duration_ms
        _request_latency_ms_max = max(_request_latency_ms_max, duration_ms)


def get_metrics_snapshot() -> dict[str, float | int]:
    with _metrics_lock:
        count = _request_count
        errors = _request_error_count
        avg = (_request_latency_ms_sum / count) if count else 0.0
        return {
            "http_requests_total": count,
            "http_request_errors_total": errors,
            "http_request_error_rate": (errors / count) if count else 0.0,
            "http_request_latency_ms_avg": avg,
            "http_request_latency_ms_max": _request_latency_ms_max,
        }


def render_prometheus_metrics() -> str:
    snapshot = get_metrics_snapshot()
    lines = [
        "# HELP syncore_http_requests_total Total HTTP requests processed.",
        "# TYPE syncore_http_requests_total counter",
        f"syncore_http_requests_total {snapshot['http_requests_total']}",
        "# HELP syncore_http_request_errors_total Total HTTP 5xx responses.",
        "# TYPE syncore_http_request_errors_total counter",
        f"syncore_http_request_errors_total {snapshot['http_request_errors_total']}",
        "# HELP syncore_http_request_error_rate Fraction of requests returning 5xx.",
        "# TYPE syncore_http_request_error_rate gauge",
        f"syncore_http_request_error_rate {snapshot['http_request_error_rate']}",
        "# HELP syncore_http_request_latency_ms_avg Average request latency in milliseconds.",
        "# TYPE syncore_http_request_latency_ms_avg gauge",
        f"syncore_http_request_latency_ms_avg {snapshot['http_request_latency_ms_avg']}",
        "# HELP syncore_http_request_latency_ms_max Maximum request latency in milliseconds.",
        "# TYPE syncore_http_request_latency_ms_max gauge",
        f"syncore_http_request_latency_ms_max {snapshot['http_request_latency_ms_max']}",
    ]
    return "\n".join(lines) + "\n"
