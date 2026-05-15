from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Callable

from app.runs.providers import LlmProvider
from app.services.workspace_acceptance_service import string_list
from app.services.workspace_execution_utils import (
    binary_install_suggestions,
    preflight_failure,
)


class WorkspacePreflightService:
    def __init__(
        self,
        *,
        providers: dict[str, LlmProvider],
        default_provider: str,
        setup_command_resolver: Callable[[dict[str, object], str, str], str],
    ) -> None:
        self._providers = providers
        self._default_provider = default_provider
        self._runner_default_command = setup_command_resolver

    def verify(
        self,
        *,
        root: Path,
        provider_hint: str | None,
        required_env: list[str] | None = None,
        required_binaries: list[str] | None = None,
        required_files: list[str] | None = None,
        supported_os: list[str] | None = None,
        runner: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if not root.exists() or not root.is_dir():
            return preflight_failure(
                reason="workspace root missing",
                suggestions=["Ensure the workspace path exists before running Syncore."],
            )
        if not os.access(root, os.R_OK | os.W_OK):
            return preflight_failure(
                reason="workspace root not writable/readable",
                suggestions=[
                    "Check filesystem permissions for the workspace directory.",
                    "Ensure the current user can read and write under the workspace root.",
                ],
            )
        provider_name = (provider_hint or self._default_provider or "local_echo").strip().lower()
        if provider_name and provider_name not in self._providers:
            return preflight_failure(
                reason=f"provider '{provider_name}' is not configured",
                suggestions=[
                    f"Configure credentials for provider '{provider_name}' in .env.",
                    "Use a configured provider or fall back to local_echo for dry runs.",
                ],
            )
        for env_name in required_env or []:
            if env_name and not os.getenv(env_name):
                return preflight_failure(
                    reason=f"required env var '{env_name}' is missing",
                    suggestions=[
                        f"Export {env_name}=... in the shell before starting Syncore.",
                        f"Add {env_name} to the workspace .env contract documentation.",
                    ],
                    missing_env=[env_name],
                )
        current_os = platform.system().lower()
        supported = [item.lower() for item in (supported_os or []) if item]
        if supported and current_os not in supported:
            return preflight_failure(
                reason=f"workspace contract does not support current os '{current_os}'",
                suggestions=[
                    "Run the workspace on a supported OS or update syncore.yaml environment.os.",
                ],
            )
        for binary in required_binaries or []:
            if binary and not self.binary_available(binary):
                return preflight_failure(
                    reason=f"required binary '{binary}' is missing from PATH",
                    suggestions=binary_install_suggestions(binary),
                    missing_binaries=[binary],
                )
        if runner:
            runner_expected = string_list(runner.get("expected_files"))
            if runner_expected and not any((root / rel).exists() for rel in runner_expected):
                return preflight_failure(
                    reason="workspace does not match the expected runner file layout",
                    suggestions=[
                        "Rescan the workspace and confirm the selected policy pack/runner.",
                        "Add an explicit runner to syncore.yaml if auto-detection is wrong.",
                    ],
                    missing_files=runner_expected,
                )
            commands_obj = runner.get("commands")
            commands = dict(commands_obj) if isinstance(commands_obj, dict) else {}
            setup_commands = string_list(commands.get("setup"))
            for command in setup_commands[:1]:
                binary = command.split()[0] if command.split() else ""
                if binary and not self.binary_available(binary):
                    return preflight_failure(
                        reason=f"runner setup binary '{binary}' is missing from PATH",
                        suggestions=binary_install_suggestions(binary),
                        missing_binaries=[binary],
                    )
        for rel in required_files or []:
            if rel and not (root / rel).exists():
                return preflight_failure(
                    reason=f"required file '{rel}' is missing",
                    suggestions=[
                        f"Create or restore '{rel}' before autonomous execution.",
                        "Update syncore.yaml if the contract no longer reflects the repo layout.",
                    ],
                    missing_files=[rel],
                )
        return {"status": "ok", "reason": "", "suggestions": []}

    def binary_available(self, binary: str) -> bool:
        return self.resolve_binary(binary) is not None

    def resolve_binary(self, binary: str) -> str | None:
        direct = shutil.which(binary)
        if direct:
            return direct
        aliases = {
            "python": ["python3", Path(sys.executable).name, sys.executable],
            "pip": ["pip3"],
        }
        for candidate in aliases.get(binary, []):
            resolved = shutil.which(candidate) if os.path.sep not in candidate else candidate
            if resolved and (os.path.sep not in candidate or Path(candidate).exists()):
                return resolved
        return None
