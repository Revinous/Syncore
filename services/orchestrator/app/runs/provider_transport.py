from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Iterator
from urllib import error, request


@dataclass
class ProviderRequestError(RuntimeError):
    provider: str
    message: str
    status_code: int | None = None
    body: str | None = None

    def __post_init__(self) -> None:
        super().__init__(self.message)


class ProviderHttpTransport:
    def __init__(self, *, provider: str, timeout_seconds: int = 60, max_retries: int = 2) -> None:
        self._provider = provider
        self._timeout_seconds = timeout_seconds
        self._max_retries = max(max_retries, 0)

    def request_json(self, req: request.Request) -> dict[str, object]:
        response = self._perform(req)
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError as exc:
            raise ProviderRequestError(
                provider=self._provider,
                message=f"{self._provider} provider returned invalid JSON",
            ) from exc
        if not isinstance(parsed, dict):
            raise ProviderRequestError(
                provider=self._provider,
                message=f"{self._provider} response payload is not an object",
            )
        return parsed

    def stream_sse_json(
        self,
        req: request.Request,
        on_event: Callable[[dict[str, object]], str | None],
    ) -> Iterator[str]:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                with request.urlopen(req, timeout=self._timeout_seconds) as response:  # nosec B310
                    for raw_line in response:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line or not line.startswith("data: "):
                            continue
                        payload_line = line[6:]
                        if payload_line == "[DONE]":
                            return
                        try:
                            event = json.loads(payload_line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(event, dict):
                            continue
                        chunk = on_event(event)
                        if chunk:
                            yield chunk
                return
            except error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code >= 500 and attempt < self._max_retries:
                    time.sleep(0.35 * (attempt + 1))
                    continue
                raise ProviderRequestError(
                    provider=self._provider,
                    status_code=exc.code,
                    body=body,
                    message=f"{self._provider} provider HTTP {exc.code}: {body}",
                ) from exc
            except error.URLError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(0.35 * (attempt + 1))
                    continue
                raise ProviderRequestError(
                    provider=self._provider,
                    message=f"{self._provider} provider connection failed: {exc.reason}",
                ) from exc
        if last_error is not None:
            raise ProviderRequestError(
                provider=self._provider,
                message=f"{self._provider} provider request failed: {last_error}",
            )

    def raw_text(self, req: request.Request) -> str:
        return self._perform(req)

    def _perform(self, req: request.Request) -> str:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                with request.urlopen(req, timeout=self._timeout_seconds) as response:  # nosec B310
                    return response.read().decode("utf-8", errors="replace")
            except error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code >= 500 and attempt < self._max_retries:
                    time.sleep(0.35 * (attempt + 1))
                    continue
                raise ProviderRequestError(
                    provider=self._provider,
                    status_code=exc.code,
                    body=body,
                    message=f"{self._provider} provider HTTP {exc.code}: {body}",
                ) from exc
            except error.URLError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(0.35 * (attempt + 1))
                    continue
                raise ProviderRequestError(
                    provider=self._provider,
                    message=f"{self._provider} provider connection failed: {exc.reason}",
                ) from exc
        if last_error is not None:
            raise ProviderRequestError(
                provider=self._provider,
                message=f"{self._provider} provider request failed: {last_error}",
            )
        raise ProviderRequestError(
            provider=self._provider,
            message=f"{self._provider} provider request failed",
        )
