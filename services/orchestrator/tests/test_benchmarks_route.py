from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def test_latest_benchmark_report_missing(monkeypatch, tmp_path) -> None:
    report_path = tmp_path / "latest.json"
    monkeypatch.setenv("BENCHMARK_REPORT_PATH", str(report_path))
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.get("/benchmarks/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False


def test_latest_benchmark_report_present(monkeypatch, tmp_path) -> None:
    report_path = tmp_path / "latest.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-05-13T00:00:00Z",
                "api_url": "http://127.0.0.1:8000",
                "execute_enabled": False,
                "provider": None,
                "model": None,
                "cases": [
                    {
                        "name": "itsdangerous",
                        "repo_url": "https://github.com/pallets/itsdangerous",
                        "root_path": "/tmp/itsdangerous",
                        "baseline_test_command": "uv run pytest -q",
                        "baseline_test_passed": True,
                        "workspace_id": "ws-1",
                        "languages": ["python"],
                        "frameworks": [],
                        "package_managers": ["uv"],
                        "test_commands": ["pytest"],
                        "readiness_pack": "python-fastapi",
                        "readiness_runner": "python-fastapi",
                        "live_execution_attempted": False,
                        "live_execution_passed": False,
                        "task_id": None,
                        "execution_outcome": None,
                        "verification_status": None,
                        "meaningful_change": None,
                        "notes": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BENCHMARK_REPORT_PATH", str(report_path))
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.get("/benchmarks/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["case_count"] == 1
    assert payload["baseline_pass_count"] == 1
    assert payload["cases"][0]["name"] == "itsdangerous"


def test_latest_benchmark_report_normalizes_runner_object(monkeypatch, tmp_path) -> None:
    report_path = tmp_path / "latest.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-05-13T00:00:00Z",
                "cases": [
                    {
                        "name": "itsdangerous",
                        "repo_url": "https://github.com/pallets/itsdangerous",
                        "root_path": "/tmp/itsdangerous",
                        "baseline_test_command": "uv run pytest -q",
                        "baseline_test_passed": True,
                        "readiness_runner": {"name": "python-fastapi"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BENCHMARK_REPORT_PATH", str(report_path))
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.get("/benchmarks/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["cases"][0]["readiness_runner"] == "python-fastapi"
