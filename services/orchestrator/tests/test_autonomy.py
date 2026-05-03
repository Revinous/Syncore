from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.runs.providers import ProviderCapabilities
from app.services.autonomy_service import (
    AutonomyService,
    _extract_sdlc_checklist_status,
    _missing_sdlc_topics,
)
from app.services.run_execution_service import RunExecutionService


def _init_sqlite(db_path: Path) -> None:
    schema = Path("scripts/init_sqlite.sql").read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as connection:
        connection.executescript(schema)
        connection.commit()


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_autonomy_scan_once_executes_new_task(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    client = TestClient(create_app())
    task = client.post(
        "/tasks",
        json={
            "title": "Build an auth flow with signup and login",
            "task_type": "implementation",
            "complexity": "medium",
        },
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    for _ in range(4):
        scan = client.post("/autonomy/scan-once")
        assert scan.status_code == 200
        assert scan.json()["processed"] >= 1
        detail = client.get(f"/tasks/{task_id}")
        assert detail.status_code == 200
        if detail.json()["task"]["status"] == "completed":
            break

    detail = client.get(f"/tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["task"]["status"] == "completed"
    assert len(detail.json()["agent_runs"]) >= 3

    events = client.get(f"/tasks/{task_id}/events")
    assert events.status_code == 200
    event_types = {event["event_type"] for event in events.json()}
    assert "autonomy.stage.completed" in event_types
    assert "routing.decision" in event_types
    assert "autonomy.completed" in event_types
    assert "analyst.digest.generated" in event_types


def test_autonomy_background_loop_processes_new_task(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_POLL_INTERVAL_SECONDS", "0.2")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Create API endpoint for invoices",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        deadline = time.time() + 4.0
        final_status = "new"
        while time.time() < deadline:
            detail = client.get(f"/tasks/{task_id}")
            final_status = detail.json()["task"]["status"]
            if final_status == "completed":
                break
            time.sleep(0.2)

        assert final_status == "completed"


def test_autonomy_retries_and_blocks_after_budget(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "missing_provider")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_MAX_RETRIES", "1")
    monkeypatch.setenv("AUTONOMY_RETRY_BASE_SECONDS", "0.1")
    monkeypatch.setenv("PROVIDER_FAILOVER_ENABLED", "false")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Task that will fail provider resolution",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        first = client.post(f"/autonomy/tasks/{task_id}/run")
        assert first.status_code == 200
        assert first.json()["status"] == "retry_scheduled"

        second = client.post(f"/autonomy/tasks/{task_id}/run")
        assert second.status_code == 200
        assert second.json()["status"] in {"waiting_retry", "failed"}

        if second.json()["status"] != "failed":
            time.sleep(0.15)
            third = client.post(f"/autonomy/tasks/{task_id}/run")
            assert third.status_code == 200
            assert third.json()["status"] == "failed"

        detail = client.get(f"/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["task"]["status"] == "blocked"


def test_autonomy_requires_approval_and_resumes_after_approve(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Approval gated task",
                "task_type": "implementation",
                "complexity": "medium",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        pref = client.post(
            "/project-events",
            json={
                "task_id": task_id,
                "event_type": "task.preferences",
                "event_data": {"requires_approval": "true"},
            },
        )
        assert pref.status_code == 201

        first = client.post(f"/autonomy/tasks/{task_id}/run")
        assert first.status_code == 200
        assert first.json()["status"] in {"in_progress", "completed"}

        second = client.post(f"/autonomy/tasks/{task_id}/run")
        assert second.status_code == 200
        assert second.json()["status"] == "awaiting_approval"

        approve = client.post(
            f"/autonomy/tasks/{task_id}/approve",
            json={"reason": "looks good"},
        )
        assert approve.status_code == 200
        assert approve.json()["status"] == "approved"

        for _ in range(4):
            run = client.post(f"/autonomy/tasks/{task_id}/run")
            assert run.status_code == 200
            detail = client.get(f"/tasks/{task_id}")
            assert detail.status_code == 200
            if detail.json()["task"]["status"] == "completed":
                break

        final_detail = client.get(f"/tasks/{task_id}")
        assert final_detail.status_code == 200
        assert final_detail.json()["task"]["status"] == "completed"


def test_autonomy_downgrades_unattended_when_workspace_readiness_is_low(
    monkeypatch, tmp_path
) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "README.md").write_text("# Demo\n", encoding="utf-8")

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    with TestClient(create_app()) as client:
        workspace = client.post(
            "/workspaces",
            json={
                "name": "Low Ready Workspace",
                "root_path": str(workspace_root),
                "runtime_mode": "native",
                "metadata": {},
            },
        )
        assert workspace.status_code == 201
        workspace_id = workspace.json()["id"]

        scan = client.post(f"/workspaces/{workspace_id}/scan")
        assert scan.status_code == 200

        task = client.post(
            "/tasks",
            json={
                "title": "Unattended requested on low-readiness workspace",
                "task_type": "implementation",
                "complexity": "low",
                "workspace_id": workspace_id,
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        pref = client.post(
            "/project-events",
            json={
                "task_id": task_id,
                "event_type": "task.preferences",
                "event_data": {"autonomy_mode": "unattended"},
            },
        )
        assert pref.status_code == 201

        run = client.post(f"/autonomy/tasks/{task_id}/run")
        assert run.status_code == 200

        events = client.get(f"/tasks/{task_id}/events")
        assert events.status_code == 200
        adjusted = [
            event
            for event in events.json()
            if event["event_type"] == "autonomy.mode.adjusted"
        ]
        assert adjusted
        assert adjusted[-1]["event_data"]["mode"] != "unattended"


def test_autonomy_recovers_after_app_restart(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Restart recovery task",
                "task_type": "implementation",
                "complexity": "medium",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        first = client.post(f"/autonomy/tasks/{task_id}/run")
        assert first.status_code == 200
        snapshots = client.get(f"/autonomy/tasks/{task_id}/snapshots")
        assert snapshots.status_code == 200
        assert len(snapshots.json()) >= 1

    get_settings.cache_clear()

    with TestClient(create_app()) as restarted:
        for _ in range(5):
            resumed = restarted.post(f"/autonomy/tasks/{task_id}/run")
            assert resumed.status_code == 200
            detail = restarted.get(f"/tasks/{task_id}")
            assert detail.status_code == 200
            if detail.json()["task"]["status"] == "completed":
                break

        final = restarted.get(f"/tasks/{task_id}")
        assert final.status_code == 200
        assert final.json()["task"]["status"] == "completed"
        snapshots = restarted.get(f"/autonomy/tasks/{task_id}/snapshots")
        assert snapshots.status_code == 200
        assert len(snapshots.json()) >= 3


def test_failure_aware_provider_choice_prefers_alternate_provider_after_repeated_failures() -> None:
    task_id = uuid4()
    workspace_id = uuid4()

    class FakeStore:
        def list_project_events(self, task_id: UUID, limit=100):
            del limit
            return [
                SimpleNamespace(
                    event_type="run.failed",
                    event_data={"provider": "openai"},
                    task_id=task_id,
                ),
                SimpleNamespace(
                    event_type="run.failed",
                    event_data={"provider": "openai"},
                    task_id=task_id,
                ),
            ]

        def get_workspace(self, workspace_id_arg):
            assert workspace_id_arg == workspace_id
            return SimpleNamespace(metadata={})

    class FakeRunExecutionService:
        def list_provider_capabilities(self):
            return [
                ProviderCapabilities(
                    provider="openai",
                    supports_streaming=True,
                    supports_system_prompt=True,
                    supports_temperature=True,
                    supports_max_tokens=True,
                    model_hint="gpt-5.4",
                    max_context_tokens=128_000,
                    quality_tier=5,
                    speed_tier=4,
                    cost_tier=4,
                    strengths=("implementation",),
                ),
                ProviderCapabilities(
                    provider="anthropic",
                    supports_streaming=True,
                    supports_system_prompt=True,
                    supports_temperature=True,
                    supports_max_tokens=True,
                    model_hint="claude",
                    max_context_tokens=200_000,
                    quality_tier=5,
                    speed_tier=3,
                    cost_tier=4,
                    strengths=("review",),
                ),
            ]

    service = AutonomyService(
        store=FakeStore(),  # type: ignore[arg-type]
        run_execution_service=FakeRunExecutionService(),  # type: ignore[arg-type]
        routing_service=SimpleNamespace(),
        digest_service=SimpleNamespace(),
        default_provider="openai",
        default_model="gpt-5.4",
        default_max_retries=1,
        retry_base_seconds=0.1,
        max_cycles=2,
        max_total_steps=10,
        review_pass_keyword="PASS",
        plan_min_chars=20,
        execute_min_chars=40,
        review_min_chars=20,
        workspace_execution_enabled=True,
        workspace_execution_profile="balanced",
        workspace_auto_approve_low_risk=True,
        workspace_max_steps=3,
        execute_plan_enabled=True,
        failure_taxonomy_v2_enabled=True,
        low_info_stop_enabled=True,
        low_info_threshold=2,
        max_provider_switches=2,
    )
    task = SimpleNamespace(id=task_id, workspace_id=workspace_id)

    chosen = service._resolve_provider(  # type: ignore[attr-defined]
        stage="execute",
        task=task,
        prefs={"preferred_provider": "openai"},
    )
    assert chosen == "anthropic"


def test_autonomy_parent_waits_for_spawned_children(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    with TestClient(create_app()) as client:
        parent = client.post(
            "/tasks",
            json={
                "title": "Planner parent task",
                "task_type": "implementation",
                "complexity": "medium",
            },
        )
        assert parent.status_code == 201
        parent_id = parent.json()["id"]

        pref = client.post(
            "/project-events",
            json={
                "task_id": parent_id,
                "event_type": "task.preferences",
                "event_data": {"auto_spawn": "true", "auto_spawn_count": "3"},
            },
        )
        assert pref.status_code == 201

        completed = False
        for _ in range(20):
            scan = client.post("/autonomy/scan-once")
            assert scan.status_code == 200
            parent_detail = client.get(f"/tasks/{parent_id}")
            assert parent_detail.status_code == 200
            if parent_detail.json()["task"]["status"] == "completed":
                completed = True
                break
            time.sleep(0.05)

        assert completed is True

        events = client.get(f"/tasks/{parent_id}/events")
        assert events.status_code == 200
        event_types = {event["event_type"] for event in events.json()}
        assert "autonomy.subtasks.spawned" in event_types
        assert "autonomy.children.completed" in event_types

        snapshots = client.get(f"/autonomy/tasks/{parent_id}/snapshots")
        assert snapshots.status_code == 200
        assert len(snapshots.json()) >= 1

        board = client.get(f"/tasks/{parent_id}/children")
        assert board.status_code == 200
        payload = board.json()
        assert payload["has_children"] is True
        assert payload["total_children"] >= 1


def test_autonomy_reject_blocks_task(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Approval rejected task",
                "task_type": "implementation",
                "complexity": "medium",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        pref = client.post(
            "/project-events",
            json={
                "task_id": task_id,
                "event_type": "task.preferences",
                "event_data": {"requires_approval": "true"},
            },
        )
        assert pref.status_code == 201

        _ = client.post(f"/autonomy/tasks/{task_id}/run")
        awaiting = client.post(f"/autonomy/tasks/{task_id}/run")
        assert awaiting.status_code == 200
        assert awaiting.json()["status"] == "awaiting_approval"

        reject = client.post(
            f"/autonomy/tasks/{task_id}/reject",
            json={"reason": "not safe"},
        )
        assert reject.status_code == 200
        assert reject.json()["status"] == "rejected"


def test_sdlc_topic_detection_finds_missing_items() -> None:
    text = "Plan covers requirements, design, implementation, and docs."
    missing = _missing_sdlc_topics(text)
    assert "tests" in missing
    assert "release" in missing
    assert "requirements" not in missing


def test_sdlc_checklist_status_detects_checked_items() -> None:
    text = """
    - [x] requirements
    - [x] design
    - [ ] implementation
    - [x] tests
    - [ ] docs
    - [x] release
    """
    status = _extract_sdlc_checklist_status(text)
    assert status["requirements"] is True
    assert status["design"] is True
    assert status["implementation"] is False
    assert status["docs"] is False
    assert status["release"] is True


def test_autonomy_spawns_subtasks_when_enabled(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Planner fanout task",
                "task_type": "implementation",
                "complexity": "medium",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        pref = client.post(
            "/project-events",
            json={
                "task_id": task_id,
                "event_type": "task.preferences",
                "event_data": {
                    "auto_spawn": "true",
                    "auto_spawn_count": "3",
                    "autonomy_mode": "supervised",
                    "workspace_execution_enabled": "true",
                    "workspace_policy_profile": "full-dev",
                },
            },
        )
        assert pref.status_code == 201

        for _ in range(3):
            run = client.post(f"/autonomy/tasks/{task_id}/run")
            assert run.status_code == 200

        tasks = client.get("/tasks?limit=50")
        assert tasks.status_code == 200
        related = [t for t in tasks.json() if t["title"].startswith("Planner fanout task :: ")]
        assert len(related) >= 3

        child_pref_map = {}
        for task_row in related:
            child_events = client.get(f"/tasks/{task_row['id']}/events")
            assert child_events.status_code == 200
            child_pref = next(
                event for event in child_events.json() if event["event_type"] == "task.preferences"
            )
            child_pref_map[task_row["title"]] = child_pref["event_data"]

        analysis_title = "Planner fanout task :: Requirements and design pass"
        implementation_title = "Planner fanout task :: Implementation pass"
        review_title = "Planner fanout task :: Verification and release pass"

        assert child_pref_map[analysis_title]["autonomy_mode"] == "supervised"
        assert child_pref_map[analysis_title]["workspace_execution_enabled"] == "false"
        assert child_pref_map[implementation_title]["workspace_execution_enabled"] == "true"
        assert child_pref_map[implementation_title]["workspace_policy_profile"] == "full-dev"
        assert child_pref_map[review_title]["workspace_execution_enabled"] == "false"

def test_autonomy_review_gate_completes_with_keyword_instruction(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_REVIEW_PASS_KEYWORD", "SYNCORE_REVIEW_OK")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
            "title": "Task with review pass keyword",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        for _ in range(8):
            run = client.post(f"/autonomy/tasks/{task_id}/run")
            assert run.status_code == 200
            if run.json()["status"] == "completed":
                break

        detail = client.get(f"/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["task"]["status"] == "completed"


def test_autonomy_blocks_when_total_step_budget_reached(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_MAX_TOTAL_STEPS", "1")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Task blocked by max steps",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        seed = client.post(
            "/project-events",
            json={
                "task_id": task_id,
                "event_type": "autonomy.stage.completed",
                "event_data": {"stage": "plan", "cycle": 1},
            },
        )
        assert seed.status_code == 201

        run = client.post(f"/autonomy/tasks/{task_id}/run")
        assert run.status_code == 200
        assert run.json()["status"] == "failed"

        detail = client.get(f"/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["task"]["status"] == "blocked"


def test_autonomy_quality_gate_can_trigger_replan(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_PLAN_MIN_CHARS", "10000")
    monkeypatch.setenv("AUTONOMY_MAX_CYCLES", "2")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Task that should replan from quality gate",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        first = client.post(f"/autonomy/tasks/{task_id}/run")
        assert first.status_code == 200
        assert first.json()["status"] == "replanning"

        events = client.get(f"/tasks/{task_id}/events")
        assert events.status_code == 200
        assert any(e["event_type"] == "autonomy.quality.failed" for e in events.json())


def test_autonomy_creates_and_reuses_execute_plan(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Task that should create and reuse execute plan",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        for _ in range(4):
            run = client.post(f"/autonomy/tasks/{task_id}/run")
            assert run.status_code == 200
            detail = client.get(f"/tasks/{task_id}")
            if detail.json()["task"]["status"] == "completed":
                break

        events = client.get(f"/tasks/{task_id}/events")
        assert events.status_code == 200
        event_types = [event["event_type"] for event in events.json()]
        assert "autonomy.execute_plan.created" in event_types
        assert "autonomy.execute_plan.reused" in event_types


def test_autonomy_low_information_failure_stops_retries(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "missing_provider")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_MAX_RETRIES", "3")
    monkeypatch.setenv("AUTONOMY_RETRY_BASE_SECONDS", "0.01")
    monkeypatch.setenv("AUTONOMY_LOW_INFO_THRESHOLD", "2")
    monkeypatch.setenv("PROVIDER_FAILOVER_ENABLED", "false")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Task that should stop repeated identical provider failures",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        first = client.post(f"/autonomy/tasks/{task_id}/run")
        assert first.status_code == 200
        assert first.json()["status"] == "retry_scheduled"

        second = None
        for _ in range(10):
            time.sleep(0.15)
            response = client.post(f"/autonomy/tasks/{task_id}/run")
            assert response.status_code == 200
            second = response
            if response.json()["status"] == "failed":
                break
        assert second is not None
        assert second.json()["status"] == "failed"
        assert "repeated equivalent failures" in second.json()["note"]

        events = client.get(f"/tasks/{task_id}/events")
        assert events.status_code == 200
        event_types = [event["event_type"] for event in events.json()]
        assert "autonomy.low_information_gain.detected" in event_types
        assert "autonomy.stopped.low_information_gain" in event_types


def test_autonomy_missing_execute_plan_replans(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_MAX_CYCLES", "2")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Task with missing execute plan",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        for event_type, event_data in [
            ("autonomy.started", {"execute_role": "coder"}),
            ("autonomy.cycle.started", {"cycle": 1, "mode": "initial"}),
            ("autonomy.stage.completed", {"stage": "plan", "cycle": 1}),
        ]:
            seeded = client.post(
                "/project-events",
                json={"task_id": task_id, "event_type": event_type, "event_data": event_data},
            )
            assert seeded.status_code == 201

        run = client.post(f"/autonomy/tasks/{task_id}/run")
        assert run.status_code == 200
        assert run.json()["status"] == "replanning"

        events = client.get(f"/tasks/{task_id}/events")
        assert events.status_code == 200
        assert any(e["event_type"] == "autonomy.execute_plan.missing" for e in events.json())


def test_autonomy_persists_state_snapshots(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Task with snapshot trail",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        run = client.post(f"/autonomy/tasks/{task_id}/run")
        assert run.status_code == 200

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM autonomy_snapshots WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        assert row is not None
        assert int(row[0]) >= 1


def test_autonomy_skips_when_stage_already_inflight(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")

    with TestClient(create_app()) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Task with inflight stage",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        for event_type in ["autonomy.started", "autonomy.cycle.started", "autonomy.stage.started"]:
            event_data = {}
            if event_type == "autonomy.started":
                event_data = {"execute_role": "coder"}
            elif event_type == "autonomy.cycle.started":
                event_data = {"cycle": 1, "mode": "initial"}
            else:
                event_data = {"stage": "plan", "cycle": 1, "strategy": "default"}
            response = client.post(
                "/project-events",
                json={
                    "task_id": task_id,
                    "event_type": event_type,
                    "event_data": event_data,
                },
            )
            assert response.status_code == 201

        run = client.post(f"/autonomy/tasks/{task_id}/run")
        assert run.status_code == 200
        assert run.json()["status"] == "in_progress"
        assert "already running" in run.json()["note"]


def test_autonomy_analysis_child_handoff_unblocks_implementation(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "gpt-5.4")

    captured_prompts: list[str] = []

    class FakeRunExecutionService:
        def execute(self, payload):
            captured_prompts.append(payload.prompt)
            if "Requirements and design pass" in payload.prompt:
                    return SimpleNamespace(
                        run_id=uuid4(),
                        provider="openai",
                        target_model=payload.target_model,
                        output_text=(
                            "Candidate improvement: Add a repo-specific syncore.yaml contract.\n"
                            "Required implementation: "
                            "Create syncore.yaml with uv-based test and lint commands.\n"
                            "Target files: syncore.yaml\n"
                            "Risks:\n- Keep the change additive.\n"
                            "Verification command: uv run pytest -q\n"
                            "$ uv run pytest -q\n"
                        ),
                )
            return SimpleNamespace(
                run_id=uuid4(),
                provider="openai",
                target_model=payload.target_model,
                output_text=(
                    "Implemented syncore.yaml contract.\n"
                    "$ uv run pytest -q\n"
                ),
            )

        def list_provider_capabilities(self):
            return [
                ProviderCapabilities(
                    provider="openai",
                    supports_streaming=True,
                    supports_system_prompt=True,
                    supports_temperature=True,
                    supports_max_tokens=True,
                    model_hint="gpt-5.4",
                    max_context_tokens=128_000,
                    quality_tier=5,
                    speed_tier=4,
                    cost_tier=4,
                    strengths=("implementation", "analysis"),
                )
            ]

    monkeypatch.setattr(
        RunExecutionService,
        "from_settings",
        classmethod(lambda cls, settings: FakeRunExecutionService()),
    )

    with TestClient(create_app()) as client:
        parent = client.post(
            "/tasks",
            json={
                "title": "Parent repo improvement task",
                "task_type": "implementation",
                "complexity": "medium",
            },
        )
        assert parent.status_code == 201
        parent_id = parent.json()["id"]

        analysis = client.post(
            "/tasks",
            json={
                "title": "Parent repo improvement task :: Requirements and design pass",
                "task_type": "analysis",
                "complexity": "medium",
            },
        )
        assert analysis.status_code == 201
        analysis_id = analysis.json()["id"]

        implementation = client.post(
            "/tasks",
            json={
                "title": "Parent repo improvement task :: Implementation pass",
                "task_type": "implementation",
                "complexity": "medium",
            },
        )
        assert implementation.status_code == 201
        implementation_id = implementation.json()["id"]

        spawned = client.post(
            "/project-events",
            json={
                "task_id": parent_id,
                "event_type": "autonomy.subtasks.spawned",
                "event_data": {
                    "count": 2,
                    "child_task_ids": f"{analysis_id},{implementation_id}",
                },
            },
        )
        assert spawned.status_code == 201

        for child_id, workspace_enabled in [
            (analysis_id, "false"),
            (implementation_id, "false"),
        ]:
            pref = client.post(
                "/project-events",
                json={
                    "task_id": child_id,
                    "event_type": "task.preferences",
                    "event_data": {
                        "parent_task_id": parent_id,
                        "preferred_provider": "openai",
                        "preferred_model": "gpt-5.4",
                        "workspace_execution_enabled": workspace_enabled,
                    },
                },
            )
            assert pref.status_code == 201
            for event_type, event_data in [
                ("autonomy.started", {"execute_role": "coder"}),
                ("autonomy.cycle.started", {"cycle": 1, "mode": "initial"}),
                ("autonomy.stage.completed", {"stage": "plan", "cycle": 1}),
                (
                    "autonomy.execute_plan.created",
                    {
                        "cycle": 1,
                        "strategy": "default",
                        "objective": "Implement repo-safe improvement",
                        "actions": "Inspect repo | Apply improvement | Verify result",
                        "target_files": "syncore.yaml",
                        "verification_commands": "uv run pytest -q",
                        "acceptance_checks": (
                            "Produce concrete artifact | Verify command passes"
                        ),
                        "fallback_strategy": "replan",
                        "risk_level": "low",
                        "signature": "seededplan",
                        "action_count": 3,
                    },
                ),
            ]:
                seeded = client.post(
                    "/project-events",
                    json={
                        "task_id": child_id,
                        "event_type": event_type,
                        "event_data": event_data,
                    },
                )
                assert seeded.status_code == 201

        waiting = client.post(f"/autonomy/tasks/{implementation_id}/run")
        assert waiting.status_code == 200
        assert waiting.json()["status"] == "in_progress"
        assert "Waiting for analysis child" in waiting.json()["note"]

        analysis_run = client.post(f"/autonomy/tasks/{analysis_id}/run")
        assert analysis_run.status_code == 200
        assert analysis_run.json()["status"] in {"in_progress", "replanning", "retry_scheduled"}

        analysis_events = client.get(f"/tasks/{analysis_id}/events")
        assert analysis_events.status_code == 200
        recommendation_events = [
            event
            for event in analysis_events.json()
            if event["event_type"] == "autonomy.recommended_improvement"
        ]
        assert recommendation_events
        candidate_events = [
            event
            for event in analysis_events.json()
            if event["event_type"] == "autonomy.candidate.selected"
        ]
        assert candidate_events
        assert (
            recommendation_events[-1]["event_data"]["verification_command"]
            == "uv run pytest -q"
        )

        service = AutonomyService.from_settings(get_settings())
        implementation_task = service._store.get_task(UUID(implementation_id))
        assert implementation_task is not None
        prompt = service._prompt_for_stage(
            stage="execute",
            task=implementation_task,
            prefs={
                "parent_task_id": parent_id,
                "preferred_provider": "openai",
                "preferred_model": "gpt-5.4",
            },
            cycle=1,
            strategy="default",
            enforce_sdlc=False,
        )
        assert "Selected improvement candidate from analysis child" in prompt
        assert "Create syncore.yaml with uv-based test and lint commands." in prompt
        assert "uv run pytest -q" in prompt

        impl_run = client.post(f"/autonomy/tasks/{implementation_id}/run")
        assert impl_run.status_code == 200
        assert impl_run.json()["status"] in {"in_progress", "replanning"}
        assert any(
            "Selected improvement candidate from analysis child" in item
            for item in captured_prompts
        )
        implementation_events = client.get(f"/tasks/{implementation_id}/events")
        assert implementation_events.status_code == 200
        assert any(
            event["event_type"] == "autonomy.mutation_intent.declared"
            for event in implementation_events.json()
        )


def test_autonomy_uses_feedback_for_replan_strategy(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "syncore.db"
    _init_sqlite(db_path)

    monkeypatch.setenv("SYNCORE_RUNTIME_MODE", "native")
    monkeypatch.setenv("SYNCORE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local_echo")
    monkeypatch.setenv("AUTONOMY_DEFAULT_MODEL", "local_echo")
    monkeypatch.setenv("AUTONOMY_PLAN_MIN_CHARS", "10000")
    monkeypatch.setenv("AUTONOMY_MAX_CYCLES", "2")

    with TestClient(create_app()) as client:
        seed_task = client.post(
            "/tasks",
            json={
                "title": "Seed feedback task",
                "task_type": "analysis",
                "complexity": "low",
            },
        )
        assert seed_task.status_code == 201
        seed_task_id = seed_task.json()["id"]
        for _ in range(2):
            ev = client.post(
                "/project-events",
                json={
                    "task_id": seed_task_id,
                    "event_type": "autonomy.feedback",
                    "event_data": {"strategy": "raise_verification", "outcome": "success"},
                },
            )
            assert ev.status_code == 201

        task = client.post(
            "/tasks",
            json={
                "title": "Task that replans from quality gate",
                "task_type": "implementation",
                "complexity": "low",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        first = client.post(f"/autonomy/tasks/{task_id}/run")
        assert first.status_code == 200
        assert first.json()["status"] == "replanning"

        second = client.post(f"/autonomy/tasks/{task_id}/run")
        assert second.status_code == 200

        events = client.get(f"/tasks/{task_id}/events")
        assert events.status_code == 200
        strategy_events = [
            e for e in events.json() if e["event_type"] == "autonomy.strategy.selected"
        ]
        assert len(strategy_events) >= 2
        assert strategy_events[-1]["event_data"]["strategy"] == "raise_verification"
