from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from packages.contracts.python.models import (
    AgentRun,
    AgentRunCreate,
    AgentRunUpdate,
    RunExecutionRequest,
    Task,
)

from app.context.schemas import OptimizedContextBundle
from app.services.run_execution_service import RunExecutionService


class FakeContextService:
    def __init__(self, *, task_id: UUID, included_refs: list[str] | None = None) -> None:
        self._task_id = task_id
        self._included_refs = included_refs or []
        self.called = False

    def assemble_optimized_context(
        self,
        *,
        task_id: UUID,
        target_agent: str,
        target_model: str,
        token_budget: int,
    ) -> OptimizedContextBundle:
        self.called = True
        assert task_id == self._task_id
        return OptimizedContextBundle(
            bundle_id=uuid4(),
            task_id=task_id,
            target_agent=target_agent,
            target_model=target_model,
            token_budget=token_budget,
            estimated_token_count=120,
            optimized_context={
                "rendered_prompt": "## Critical Constraints\nDO NOT remove failing tests.",
                "section_count": 1,
            },
            sections=[],
            included_refs=self._included_refs,
            warnings=["context compressed"],
            created_at=datetime.now(timezone.utc),
        )


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.last_prompt = ""
        self.should_fail = False

    def complete(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ):
        del model, system_prompt, max_output_tokens, temperature
        self.last_prompt = prompt
        if self.should_fail:
            raise RuntimeError("provider boom")
        return type(
            "ProviderResult", (), {"output_text": "model output", "finish_reason": "stop"}
        )()

    def stream(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ):
        del model, system_prompt, max_output_tokens, temperature
        self.last_prompt = prompt
        if self.should_fail:
            raise RuntimeError("provider boom")
        yield "chunk-a"
        yield "chunk-b"


