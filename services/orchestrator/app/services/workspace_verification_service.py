from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

CommandRunner = Callable[[Path, str, dict[str, object]], dict[str, object]]
CommandNormalizer = Callable[[str], str]


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


@dataclass(slots=True)
class WorkspaceVerificationService:
    run_command: CommandRunner
    normalize_command: CommandNormalizer

    def verify_workspace_execution(
        self,
        *,
        changed_files: list[str],
        command_results: list[dict[str, object]],
        root: Path,
        task_preferences: dict[str, str],
        contract: dict[str, object],
        runbook: dict[str, object],
        runner: dict[str, object] | None = None,
        policy: dict[str, object] | None = None,
    ) -> dict[str, object]:
        acceptance = self.merged_acceptance_criteria(
            task_preferences=task_preferences,
            contract=contract,
            runbook=runbook,
        )
        enriched_command_results = list(command_results)
        behavioral = self.run_behavioral_probes(
            root=root,
            acceptance=acceptance,
            policy=policy or {},
            command_results=enriched_command_results,
        )
        if behavioral["status"] != "ok":
            return behavioral
        forbidden_paths = _string_list(runbook.get("forbidden_paths"))
        risk_rules = dict(runbook.get("risk_rules") or contract.get("risk_rules") or {})
        mechanical = self.verify_mechanical_gates(
            command_results=enriched_command_results,
            acceptance=acceptance,
            runner=runner or {},
        )
        if mechanical["status"] != "ok":
            return mechanical
        diff_risk = self.verify_diff_risk(
            changed_files=changed_files,
            forbidden_paths=forbidden_paths,
            risk_rules=risk_rules,
        )
        if diff_risk["status"] != "ok":
            return diff_risk
        acceptance_result = self.verify_acceptance_criteria(
            root=root,
            changed_files=changed_files,
            acceptance=acceptance,
        )
        if acceptance_result["status"] != "ok":
            return acceptance_result
        secret_check = self.verify_secret_safety(root=root, changed_files=changed_files)
        if secret_check["status"] != "ok":
            return secret_check
        failed_cmds = [
            item
            for item in enriched_command_results
            if str(item.get("status")) in {"failed", "blocked"}
        ]
        if not changed_files and not enriched_command_results:
            return {
                "status": "failed",
                "reason": "No changes or verification commands were produced.",
            }
        if failed_cmds:
            return {
                "status": "ok",
                "reason": "",
                "warnings": [
                    "Optional workspace commands failed or were blocked after required "
                    "verification passed."
                ],
                "failed_commands": [str(item.get("command")) for item in failed_cmds[:10]],
            }
        return {"status": "ok", "reason": ""}

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
            "must_pass_commands": _string_list(source_dict.get("must_pass_commands")),
            "must_modify_paths": _string_list(source_dict.get("must_modify_paths")),
            "must_not_modify_paths": _string_list(source_dict.get("must_not_modify_paths")),
            "must_include_behavior": _string_list(source_dict.get("must_include_behavior")),
            "must_create_paths": _string_list(source_dict.get("must_create_paths")),
            "must_observe_output": _string_list(source_dict.get("must_observe_output")),
            "probe_commands": _string_list(source_dict.get("probe_commands")),
        }
        if not merged["probe_commands"]:
            merged["probe_commands"] = (
                _string_list(runbook.get("probe_commands"))
                or _string_list(runner_commands.get("probe"))
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
            required = _string_list(runner_commands.get("test"))[:1]
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
                    self.workspace_commands_match(command, observed)
                    for observed in observed_ok
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
    ) -> None:
        required = acceptance.get("must_pass_commands", [])
        if not required:
            runner_commands = dict(runner.get("commands") or {})
            required = _string_list(runner_commands.get("test"))[:1]
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
            result = self.run_command(root, command, policy)
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
    ) -> None:
        runner_commands = dict(runner.get("commands") or {})
        candidates = _string_list(runner_commands.get("test"))
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
            result = self.run_command(root, command, policy)
            command_results.append(result)
            if str(result.get("status")) == "ok":
                observed_ok.add(str(result.get("command") or command))

    def workspace_commands_match(self, expected: str, observed: str) -> bool:
        normalized_expected = self.normalize_command(expected).strip()
        normalized_observed = self.normalize_command(observed).strip()
        if not normalized_expected or not normalized_observed:
            return False
        return (
            normalized_expected == normalized_observed
            or normalized_expected in normalized_observed
            or normalized_observed in normalized_expected
        )

    def verify_diff_risk(
        self,
        *,
        changed_files: list[str],
        forbidden_paths: list[str],
        risk_rules: dict[str, object],
    ) -> dict[str, object]:
        if forbidden_paths:
            violations = [
                path
                for path in changed_files
                if any(
                    path == forbidden or path.startswith(forbidden.rstrip("/") + "/")
                    for forbidden in forbidden_paths
                )
            ]
            if violations:
                return {
                    "status": "failed",
                    "reason": "Workspace changed forbidden paths.",
                    "violations": violations[:20],
                }
        max_changed = risk_rules.get("max_changed_files")
        if (
            isinstance(max_changed, int)
            and max_changed > 0
            and len(set(changed_files)) > max_changed
        ):
            return {
                "status": "failed",
                "reason": "Workspace changed too many files for current risk budget.",
                "changed_files": len(set(changed_files)),
                "limit": max_changed,
            }
        return {"status": "ok", "reason": ""}

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

    def run_behavioral_probes(
        self,
        *,
        root: Path,
        acceptance: dict[str, list[str]],
        policy: dict[str, object],
        command_results: list[dict[str, object]],
    ) -> dict[str, object]:
        probe_commands = acceptance.get("probe_commands", [])
        for command in probe_commands:
            result = self.run_command(root, command, policy or {})
            command_results.append(result)
            if str(result.get("status")) != "ok":
                return {
                    "status": "failed",
                    "reason": "Behavioral probe command failed.",
                    "failed_command": command,
                }
        expected_output = acceptance.get("must_observe_output", [])
        if expected_output:
            observed_output = "\n".join(
                str(item.get("output") or "")
                for item in command_results
                if str(item.get("status")) == "ok"
            ).lower()
            missing_output = [
                marker for marker in expected_output if marker.lower() not in observed_output
            ]
            if missing_output:
                return {
                    "status": "failed",
                    "reason": "Expected behavioral output markers were not observed.",
                    "missing_output_markers": missing_output,
                }
        return {"status": "ok", "reason": ""}

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

    def verify_secret_safety(
        self,
        *,
        root: Path,
        changed_files: list[str],
    ) -> dict[str, object]:
        secret_markers = ("api_key", "secret_key", "sk-proj-", "BEGIN PRIVATE KEY")
        for rel in changed_files[:50]:
            target = root / rel
            if not target.exists() or not target.is_file():
                continue
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lowered = content.lower()
            if any(marker.lower() in lowered for marker in secret_markers):
                return {
                    "status": "failed",
                    "reason": "Potential secret material detected in changed files.",
                    "path": rel,
                }
        return {"status": "ok", "reason": ""}
