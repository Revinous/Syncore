from __future__ import annotations

from typing import Any


def compute_workspace_readiness(
    *,
    scan: dict[str, Any],
    contract: dict[str, Any],
    runner: dict[str, Any],
    learning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    learning = dict(learning or {})
    score = 0
    reasons: list[str] = []

    if contract.get("schema_version"):
        score += 10
    if contract.get("policy_pack"):
        score += 10
    if contract.get("runner") or runner.get("name") != "generic":
        score += 10

    environment = dict(contract.get("environment") or {})
    commands = dict(contract.get("commands") or {})
    capabilities = dict(contract.get("capabilities") or {})
    acceptance = dict(contract.get("acceptance") or {})

    if environment.get("required_binaries"):
        score += 10
    else:
        reasons.append("No required binaries declared.")
    if environment.get("required_env"):
        score += 5
    if environment.get("required_files"):
        score += 5

    if any(commands.get(key) for key in ("setup", "test", "build", "lint")):
        score += 15
    else:
        reasons.append("No explicit build/test/lint commands declared.")

    if capabilities.get("allowed_commands") or capabilities.get("allowed_command_patterns"):
        score += 10
    else:
        reasons.append("No explicit command capability policy declared.")

    if capabilities.get("forbidden_paths") or capabilities.get("approval_required_paths"):
        score += 10
    else:
        reasons.append("No path risk rules declared.")

    if any(acceptance.get(key) for key in acceptance):
        score += 15
    else:
        reasons.append("No acceptance criteria declared.")

    frameworks = set(scan.get("frameworks") or [])
    languages = set(scan.get("languages") or [])
    if frameworks or languages:
        score += 5

    success_count = int(learning.get("success_count") or 0)
    if success_count >= 3:
        score += 10
    elif success_count >= 1:
        score += 5
    else:
        reasons.append("No successful autonomous executions recorded yet.")
    failure_count = int(learning.get("failure_count") or 0)
    if failure_count >= 5:
        score -= 15
        reasons.append("Recent autonomy failures reduce unattended confidence.")
    elif failure_count >= 1:
        score -= 5

    score = max(0, min(score, 100))
    autonomy_mode = "observe"
    if score >= 85:
        autonomy_mode = "unattended"
    elif score >= 65:
        autonomy_mode = "supervised"
    elif score >= 40:
        autonomy_mode = "guided"

    return {
        "score": score,
        "recommended_autonomy_mode": autonomy_mode,
        "status": _readiness_status(score),
        "reasons": reasons[:8],
    }


def _readiness_status(score: int) -> str:
    if score >= 85:
        return "high"
    if score >= 65:
        return "good"
    if score >= 40:
        return "partial"
    return "low"
