from __future__ import annotations

import time
from threading import Lock
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.config import Settings

EXEMPT_PATH_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")


def create_security_middleware(settings: Settings) -> Callable:
    request_windows: dict[tuple[str, str], tuple[float, int]] = {}
    lock = Lock()

    async def security_middleware(request: Request, call_next) -> Response:
        path = request.url.path
        if any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES):
            return await call_next(request)

        if settings.api_auth_enabled:
            expected = (settings.api_auth_token or "").strip()
            provided = request.headers.get("x-api-key", "").strip()
            if not expected or provided != expected:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized: missing or invalid x-api-key"},
                )

        if settings.rate_limit_enabled:
            ip = request.client.host if request.client else "unknown"
            now = time.time()
            window_seconds = max(settings.rate_limit_window_seconds, 1)
            max_requests = max(settings.rate_limit_max_requests, 1)
            key = (ip, path)
            with lock:
                started_at, count = request_windows.get(key, (now, 0))
                if now - started_at >= window_seconds:
                    started_at, count = now, 0
                count += 1
                request_windows[key] = (started_at, count)
                if count > max_requests:
                    retry_after = max(int(window_seconds - (now - started_at)), 1)
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": (
                                "Rate limit exceeded. "
                                f"Try again in {retry_after}s."
                            )
                        },
                    )

        return await call_next(request)

    return security_middleware
