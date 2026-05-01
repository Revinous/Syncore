from __future__ import annotations

from app.services.workspace_readiness import compute_workspace_readiness


def test_workspace_readiness_prefers_unattended_when_contract_and_learning_are_strong() -> None:
    result = compute_workspace_readiness(
        scan={"frameworks": ["fastapi"], "languages": ["python"]},
        contract={
            "schema_version": 2,
            "policy_pack": "python-fastapi",
            "runner": "python-fastapi",
            "environment": {
                "required_binaries": ["python"],
                "required_env": ["OPENAI_API_KEY"],
                "required_files": ["pyproject.toml"],
            },
            "commands": {
                "setup": ["uv sync"],
                "test": ["uv run pytest -q"],
                "build": ["python -m compileall ."],
                "lint": ["python -m ruff check ."],
            },
            "capabilities": {
                "allowed_commands": ["uv run pytest -q"],
                "forbidden_paths": ["secrets/"],
                "approval_required_paths": ["infra/"],
            },
            "acceptance": {"must_pass_commands": ["pytest"]},
        },
        runner={"name": "python-fastapi"},
        learning={"success_count": 4},
    )
    assert result["recommended_autonomy_mode"] == "unattended"
    assert result["status"] == "high"


def test_workspace_readiness_penalizes_failure_history() -> None:
    result = compute_workspace_readiness(
        scan={"frameworks": ["nextjs"], "languages": ["typescript"]},
        contract={
            "schema_version": 2,
            "policy_pack": "node-next",
            "runner": "node-next",
            "environment": {"required_binaries": ["node", "npm"]},
            "commands": {"test": ["npm test"]},
            "capabilities": {"allowed_commands": ["npm test"]},
            "acceptance": {"must_pass_commands": ["npm test"]},
        },
        runner={"name": "node-next"},
        learning={"success_count": 1, "failure_count": 6},
    )
    assert result["score"] < 85
    assert result["recommended_autonomy_mode"] in {"guided", "supervised"}
