import pytest
from fastapi.testclient import TestClient

from app.api.routes import health as health_route
from app.config import get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "orchestrator"


def test_services_health_endpoint_reports_ok(monkeypatch) -> None:
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "postgres")
    monkeypatch.setenv("REDIS_REQUIRED", "true")
    get_settings.cache_clear()
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
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "postgres")
    monkeypatch.setenv("REDIS_REQUIRED", "true")
    get_settings.cache_clear()
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


def test_services_health_endpoint_supports_sqlite_without_redis(monkeypatch) -> None:
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("SQLITE_DB_PATH", ".syncore/health_test.db")
    get_settings.cache_clear()
    client = TestClient(create_app())

    monkeypatch.setattr(health_route, "probe_sqlite", lambda _: ("ok", "reachable"))

    response = client.get("/health/services")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    names = {dependency["name"] for dependency in payload["dependencies"]}
    assert names == {"sqlite", "redis"}
    redis_dependency = next(
        dependency for dependency in payload["dependencies"] if dependency["name"] == "redis"
    )
    assert redis_dependency["detail"] == "disabled (REDIS_REQUIRED=false)"
