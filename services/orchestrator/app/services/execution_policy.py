from __future__ import annotations

from dataclasses import dataclass

from app.services.policy_packs import get_policy_pack


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


@dataclass(slots=True)
class ExecutionPolicyResolver:
    workspace_policy_profiles: dict[str, dict[str, object]]

    def resolve_workspace_policy(
        self,
        *,
        requested_profile: str,
        workspace_metadata: dict[str, object],
        task_preferences: dict[str, str],
    ) -> dict[str, object]:
        requested_profile = str(requested_profile or "").strip().lower()
        explicit_requested = requested_profile in self.workspace_policy_profiles
        profile = requested_profile if explicit_requested else "balanced"
        base = dict(self.workspace_policy_profiles[profile])
        pack_name = str(
            task_preferences.get("policy_pack")
            or workspace_metadata.get("policy_pack")
            or ""
        ).strip()
        pack = get_policy_pack(pack_name)
        if pack:
            override_profile = str(pack.get("profile") or "").strip()
            if (
                not explicit_requested
                and override_profile in self.workspace_policy_profiles
            ):
                base = dict(self.workspace_policy_profiles[override_profile])
                profile = override_profile
            pack_commands = tuple(pack.get("allow_commands") or ())
            if pack_commands:
                base["allow_commands"] = pack_commands
            pack_allowed_patterns = tuple(pack.get("allowed_command_patterns") or ())
            if pack_allowed_patterns:
                base["allowed_command_patterns"] = pack_allowed_patterns
            base["verification_required_commands"] = tuple(
                pack.get("verification_required_commands") or ()
            )
            base["allowed_actions"] = tuple(
                pack.get("allowed_actions") or base.get("allowed_actions") or ()
            )
            base["approval_required_paths"] = tuple(
                pack.get("approval_required_paths") or ()
            )
            base["network_policy"] = str(pack.get("network_policy") or "offline")
        runbook = dict(workspace_metadata.get("workspace_runbook") or {})
        runner_commands = dict(runbook.get("runner", {}).get("commands") or {})
        runbook_allowed = tuple(
            _string_list(runbook.get("allowed_commands"))
            + _string_list(runbook.get("runbook_commands"))
            + _string_list(runbook.get("setup_commands"))
            + _string_list(runbook.get("build_commands"))
            + _string_list(runbook.get("test_commands"))
            + _string_list(runbook.get("lint_commands"))
            + _string_list(runbook.get("format_commands"))
            + _string_list(runner_commands.get("setup"))
            + _string_list(runner_commands.get("build"))
            + _string_list(runner_commands.get("test"))
            + _string_list(runner_commands.get("lint"))
            + _string_list(runner_commands.get("format"))
        )
        if runbook_allowed:
            base["allow_commands"] = tuple(
                dict.fromkeys(tuple(base.get("allow_commands") or ()) + runbook_allowed)
            )
        runbook_probe_commands = tuple(_string_list(runbook.get("probe_commands")))
        if runbook_probe_commands:
            base["allow_commands"] = tuple(
                dict.fromkeys(
                    tuple(base.get("allow_commands") or ()) + runbook_probe_commands
                )
            )
        runbook_patterns = tuple(_string_list(runbook.get("allowed_command_patterns")))
        if runbook_patterns:
            base["allowed_command_patterns"] = runbook_patterns
        base["blocked_commands"] = tuple(_string_list(runbook.get("blocked_commands")))
        base["allowed_paths"] = tuple(_string_list(runbook.get("allowed_paths")))
        base["forbidden_paths"] = tuple(_string_list(runbook.get("forbidden_paths")))
        base["approval_required_paths"] = tuple(
            _string_list(runbook.get("approval_required_paths"))
        ) or tuple(base.get("approval_required_paths") or ())
        contract = dict(workspace_metadata.get("syncore_contract") or {})
        capabilities = dict(contract.get("capabilities") or {})
        allowed_actions = _string_list(capabilities.get("allow_actions"))
        if allowed_actions:
            base["allowed_actions"] = tuple(allowed_actions)
        denied_actions = _string_list(capabilities.get("deny_actions"))
        if denied_actions:
            base["denied_actions"] = tuple(denied_actions)
        base["profile"] = profile
        base["policy_pack"] = pack_name or None
        return base
