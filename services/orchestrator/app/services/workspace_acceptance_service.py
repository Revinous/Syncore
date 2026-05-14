from __future__ import annotations

from pathlib import Path


def string_list(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


class WorkspaceAcceptanceService:
    def __init__(self, normalize_command):
        self._normalize_command = normalize_command

    def merged_acceptance_criteria(
        self,
        *,
        task_preferences: dict[str, str],
        contract: dict[str, object],
        runbook: dict[str, object],
    ) -> dict[str, list[str]]:
        contract_acceptance = contract.get("acceptance")
        source = (
            contract_acceptance
            if isinstance(contract_acceptance, dict)
            else runbook.get("acceptance")
        )
        source_dict = dict(source) if isinstance(source, dict) else {}
        runner_commands = dict(runbook.get("runner", {}).get("commands") or {})
        merged = {
            "must_pass_commands": string_list(source_dict.get("must_pass_commands")),
            "must_modify_paths": string_list(source_dict.get("must_modify_paths")),
            "must_not_modify_paths": string_list(source_dict.get("must_not_modify_paths")),
            "must_include_behavior": string_list(source_dict.get("must_include_behavior")),
            "must_create_paths": string_list(source_dict.get("must_create_paths")),
            "must_observe_output": string_list(source_dict.get("must_observe_output")),
            "probe_commands": string_list(source_dict.get("probe_commands")),
        }
        if not merged["probe_commands"]:
            merged["probe_commands"] = string_list(runbook.get("probe_commands")) or string_list(
                runner_commands.get("probe")
            )
        if not merged["must_observe_output"]:
            merged["must_observe_output"] = self.default_probe_markers(
                probe_commands=merged["probe_commands"]
            )
        for key in tuple(merged.keys()):
            pref_value = task_preferences.get(key)
            if pref_value:
                merged[key] = [item.strip() for item in pref_value.split(",") if item.strip()]
        return merged

    def verify_mechanical_gates(
        self,
        *,
        command_results: list[dict[str, object]],
        acceptance: dict[str, list[str]],
        runner: dict[str, object],
    ) -> dict[str, object]:
        required = acceptance.get("must_pass_commands", [])
        if not required:
            runner_commands = dict(runner.get("commands") or {})
            required = string_list(runner_commands.get("test"))[:1]
        if required:
            observed_ok = {
                str(item.get("command") or "")
                for item in command_results
                if str(item.get("status")) == "ok"
            }
            missing = [
                command
                for command in required
                if not any(
                    self.workspace_commands_match(command, observed) for observed in observed_ok
                )
            ]
            if missing:
                return {
                    "status": "failed",
                    "reason": "Required verification commands did not pass.",
                    "missing_commands": missing,
                }
        return {"status": "ok", "reason": ""}

    def ensure_required_verification_commands_run(
        self,
        *,
        root: Path,
        command_results: list[dict[str, object]],
        acceptance: dict[str, list[str]],
        runner: dict[str, object],
        policy: dict[str, object],
        run_command,
    ) -> None:
        required = acceptance.get("must_pass_commands", [])
        if not required:
            runner_commands = dict(runner.get("commands") or {})
            required = string_list(runner_commands.get("test"))[:1]
        if not required:
            return
        observed_ok = {
            str(item.get("command") or "")
            for item in command_results
            if str(item.get("status")) == "ok"
        }
        for command in required:
            if any(self.workspace_commands_match(command, existing) for existing in observed_ok):
                continue
            result = run_command(root, command, policy)
            command_results.append(result)
            if str(result.get("status")) == "ok":
                observed_ok.add(str(result.get("command") or command))

    def run_all_runner_test_commands(
        self,
        *,
        root: Path,
        command_results: list[dict[str, object]],
        runner: dict[str, object],
        policy: dict[str, object],
        run_command,
    ) -> None:
        runner_commands = dict(runner.get("commands") or {})
        candidates = string_list(runner_commands.get("test"))
        if not candidates:
            return
        observed_ok = {
            str(item.get("command") or "")
            for item in command_results
            if str(item.get("status")) == "ok"
        }
        for command in candidates:
            if any(self.workspace_commands_match(command, existing) for existing in observed_ok):
                continue
            result = run_command(root, command, policy)
            command_results.append(result)
            if str(result.get("status")) == "ok":
                observed_ok.add(str(result.get("command") or command))

    def verify_acceptance_criteria(
        self,
        *,
        root: Path,
        changed_files: list[str],
        acceptance: dict[str, list[str]],
    ) -> dict[str, object]:
        must_modify = acceptance.get("must_modify_paths", [])
        if must_modify:
            missing_paths = [
                path
                for path in must_modify
                if not any(
                    changed == path or changed.startswith(path.rstrip("/") + "/")
                    for changed in changed_files
                )
            ]
            if missing_paths:
                return {
                    "status": "failed",
                    "reason": "Required paths were not modified.",
                    "missing_paths": missing_paths,
                }
        must_not_modify = acceptance.get("must_not_modify_paths", [])
        if must_not_modify:
            violated = [
                path
                for path in changed_files
                if any(
                    path == forbidden or path.startswith(forbidden.rstrip("/") + "/")
                    for forbidden in must_not_modify
                )
            ]
            if violated:
                return {
                    "status": "failed",
                    "reason": "Disallowed paths were modified.",
                    "violations": violated[:20],
                }
        behaviors = acceptance.get("must_include_behavior", [])
        if behaviors:
            corpus: list[str] = []
            for rel in changed_files[:50]:
                target = root / rel
                if target.exists() and target.is_file():
                    try:
                        corpus.append(target.read_text(encoding="utf-8", errors="replace"))
                    except OSError:
                        continue
            joined = "\n".join(corpus).lower()
            missing_behaviors = [item for item in behaviors if item.lower() not in joined]
            if missing_behaviors:
                return {
                    "status": "failed",
                    "reason": "Acceptance behavior markers were not found in changed artifacts.",
                    "missing_behaviors": missing_behaviors,
                }
        must_create = acceptance.get("must_create_paths", [])
        if must_create:
            missing_create = [path for path in must_create if not (root / path).exists()]
            if missing_create:
                return {
                    "status": "failed",
                    "reason": "Required artifacts were not created.",
                    "missing_paths": missing_create,
                }
        return {"status": "ok", "reason": ""}

    def workspace_commands_match(self, expected: str, observed: str) -> bool:
        normalized_expected = self._normalize_command(expected).strip()
        normalized_observed = self._normalize_command(observed).strip()
        if not normalized_expected or not normalized_observed:
            return False
        return (
            normalized_expected == normalized_observed
            or normalized_expected in normalized_observed
            or normalized_observed in normalized_expected
        )

    def default_probe_markers(self, *, probe_commands: list[str]) -> list[str]:
        markers: list[str] = []
        for command in probe_commands:
            if "python-ready" in command:
                markers.append("python-ready")
            elif "flask-ready" in command:
                markers.append("flask-ready")
            elif "node-ready" in command:
                markers.append("node-ready")
            elif "pnpm-ready" in command:
                markers.append("pnpm-ready")
            elif "go version" in command:
                markers.append("go version")
            elif "cargo --version" in command:
                markers.append("cargo")
            elif "java -version" in command:
                markers.append("version")
            elif "manage.py check" in command:
                markers.append("system check")
        return markers[:10]