@dataclass
class FakeStore:
    task_id: UUID
    runs: dict[UUID, AgentRun] = field(default_factory=dict)
    events: list[dict[str, str | int | float | bool | None]] = field(default_factory=list)
    context_refs: dict[str, dict[str, object]] = field(default_factory=dict)

    def create_agent_run(self, run: AgentRunCreate) -> AgentRun:
        now = datetime.now(timezone.utc)
        created = AgentRun(
            id=uuid4(),
            task_id=run.task_id,
            role=run.role,
            status=run.status,
            input_summary=run.input_summary,
            output_summary=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self.runs[created.id] = created
        return created

    def update_agent_run(self, run_id: UUID, update: AgentRunUpdate) -> AgentRun | None:
        existing = self.runs.get(run_id)
        if existing is None:
            return None
        updated = AgentRun(
            id=existing.id,
            task_id=existing.task_id,
            role=existing.role,
            status=update.status or existing.status,
            input_summary=existing.input_summary,
            output_summary=update.output_summary
            if update.output_summary is not None
            else existing.output_summary,
            error_message=update.error_message
            if update.error_message is not None
            else existing.error_message,
            created_at=existing.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.runs[run_id] = updated
        return updated

    def save_project_event(self, event) -> None:
        self.events.append(
            {
                "task_id": str(event.task_id),
                "event_type": event.event_type,
                **event.event_data,
            }
        )

    def upsert_context_reference(
        self,
        *,
        ref_id: str,
        task_id: UUID,
        content_type: str,
        original_content: str,
        summary: str,
        retrieval_hint: str,
    ) -> dict[str, object]:
        record: dict[str, object] = {
            "ref_id": ref_id,
            "task_id": task_id,
            "content_type": content_type,
            "original_content": original_content,
            "summary": summary,
            "retrieval_hint": retrieval_hint,
            "created_at": datetime.now(timezone.utc),
        }
        self.context_refs[ref_id] = record
        return record

    def get_context_reference(self, ref_id: str):
        return self.context_refs.get(ref_id)

    def get_task(self, task_id: UUID):
        now = datetime.now(timezone.utc)
        if task_id != self.task_id:
            return None
        return Task(
            id=task_id,
            title="fake task",
            status="in_progress",
            task_type="implementation",
            complexity="medium",
            workspace_id=None,
            created_at=now,
            updated_at=now,
        )

    def list_tasks(self, limit: int = 50, workspace_id=None):
        del workspace_id
        task = self.get_task(self.task_id)
        return [task] if task is not None else []

    def list_agent_runs(self, task_id: UUID | None = None, limit: int = 50):
        del limit
        rows = list(self.runs.values())
        if task_id is not None:
            rows = [row for row in rows if row.task_id == task_id]
        return rows


def _request(task_id: UUID) -> RunExecutionRequest:
    return RunExecutionRequest(
        task_id=task_id,
        prompt="Implement run endpoint with context compression",
        target_agent="coder",
        target_model="gpt-4.1-mini",
        provider="fake",
        token_budget=1600,
    )


def _service(task_id: UUID) -> tuple[RunExecutionService, FakeStore, FakeProvider]:
    store = FakeStore(task_id=task_id)
    provider = FakeProvider()
    context_service = FakeContextService(task_id=task_id)
    service = RunExecutionService(
        store=store,  # type: ignore[arg-type]
        context_service=context_service,  # type: ignore[arg-type]
        providers={"fake": provider},
        default_provider="fake",
        failover_enabled=True,
        fallback_order=["fake"],
        default_timeout_seconds=30,
        max_concurrent_runs_per_task=1,
        max_concurrent_runs_per_workspace=4,
    )
    return service, store, provider


def test_execute_uses_context_and_marks_run_completed() -> None:
    task_id = uuid4()
    store = FakeStore(task_id=task_id)
    provider = FakeProvider()
    context_service = FakeContextService(task_id=task_id, included_refs=["ctxref_abc123"])
    service = RunExecutionService(
        store=store,  # type: ignore[arg-type]
        context_service=context_service,  # type: ignore[arg-type]
        providers={"fake": provider},
        default_provider="fake",
        failover_enabled=True,
        fallback_order=["fake"],
        default_timeout_seconds=30,
        max_concurrent_runs_per_task=1,
        max_concurrent_runs_per_workspace=4,
    )

    payload = _request(task_id).model_copy(update={"provider": None})
    result = service.execute(payload)

    assert context_service.called is True
    assert "## Optimized Context" in provider.last_prompt
    assert "DO NOT remove failing tests." in provider.last_prompt
    assert result.status == "completed"
    assert result.included_refs == ["ctxref_abc123"]
    assert result.total_estimated_tokens >= result.estimated_input_tokens
    assert any(event["event_type"] == "run.started" for event in store.events)
    assert any(event["event_type"] == "run.completed" for event in store.events)
    assert any(event["event_type"] == "run.output.stored" for event in store.events)
    assert len(store.context_refs) >= 3


def test_execute_marks_failed_on_provider_error() -> None:
    task_id = uuid4()
    store = FakeStore(task_id=task_id)
    provider = FakeProvider()
    provider.should_fail = True
    context_service = FakeContextService(task_id=task_id)
    service = RunExecutionService(
        store=store,  # type: ignore[arg-type]
        context_service=context_service,  # type: ignore[arg-type]
        providers={"fake": provider},
        default_provider="fake",
        failover_enabled=True,
        fallback_order=["fake"],
        default_timeout_seconds=30,
        max_concurrent_runs_per_task=1,
        max_concurrent_runs_per_workspace=4,
    )

    with pytest.raises(RuntimeError):
        service.execute(_request(task_id))

    assert any(run.status == "failed" for run in store.runs.values())
    assert any(event["event_type"] == "run.failed" for event in store.events)


def test_stream_execute_emits_started_chunks_and_completed() -> None:
    task_id = uuid4()
    store = FakeStore(task_id=task_id)
    provider = FakeProvider()
    context_service = FakeContextService(task_id=task_id)
    service = RunExecutionService(
        store=store,  # type: ignore[arg-type]
        context_service=context_service,  # type: ignore[arg-type]
        providers={"fake": provider},
        default_provider="fake",
        failover_enabled=True,
        fallback_order=["fake"],
        default_timeout_seconds=30,
        max_concurrent_runs_per_task=1,
        max_concurrent_runs_per_workspace=4,
    )

    events = list(service.stream_execute(_request(task_id)))
    assert events[0].event == "started"
    assert any(event.event == "chunk" for event in events)
    assert events[-1].event == "completed"
    assert any(run.status == "completed" for run in store.runs.values())


def test_execute_failover_uses_secondary_provider() -> None:
    task_id = uuid4()
    store = FakeStore(task_id=task_id)
    primary = FakeProvider()
    primary.should_fail = True
    secondary = FakeProvider()
    context_service = FakeContextService(task_id=task_id)
    service = RunExecutionService(
        store=store,  # type: ignore[arg-type]
        context_service=context_service,  # type: ignore[arg-type]
        providers={"primary": primary, "secondary": secondary},
        default_provider="primary",
        failover_enabled=True,
        fallback_order=["secondary"],
        default_timeout_seconds=30,
        max_concurrent_runs_per_task=1,
        max_concurrent_runs_per_workspace=4,
    )

    result = service.execute(_request(task_id).model_copy(update={"provider": None}))
    assert result.status == "completed"
    assert result.provider == "secondary"


def test_execute_explicit_provider_disables_failover() -> None:
    task_id = uuid4()
    store = FakeStore(task_id=task_id)
    primary = FakeProvider()
    primary.should_fail = True
    secondary = FakeProvider()
    context_service = FakeContextService(task_id=task_id)
    service = RunExecutionService(
        store=store,  # type: ignore[arg-type]
        context_service=context_service,  # type: ignore[arg-type]
        providers={"primary": primary, "secondary": secondary},
        default_provider="primary",
        failover_enabled=True,
        fallback_order=["secondary"],
        default_timeout_seconds=30,
        max_concurrent_runs_per_task=1,
        max_concurrent_runs_per_workspace=4,
    )

    payload = _request(task_id).model_copy(update={"provider": "primary"})
    with pytest.raises(RuntimeError):
        service.execute(payload)


def test_workspace_policy_profile_blocks_disallowed_command(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path
    blocked = service._safe_run_workspace_command(  # type: ignore[attr-defined]
        root,
        "npm run build",
        policy=RunExecutionService.WORKSPACE_POLICY_PROFILES["strict"],
    )
    allowed = service._safe_run_workspace_command(  # type: ignore[attr-defined]
        root,
        "pytest -q",
        policy=RunExecutionService.WORKSPACE_POLICY_PROFILES["strict"],
    )

    assert blocked["status"] == "blocked"
    assert "not allowed" in str(blocked["output"]).lower()
    assert allowed["status"] in {"ok", "failed"}


def test_workspace_command_normalizes_python_alias(monkeypatch, tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)

    def fake_which(binary: str):
        if binary == "python":
            return None
        if binary == "python3":
            return "/usr/bin/python3"
        return shutil.which(binary)

    monkeypatch.setattr("app.services.run_execution_service.shutil.which", fake_which)
    assert service._binary_available("python") is True  # type: ignore[attr-defined]
    normalized = service._normalize_workspace_command("python -m pytest -q")  # type: ignore[attr-defined]
    assert normalized.startswith("python3 -m pytest -q")


def test_workspace_required_command_matching_accepts_python_alias(monkeypatch) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)

    def fake_which(binary: str):
        if binary == "python":
            return None
        if binary == "python3":
            return "/usr/bin/python3"
        return shutil.which(binary)

    monkeypatch.setattr("app.services.run_execution_service.shutil.which", fake_which)
    result = service._verify_mechanical_gates(  # type: ignore[attr-defined]
        command_results=[{"command": "python3 -m pytest -q", "status": "ok", "output": ""}],
        acceptance={"must_pass_commands": ["python -m pytest -q"]},
        runner={},
    )

    assert result["status"] == "ok"


def test_workspace_effective_policy_keeps_explicit_requested_profile() -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)

    policy = service._effective_workspace_policy(  # type: ignore[attr-defined]
        requested_profile="full-dev",
        workspace_metadata={"policy_pack": "python-fastapi"},
        task_preferences={},
    )

    assert policy["profile"] == "full-dev"


def test_workspace_effective_policy_allows_runbook_probe_commands() -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)

    policy = service._effective_workspace_policy(  # type: ignore[attr-defined]
        requested_profile="full-dev",
        workspace_metadata={
            "policy_pack": "python-fastapi",
            "workspace_runbook": {"probe_commands": ["python -c \"print('python-ready')\""]},
        },
        task_preferences={},
    )

    assert "python -c \"print('python-ready')\"" in policy["allow_commands"]


