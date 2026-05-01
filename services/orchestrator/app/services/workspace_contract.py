from __future__ import annotations

from pathlib import Path
from typing import Any


def load_workspace_contract(root: Path) -> dict[str, Any]:
    contract_path = root / "syncore.yaml"
    if not contract_path.exists() or not contract_path.is_file():
        return {}
    text = contract_path.read_text(encoding="utf-8", errors="replace")
    parsed = _parse_simple_yaml(text)
    if not isinstance(parsed, dict):
        return {}
    return normalize_workspace_contract(parsed)


def normalize_workspace_contract(contract: dict[str, Any]) -> dict[str, Any]:
    environment = _dict_value(contract.get("environment"))
    commands = _dict_value(contract.get("commands"))
    capabilities = _dict_value(contract.get("capabilities"))
    acceptance = _dict_value(contract.get("acceptance"))
    risk_rules = _dict_value(contract.get("risk_rules"))

    normalized = {
        "schema_version": int(contract.get("schema_version") or contract.get("version") or 2),
        "policy_pack": str(contract.get("policy_pack") or "").strip() or None,
        "runner": str(contract.get("runner") or "").strip() or None,
        "environment": {
            "os": _string_list(environment.get("os") or contract.get("os")),
            "package_manager": str(
                environment.get("package_manager") or contract.get("package_manager") or ""
            ).strip()
            or None,
            "required_binaries": _string_list(
                environment.get("required_binaries") or contract.get("required_binaries")
            ),
            "required_env": _string_list(
                environment.get("required_env") or contract.get("required_env")
            ),
            "optional_env": _string_list(environment.get("optional_env")),
            "required_files": _string_list(environment.get("required_files")),
            "preferred_shell": str(environment.get("preferred_shell") or "").strip() or None,
        },
        "commands": {
            "setup": _string_list(commands.get("setup") or contract.get("setup")),
            "build": _string_list(commands.get("build") or contract.get("build")),
            "test": _string_list(commands.get("test") or contract.get("test")),
            "lint": _string_list(commands.get("lint") or contract.get("lint")),
            "format": _string_list(commands.get("format") or contract.get("format")),
            "run": _string_list(commands.get("run") or contract.get("run")),
            "migrations": _string_list(commands.get("migrations") or contract.get("migrations")),
            "deploy": _string_list(commands.get("deploy") or contract.get("deploy")),
        },
        "capabilities": {
            "allow_actions": _string_list(capabilities.get("allow_actions")),
            "deny_actions": _string_list(capabilities.get("deny_actions")),
            "allowed_paths": _string_list(capabilities.get("allowed_paths")),
            "forbidden_paths": _string_list(
                capabilities.get("forbidden_paths") or contract.get("forbidden_paths")
            ),
            "approval_required_paths": _string_list(
                capabilities.get("approval_required_paths")
            ),
            "allowed_commands": _string_list(
                capabilities.get("allowed_commands") or contract.get("allowed_commands")
            ),
            "allowed_command_patterns": _string_list(
                capabilities.get("allowed_command_patterns")
            ),
            "blocked_commands": _string_list(capabilities.get("blocked_commands")),
            "network_policy": str(capabilities.get("network_policy") or "offline").strip()
            or "offline",
        },
        "entrypoints": _string_list(contract.get("entrypoints")),
        "acceptance": {
            "must_pass_commands": _string_list(acceptance.get("must_pass_commands")),
            "must_modify_paths": _string_list(acceptance.get("must_modify_paths")),
            "must_not_modify_paths": _string_list(acceptance.get("must_not_modify_paths")),
            "must_include_behavior": _string_list(acceptance.get("must_include_behavior")),
            "must_create_paths": _string_list(acceptance.get("must_create_paths")),
        },
        "risk_rules": {
            "max_changed_files": _optional_int(risk_rules.get("max_changed_files")),
            "max_diff_chars": _optional_int(risk_rules.get("max_diff_chars")),
            "require_approval_for": _string_list(risk_rules.get("require_approval_for")),
        },
    }
    return normalized


def build_runbook_from_contract(contract: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_workspace_contract(contract)
    command_sections = dict(normalized.get("commands") or {})
    commands: list[str] = []
    for key in ("setup", "build", "test", "lint", "format"):
        commands.extend(_string_list(command_sections.get(key)))
    environment = dict(normalized.get("environment") or {})
    capabilities = dict(normalized.get("capabilities") or {})
    return {
        "commands": commands[:20],
        "command_sections": command_sections,
        "required_env": _string_list(environment.get("required_env")),
        "required_binaries": _string_list(environment.get("required_binaries")),
        "required_files": _string_list(environment.get("required_files")),
        "package_manager": environment.get("package_manager"),
        "allowed_commands": _string_list(capabilities.get("allowed_commands")),
        "allowed_command_patterns": _string_list(
            capabilities.get("allowed_command_patterns")
        ),
        "blocked_commands": _string_list(capabilities.get("blocked_commands")),
        "forbidden_paths": _string_list(capabilities.get("forbidden_paths")),
        "allowed_paths": _string_list(capabilities.get("allowed_paths")),
        "approval_required_paths": _string_list(
            capabilities.get("approval_required_paths")
        ),
        "entrypoints": _string_list(normalized.get("entrypoints")),
        "policy_pack": normalized.get("policy_pack"),
        "runner": normalized.get("runner"),
        "acceptance": dict(normalized.get("acceptance") or {}),
        "risk_rules": dict(normalized.get("risk_rules") or {}),
        "network_policy": str(capabilities.get("network_policy") or "offline"),
    }


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    lines = [
        line.rstrip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(-1, root)]

    for idx, raw in enumerate(lines):
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]

        if line.startswith("- "):
            item = _coerce_scalar(line[2:].strip())
            if isinstance(container, list):
                container.append(item)
                continue
            raise ValueError("Invalid contract list structure.")

        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        key = key.strip()
        value = rest.strip()

        if value == "":
            next_is_list = False
            if idx + 1 < len(lines):
                nxt = lines[idx + 1].strip()
                nxt_indent = len(lines[idx + 1]) - len(lines[idx + 1].lstrip(" "))
                next_is_list = nxt.startswith("- ") and nxt_indent > indent
            new_container: dict[str, Any] | list[Any] = [] if next_is_list else {}
            if isinstance(container, dict):
                container[key] = new_container
            stack.append((indent, new_container))
            continue

        if isinstance(container, dict):
            container[key] = _coerce_scalar(value)

    return root


def _coerce_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    if lowered.startswith('"') and lowered.endswith('"'):
        return value[1:-1]
    if lowered.startswith("'") and lowered.endswith("'"):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
