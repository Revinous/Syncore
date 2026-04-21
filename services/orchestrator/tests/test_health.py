from fastapi.testclient import TestClient

from app.api.routes import health as health_route
from app.main import create_app


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "orchestrator"


def test_services_health_endpoint_reports_ok(monkeypatch) -> None:
    client = TestClient(create_app())

    monkeypatch.setattr(health_route, "probe_postgres", lambda _: ("ok", "reachable"))
    monkeypatch.setattr(health_route, "probe_redis", lambda _: ("ok", "reachable"))

    response = client.get("/health/services")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert {dependency["name"] for dependency in payload["dependencies"]} == {
        "postgres",
        "redis",
    }


def test_services_health_endpoint_reports_degraded(monkeypatch) -> None:
    client = TestClient(create_app())

    monkeypatch.setattr(health_route, "probe_postgres", lambda _: ("unavailable", "timeout"))
    monkeypatch.setattr(health_route, "probe_redis", lambda _: ("ok", "reachable"))

    response = client.get("/health/services")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    postgres_dependency = next(
        dependency for dependency in payload["dependencies"] if dependency["name"] == "postgres"
    )
    assert postgres_dependency["status"] == "unavailable"
