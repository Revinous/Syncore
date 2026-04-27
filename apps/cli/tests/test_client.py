from __future__ import annotations

import httpx

from syncore_cli.client import SyncoreApiClient


class DummyResponse:
    def __init__(self) -> None:
        self.status_code = 200
        self.reason_phrase = "OK"
        self.headers = {"content-type": "application/json"}

    def json(self):
        return {"status": "ok"}


def test_client_builds_correct_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_request(method: str, url: str, json=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        return DummyResponse()

    monkeypatch.setattr(httpx, "request", fake_request)
    client = SyncoreApiClient("http://localhost:8000")
    result = client.health()

    assert captured["method"] == "GET"
    assert captured["url"] == "http://localhost:8000/health"
    assert result["status"] == "ok"
