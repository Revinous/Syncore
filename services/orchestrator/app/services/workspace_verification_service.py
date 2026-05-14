from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.services.workspace_acceptance_service import WorkspaceAcceptanceService, string_list
from app.services.workspace_probe_service import WorkspaceProbeService
from app.services.workspace_risk_service import WorkspaceRiskService

CommandRunner = Callable[[Path, str, dict[str, object]], dict[str, object]]
CommandNormalizer = Callable[[str], str]


@dataclass(slots=True)
class WorkspaceVerificationService:
    run_command: CommandRunner
    normalize_command: CommandNormalizer
    _acceptance: WorkspaceAcceptanceService = field(init=False)
    _probes: WorkspaceProbeService = field(init=False)
    _risk: WorkspaceRiskService = field(init=False)

    def __post_init__(self) -> None:
        self._acceptance = WorkspaceAcceptanceService(self.normalize_command)
        self._probes = WorkspaceProbeService(self.run_command)
        self._risk = WorkspaceRiskService()

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
        acceptance = self._acceptance.merged_acceptance_criteria(
            task_preferences=task_preferences,
            contract=contract,
            runbook=runbook,
        )
        enriched_command_results = list(command_results)
        behavioral = self._probes.run_behavioral_probes(
            root=root,
            acceptance=acceptance,
            policy=policy or {},
            command_results=enriched_command_results,
        )
        if behavioral["status"] != "ok":
            return behavioral
        forbidden_paths = string_list(runbook.get("forbidden_paths"))
        risk_rules = dict(runbook.get("risk_rules") or contract.get("risk_rules") or {})
        mechanical = self._acceptance.verify_mechanical_gates(
            command_results=enriched_command_results,
            acceptance=acceptance,
            runner=runner or {},
        )
        if mechanical["status"] != "ok":
            return mechanical
        diff_risk = self._risk.verify_diff_risk(
            changed_files=changed_files,
            forbidden_paths=forbidden_paths,
            risk_rules=risk_rules,
        )
        if diff_risk["status"] != "ok":
            return diff_risk
        acceptance_result = self._acceptance.verify_acceptance_criteria(
            root=root,
            changed_files=changed_files,
            acceptance=acceptance,
        )
        if acceptance_result["status"] != "ok":
            return acceptance_result
        secret_check = self._risk.verify_secret_safety(root=root, changed_files=changed_files)
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
        return self._acceptance.merged_acceptance_criteria(
            task_preferences=task_preferences,
            contract=contract,
            runbook=runbook,
        )

    def verify_mechanical_gates(
        self,
        *,
        command_results: list[dict[str, object]],
        acceptance: dict[str, list[str]],
        runner: dict[str, object],
    ) -> dict[str, object]:
        return self._acceptance.verify_mechanical_gates(
            command_results=command_results,
            acceptance=acceptance,
            runner=runner,
        )

    def ensure_required_verification_commands_run(
        self,
        *,
        root: Path,
        command_results: list[dict[str, object]],
        acceptance: dict[str, list[str]],
        runner: dict[str, object],
        policy: dict[str, object],
    ) -> None:
        self._acceptance.ensure_required_verification_commands_run(
            root=root,
            command_results=command_results,
            acceptance=acceptance,
            runner=runner,
            policy=policy,
            run_command=self.run_command,
        )

    def run_all_runner_test_commands(
        self,
        *,
        root: Path,
        command_results: list[dict[str, object]],
        runner: dict[str, object],
        policy: dict[str, object],
    ) -> None:
        self._acceptance.run_all_runner_test_commands(
            root=root,
            command_results=command_results,
            runner=runner,
            policy=policy,
            run_command=self.run_command,
        )
