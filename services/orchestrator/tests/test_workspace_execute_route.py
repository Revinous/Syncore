from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.routes.runs import get_run_execution_service
from app.main import create_app


class _FakeRunService:
    def execute_workspace_loop(self, payload, max_steps: int = 3):
        return {
            "task_id": str(payload.task_id),
            "provider": payload.provider or "default",
            "target_model": payload.target_model,
            "max_steps": max_steps,
            "changed_files": ["calculator/main.py"],
            "diff_ref_ids": ["ctxref_demo"],
            "commands": [],
            "baton_id": str(uuid4()),
            "digest": {"eli5_summary": "What was done: created calculator/main.py"},
        }


def test_execute_workspace_route_returns_artifacts() -> None:
    app = create_app()
    app.dependency_overrides[get_run_execution_service] = lambda: _FakeRunService()
    client = TestClient(app)

    response = client.post(
        "/runs/execute-workspace",
        json={
            "run": {
                "task_id": str(uuid4()),
                "prompt": "build app",
                "target_agent": "coder",
                "target_model": "gpt-5.4",
                "provider": "openai",
                "token_budget": 4000,
            },
            "max_steps": 2,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["changed_files"] == ["calculator/main.py"]
    assert payload["digest"]["eli5_summary"]

    app.dependency_overrides.clear()
