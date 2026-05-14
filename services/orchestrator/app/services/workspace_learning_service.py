from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from packages.contracts.python.models import WorkspaceUpdate
from services.memory import MemoryStoreProtocol

from app.services.workspace_readiness import compute_workspace_readiness


@dataclass(slots=True)
class WorkspaceLearningService:
    store: MemoryStoreProtocol

    def record_success(
        self,
        *,
        workspace_id: UUID | None,
        provider: str,
        model: str,
        profile: str,
        policy: dict[str, object],
        runner: dict[str, object],
        command_results: list[dict[str, object]],
    ) -> None:
        if workspace_id is None:
            return
        workspace = self.store.get_workspace(workspace_id)
        if workspace is None:
            return
        metadata = dict(workspace.metadata)
        learning = dict(metadata.get("learning") or {})
        commands_ok = [
            str(item.get("command"))
            for item in command_results
            if str(item.get("status")) == "ok" and item.get("command")
        ]
        learning["last_successful_provider"] = provider
        learning["last_successful_model"] = model
        learning["last_successful_profile"] = profile
        learning["last_successful_runner"] = runner.get("name")
        learning["last_successful_policy_pack"] = policy.get("policy_pack")
        learning["successful_commands"] = commands_ok[:20]
        learning["success_count"] = int(learning.get("success_count") or 0) + 1
        learning["updated_at"] = datetime.now(timezone.utc).isoformat()
        metadata["learning"] = learning
        metadata["workspace_readiness"] = compute_workspace_readiness(
            scan=dict(metadata.get("scan") or {}),
            contract=dict(metadata.get("syncore_contract") or {}),
            runner=dict(metadata.get("workspace_runner") or runner),
            learning=learning,
        )
        self.store.update_workspace(workspace_id, WorkspaceUpdate(metadata=metadata))

    def record_failure(
        self,
        *,
        workspace_id: UUID | None,
        reason: str,
        category: str,
        strategy: str,
    ) -> None:
        if workspace_id is None:
            return
        workspace = self.store.get_workspace(workspace_id)
        if workspace is None:
            return
        metadata = dict(workspace.metadata)
        learning = dict(metadata.get("learning") or {})
        failures = list(learning.get("recent_failures") or [])
        failures.append(
            {
                "category": category,
                "strategy": strategy,
                "reason": reason[:200],
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        learning["recent_failures"] = failures[-10:]
        learning["failure_count"] = int(learning.get("failure_count") or 0) + 1
        learning["updated_at"] = datetime.now(timezone.utc).isoformat()
        metadata["learning"] = learning
        metadata["workspace_readiness"] = compute_workspace_readiness(
            scan=dict(metadata.get("scan") or {}),
            contract=dict(metadata.get("syncore_contract") or {}),
            runner=dict(metadata.get("workspace_runner") or {}),
            learning=learning,
        )
        self.store.update_workspace(workspace_id, WorkspaceUpdate(metadata=metadata))