def test_workspace_effective_policy_allows_runner_verification_commands() -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)

    policy = service._effective_workspace_policy(  # type: ignore[attr-defined]
        requested_profile="full-dev",
        workspace_metadata={
            "workspace_runbook": {
                "runner": {
                    "commands": {
                        "lint": ["python -m ruff check ."],
                        "format": ["python -m ruff format ."],
                        "test": ["uv run pytest -q"],
                    }
                }
            }
        },
        task_preferences={},
    )

    assert "python -m ruff check ." in policy["allow_commands"]
    assert "python -m ruff format ." in policy["allow_commands"]
    assert "uv run pytest -q" in policy["allow_commands"]


def test_workspace_path_traversal_is_blocked(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()

    with pytest.raises(PermissionError):
        service._resolve_workspace_path(root, "../outside.txt")  # type: ignore[attr-defined]


def test_workspace_patch_requires_before_text(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    target = root / "main.py"
    target.write_text("print('hello')\n", encoding="utf-8")

    with pytest.raises(ValueError):
        service._safe_patch_with_diff(  # type: ignore[attr-defined]
            task_id=task_id,
            root=root,
            relative_path="main.py",
            before_text="missing_text",
            after_text="print('updated')",
        )


def test_workspace_preflight_fails_for_unconfigured_provider(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    result = service._workspace_preflight(  # type: ignore[attr-defined]
        root=root,
        provider_hint="openai",
    )
    assert result["status"] == "failed"
    assert "not configured" in result["reason"]


def test_workspace_preflight_fails_for_missing_binary(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    result = service._workspace_preflight(  # type: ignore[attr-defined]
        root=root,
        provider_hint="fake",
        required_binaries=["definitely_missing_binary_123"],
    )
    assert result["status"] == "failed"
    assert "missing from PATH" in result["reason"]
    assert result["missing_binaries"] == ["definitely_missing_binary_123"]
    assert result["suggestions"]


def test_workspace_preflight_runner_expected_files_are_not_all_hard_required(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    result = service._workspace_preflight(  # type: ignore[attr-defined]
        root=root,
        provider_hint="fake",
        runner={
            "expected_files": ["pyproject.toml", "requirements.txt"],
            "commands": {},
        },
        required_files=[],
    )
    assert result["status"] == "ok"


def test_workspace_verifier_rejects_empty_execution() -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    result = service._verify_workspace_execution(  # type: ignore[attr-defined]
        changed_files=[],
        command_results=[],
        root=Path("."),
        task_preferences={},
        contract={},
        runbook={},
        runner={},
    )
    assert result["status"] == "failed"


def test_workspace_policy_blocks_action_outside_allowed_root() -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    result = service._check_action_allowed(  # type: ignore[attr-defined]
        action_type="write_file",
        policy={
            "allowed_actions": ("write_file",),
            "allowed_paths": ("src/",),
        },
        relative_path="docs/readme.md",
    )
    assert result["status"] == "blocked"
    assert "outside allowed workspace roots" in result["reason"]


def test_workspace_verifier_enforces_acceptance_criteria(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    target = root / "cli.py"
    target.write_text("print('plain output')\n", encoding="utf-8")

    result = service._verify_workspace_execution(  # type: ignore[attr-defined]
        changed_files=["cli.py"],
        command_results=[{"command": "pytest -q", "status": "ok"}],
        root=root,
        task_preferences={},
        contract={
            "acceptance": {
                "must_pass_commands": ["pytest"],
                "must_modify_paths": ["cli.py"],
                "must_include_behavior": ["help text"],
            }
        },
        runbook={},
        runner={},
    )
    assert result["status"] == "failed"
    assert "missing_behaviors" in result


def test_workspace_verifier_rejects_missing_artifact_and_secret_leak(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    target = root / "cli.py"
    target.write_text("API_KEY = 'sk-proj-demo'\n", encoding="utf-8")

    result = service._verify_workspace_execution(  # type: ignore[attr-defined]
        changed_files=["cli.py"],
        command_results=[{"command": "pytest -q", "status": "ok"}],
        root=root,
        task_preferences={},
        contract={
            "acceptance": {
                "must_pass_commands": ["pytest"],
                "must_create_paths": ["dist/report.txt"],
            }
        },
        runbook={},
        runner={},
    )
    assert result["status"] == "failed"
    assert result["reason"] in {
        "Required artifacts were not created.",
        "Potential secret material detected in changed files.",
    }


def test_workspace_verifier_runs_behavioral_probe_and_checks_output(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    target = root / "cli.py"
    target.write_text("print('ready')\n", encoding="utf-8")

    result = service._verify_workspace_execution(  # type: ignore[attr-defined]
        changed_files=["cli.py"],
        command_results=[],
        root=root,
        task_preferences={},
        contract={
            "acceptance": {
                "probe_commands": ["printf 'calculator ready'"],
                "must_observe_output": ["calculator ready"],
            }
        },
        runbook={},
        runner={},
        policy={"allow_commands": ("printf",)},
    )
    assert result["status"] == "ok"


def test_workspace_verifier_fails_when_behavioral_output_missing(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    (root / "cli.py").write_text("print('ready')\n", encoding="utf-8")

    result = service._verify_workspace_execution(  # type: ignore[attr-defined]
        changed_files=["cli.py"],
        command_results=[],
        root=root,
        task_preferences={},
        contract={
            "acceptance": {
                "probe_commands": ["printf 'calculator ready'"],
                "must_observe_output": ["scientific mode"],
            }
        },
        runbook={},
        runner={},
        policy={"allow_commands": ("printf",)},
    )
    assert result["status"] == "failed"
    assert result["reason"] == "Expected behavioral output markers were not observed."


def test_workspace_auto_repair_runs_setup_when_dependency_artifacts_missing(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    (root / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")

    repaired = service._attempt_workspace_auto_repair(  # type: ignore[attr-defined]
        task_id=task_id,
        root=root,
        runner={
            "name": "node-express",
            "commands": {"setup": ["mkdir -p node_modules"]},
            "package_manager": "npm",
        },
        runbook={"package_manager": "npm"},
        policy={"allow_commands": ("mkdir -p node_modules",)},
    )

    assert repaired is True
    assert (root / "node_modules").exists()


def test_workspace_auto_repair_skips_when_no_bootstrap_needed(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    (root / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")
    (root / "node_modules").mkdir()

    repaired = service._attempt_workspace_auto_repair(  # type: ignore[attr-defined]
        task_id=task_id,
        root=root,
        runner={
            "name": "node-express",
            "commands": {"setup": ["mkdir -p node_modules"]},
            "package_manager": "npm",
        },
        runbook={"package_manager": "npm"},
        policy={"allow_commands": ("mkdir -p node_modules",)},
    )

    assert repaired is False


def test_workspace_verifier_accepts_when_contract_criteria_met(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    target = root / "cli.py"
    target.write_text("print('help text available')\n", encoding="utf-8")

    result = service._verify_workspace_execution(  # type: ignore[attr-defined]
        changed_files=["cli.py"],
        command_results=[{"command": "pytest -q", "status": "ok"}],
        root=root,
        task_preferences={},
        contract={
            "acceptance": {
                "must_pass_commands": ["pytest"],
                "must_modify_paths": ["cli.py"],
                "must_not_modify_paths": ["secrets/"],
                "must_include_behavior": ["help text"],
                "must_create_paths": ["cli.py"],
            }
        },
        runbook={},
        runner={},
    )
    assert result["status"] == "ok"


def test_workspace_verifier_uses_runner_default_test_gate(tmp_path) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    (root / "main.py").write_text("print('ok')\n", encoding="utf-8")

    result = service._verify_workspace_execution(  # type: ignore[attr-defined]
        changed_files=["main.py"],
        command_results=[],
        root=root,
        task_preferences={},
        contract={},
        runbook={},
        runner={"commands": {"test": ["pytest -q"]}},
    )
    assert result["status"] == "failed"
    assert result["reason"] == "Required verification commands did not pass."


def test_workspace_verifier_tolerates_optional_failed_commands_when_required_test_passes(
    tmp_path,
) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    (root / "main.py").write_text("print('ok')\n", encoding="utf-8")

    result = service._verify_workspace_execution(  # type: ignore[attr-defined]
        changed_files=["main.py"],
        command_results=[
            {"command": "uv run pytest -q", "status": "ok", "output": "297 passed"},
            {"command": "python -m ruff check .", "status": "failed", "output": "ruff missing"},
        ],
        root=root,
        task_preferences={},
        contract={
            "acceptance": {
                "must_pass_commands": ["uv run pytest -q"],
            }
        },
        runbook={},
        runner={},
    )

    assert result["status"] == "ok"
    assert "warnings" in result


def test_workspace_runs_all_runner_test_commands_when_required_verification_fails(
    monkeypatch, tmp_path
) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    root = tmp_path / "ws"
    root.mkdir()
    results: list[str] = []

    def fake_run(root_arg, command, *, policy):
        del root_arg, policy
        results.append(command)
        if command == "pytest -q":
            return {"command": command, "status": "failed", "output": "missing deps"}
        return {"command": command, "status": "ok", "output": "297 passed"}

    monkeypatch.setattr(service, "_safe_run_workspace_command", fake_run)
    command_results = [{"command": "pytest -q", "status": "failed", "output": "missing deps"}]
    service._run_all_runner_test_commands(  # type: ignore[attr-defined]
        root=root,
        command_results=command_results,
        runner={"commands": {"test": ["pytest -q", "uv run pytest -q"]}},
        policy={"allow_commands": ("pytest", "uv run pytest")},
    )

    assert "uv run pytest -q" in results
    assert any(item["command"] == "uv run pytest -q" for item in command_results)


def test_meaningful_candidate_change_requires_matching_diff(monkeypatch) -> None:
    task_id = uuid4()
    service, _, _ = _service(task_id)
    parent_id = uuid4()

    monkeypatch.setattr(
        service,
        "_selected_candidate_for_parent",
        lambda parent_id_arg: {
            "candidate_id": "cand-1",
            "target_files": "syncore.yaml,README.md",
            "verification_command": "uv run pytest -q",
        }
        if parent_id_arg == parent_id
        else None,
    )

    failed = service._validate_meaningful_candidate_change(  # type: ignore[attr-defined]
        task_id=task_id,
        task_preferences={"parent_task_id": str(parent_id)},
        changed_files=["docs/guide.md"],
    )
    assert failed["status"] == "failed"
    assert "selected candidate target files" in str(failed["reason"])

    passed = service._validate_meaningful_candidate_change(  # type: ignore[attr-defined]
        task_id=task_id,
        task_preferences={"parent_task_id": str(parent_id)},
        changed_files=["syncore.yaml"],
    )
    assert passed["status"] == "ok"
