from fastapi.testclient import TestClient

from app.main import create_app


def test_request_id_is_generated_when_missing() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers.get("x-request-id") is not None


def test_request_id_header_is_preserved() -> None:
    client = TestClient(create_app())

    response = client.get("/health", headers={"x-request-id": "custom-request-id"})

    assert response.status_code == 200
    assert response.headers.get("x-request-id") == "custom-request-id"


def test_metrics_endpoint_exposes_prometheus_text() -> None:
    client = TestClient(create_app())
    _ = client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "syncore_http_requests_total" in response.text
