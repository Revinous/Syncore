from __future__ import annotations

from pathlib import Path


class WorkspaceProbeService:
    def __init__(self, run_command) -> None:
        self._run_command = run_command

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
            result = self._run_command(root, command, policy or {})
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
