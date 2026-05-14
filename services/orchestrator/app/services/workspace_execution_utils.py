from __future__ import annotations

import re
from pathlib import Path

from app.services.workspace_acceptance_service import string_list


def resolve_workspace_path(root: Path, relative_path: str) -> Path:
    if not relative_path or relative_path.startswith("/") or ".." in Path(relative_path).parts:
        raise ValueError(f"Unsafe workspace path: {relative_path}")
    target = (root / relative_path).resolve()
    if root not in target.parents and target != root:
        raise ValueError(f"Workspace path escapes root: {relative_path}")
    return target


def runner_default_command(runner: dict[str, object], section: str, fallback: str) -> str:
    commands = dict(runner.get("commands") or {})
    values = string_list(commands.get(section))
    return values[0] if values else fallback


def command_allowed(command: str, policy: dict[str, object]) -> bool:
    blocked_commands = tuple(policy.get("blocked_commands", ()))
    if any(command.startswith(str(prefix)) for prefix in blocked_commands):
        return False
    allowed_prefixes = tuple(policy.get("allow_commands", ()))
    if any(command.startswith(str(prefix)) for prefix in allowed_prefixes):
        return True
    patterns = tuple(policy.get("allowed_command_patterns", ()))
    return any(re.fullmatch(str(pattern), command) for pattern in patterns)


def check_action_allowed(
    *,
    action_type: str,
    policy: dict[str, object],
    relative_path: str | None = None,
    command: str | None = None,
) -> dict[str, str]:
    allowed_actions = {
        str(item).strip().lower() for item in tuple(policy.get("allowed_actions") or ())
    }
    denied_actions = {
        str(item).strip().lower() for item in tuple(policy.get("denied_actions") or ())
    }
    if action_type in denied_actions:
        return {"status": "blocked", "reason": f"Action {action_type} denied by policy"}
    if allowed_actions and action_type not in allowed_actions:
        return {"status": "blocked", "reason": f"Action {action_type} is not allowed"}
    forbidden_paths = string_list(policy.get("forbidden_paths"))
    if relative_path and forbidden_paths and any(
        relative_path == path or relative_path.startswith(path.rstrip("/") + "/")
        for path in forbidden_paths
    ):
        return {
            "status": "blocked",
            "reason": f"Path {relative_path} is forbidden by workspace policy",
        }
    allowed_paths = string_list(policy.get("allowed_paths"))
    if relative_path and allowed_paths and not any(
        relative_path == path or relative_path.startswith(path.rstrip("/") + "/")
        for path in allowed_paths
    ):
        return {
            "status": "blocked",
            "reason": f"Path {relative_path} is outside allowed workspace roots",
        }
    approval_paths = string_list(policy.get("approval_required_paths"))
    if relative_path and approval_paths and any(
        relative_path == path or relative_path.startswith(path.rstrip("/") + "/")
        for path in approval_paths
    ):
        return {
            "status": "blocked",
            "reason": f"Path {relative_path} requires explicit approval",
        }
    if command and not command_allowed(command, policy):
        return {"status": "blocked", "reason": f"Command {command} is not allowed"}
    return {"status": "ok", "reason": ""}


def preflight_failure(
    *,
    reason: str,
    suggestions: list[str],
    missing_env: list[str] | None = None,
    missing_binaries: list[str] | None = None,
    missing_files: list[str] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "failed",
        "reason": reason,
        "suggestions": suggestions[:8],
    }
    if missing_env:
        payload["missing_env"] = missing_env[:20]
    if missing_binaries:
        payload["missing_binaries"] = missing_binaries[:20]
    if missing_files:
        payload["missing_files"] = missing_files[:20]
    return payload


def binary_install_suggestions(binary: str) -> list[str]:
    common = {
        "python": ["Install Python 3.10+ and ensure `python` or `python3` is on PATH."],
        "node": ["Install Node.js 20+ and ensure `node` is on PATH."],
        "npm": ["Install Node.js/npm and verify `npm --version` succeeds."],
        "pnpm": ["Install pnpm globally, for example `npm install -g pnpm`."],
        "uv": ["Install uv, for example `curl -LsSf https://astral.sh/uv/install.sh | sh`."],
        "cargo": ["Install Rust toolchain via rustup so `cargo` is available on PATH."],
        "go": ["Install Go and verify `go version` succeeds."],
        "gradle": ["Install Gradle or use the project wrapper if available."],
        "java": ["Install a JDK and verify `java -version` succeeds."],
    }
    return common.get(
        binary,
        [f"Install {binary} and ensure it is available on PATH before retrying."],
    )


def needs_dependency_bootstrap(
    *,
    root: Path,
    runner: dict[str, object],
    runbook: dict[str, object],
) -> bool:
    package_manager = str(runbook.get("package_manager") or runner.get("package_manager") or "")
    runner_name = str(runner.get("name") or "")
    if (
        package_manager in {"npm", "pnpm", "yarn"}
        or runner_name.startswith("node-")
        or runner_name == "monorepo-pnpm"
    ):
        return (root / "package.json").exists() and not (root / "node_modules").exists()
    if runner_name.startswith("python-"):
        if (root / "pyproject.toml").exists() and not (root / ".venv").exists():
            return True
        if (root / "requirements.txt").exists():
            return True
    if runner_name == "rust-cli":
        return (root / "Cargo.toml").exists()
    if runner_name == "go-service":
        return (root / "go.mod").exists()
    if runner_name == "java-gradle":
        return (root / "build.gradle").exists() or (root / "build.gradle.kts").exists()
    return False


def classify_workspace_issue(*, stage: str, reason: str) -> dict[str, str]:
    del stage
    lowered = reason.lower()
    if "env var" in lowered or "binary" in lowered or "os" in lowered:
        return {"category": "environment_failure", "strategy": "repair_environment"}
    if "provider" in lowered:
        return {"category": "provider_failure", "strategy": "switch_model_or_provider"}
    if "command" in lowered and "allowed" in lowered:
        return {"category": "policy_block", "strategy": "relax_policy_or_request_approval"}
    if "forbidden" in lowered or "approval" in lowered:
        return {"category": "risk_guardrail", "strategy": "request_approval_or_narrow_scope"}
    if "acceptance" in lowered or "behavior" in lowered:
        return {
            "category": "acceptance_failure",
            "strategy": "tighten_implementation_to_acceptance",
        }
    if "verification" in lowered or "probe" in lowered:
        return {
            "category": "verification_failure",
            "strategy": "run_stronger_verification_or_fix_output",
        }
    if "no changes" in lowered:
        return {
            "category": "no_artifact_change",
            "strategy": "narrow_scope_and_require_mutation_intent",
        }
    return {"category": "workspace_failure", "strategy": "replan_with_repo_context"}


def normalize_workspace_command(command: str) -> str:
    if not command:
        return ""
    normalized = re.sub(r"\s+", " ", command.strip())
    normalized = normalized.replace("python3 -m ", "python -m ")
    return normalized
