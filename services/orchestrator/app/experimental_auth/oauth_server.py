from __future__ import annotations

import contextlib
import queue
import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass(frozen=True)
class OAuthCallbackResult:
    code: str | None
    state: str | None
    error: str | None
    error_description: str | None


class OAuthCallbackServer:
    def __init__(self, port: int) -> None:
        self._port = port
        self._results: queue.Queue[OAuthCallbackResult] = queue.Queue(maxsize=1)
        self._server = _ReusableThreadingHTTPServer(("127.0.0.1", port), self._build_handler())
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with contextlib.suppress(Exception):
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def wait_for_callback(self, timeout_seconds: float) -> OAuthCallbackResult:
        return self._results.get(timeout=timeout_seconds)

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        results = self._results

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path.startswith("/auth/callback"):
                    self._handle_callback()
                    return
                if self.path.startswith("/success"):
                    self._write_html(
                        200,
                        (
                            "<html><body><h1>Syncore Codex auth complete</h1>"
                            "<p>You can return to the terminal.</p></body></html>"
                        ),
                    )
                    return
                self.send_error(404)

            def log_message(self, format: str, *args) -> None:  # noqa: A003
                return

            def _handle_callback(self) -> None:
                from urllib.parse import parse_qs, urlparse

                query = parse_qs(urlparse(self.path).query)
                result = OAuthCallbackResult(
                    code=_first(query.get("code")),
                    state=_first(query.get("state")),
                    error=_first(query.get("error")),
                    error_description=_first(query.get("error_description")),
                )
                with contextlib.suppress(queue.Full):
                    results.put_nowait(result)
                if result.error:
                    self._write_html(
                        400,
                        (
                            "<html><body><h1>Syncore Codex auth failed</h1>"
                            f"<p>{result.error}</p></body></html>"
                        ),
                    )
                    return
                self.send_response(302)
                self.send_header("Location", "/success")
                self.end_headers()

            def _write_html(self, status: int, body: str) -> None:
                payload = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return Handler


def _first(values: list[str] | None) -> str | None:
    if not values:
        return None
    value = values[0].strip()
    return value or None


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def find_available_callback_port(preferred_port: int, attempts: int = 20) -> int:
    for offset in range(attempts):
        candidate = preferred_port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return candidate
    raise OSError(f"No local callback port available near {preferred_port}.")
