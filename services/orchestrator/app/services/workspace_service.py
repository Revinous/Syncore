from __future__ import annotations

from pathlib import Path
from uuid import UUID

from packages.contracts.python.models import Workspace, WorkspaceCreate, WorkspaceUpdate
from services.memory import MemoryStoreProtocol

from app.services.policy_packs import infer_policy_pack
from app.services.project_scanner import scan_project
from app.services.workspace_contract import build_runbook_from_contract, load_workspace_contract
from app.services.workspace_files import WorkspaceFilesService
from app.services.workspace_readiness import compute_workspace_readiness
from app.services.workspace_runners import select_workspace_runner


class WorkspaceService:
    def __init__(
        self,
        store: MemoryStoreProtocol,
        files_service: WorkspaceFilesService | None = None,
    ) -> None:
        self._store = store
        self._files_service = files_service or WorkspaceFilesService()

    def create_workspace(self, payload: WorkspaceCreate) -> Workspace:
        return self._store.create_workspace(payload)

    def list_workspaces(self, limit: int = 100) -> list[Workspace]:
        return self._store.list_workspaces(limit=limit)

    def get_workspace(self, workspace_id: UUID) -> Workspace | None:
        return self._store.get_workspace(workspace_id)

    def update_workspace(self, workspace_id: UUID, payload: WorkspaceUpdate) -> Workspace | None:
        return self._store.update_workspace(workspace_id, payload)

    def delete_workspace(self, workspace_id: UUID) -> bool:
        return self._store.delete_workspace(workspace_id)

    def scan_workspace(self, workspace_id: UUID) -> tuple[Workspace, dict[str, list[str]]]:
        workspace = self._store.get_workspace(workspace_id)
        if workspace is None:
            raise LookupError("Workspace not found")

        root = Path(workspace.root_path)
        scan_metadata = scan_project(root_path=root)
        contract = load_workspace_contract(root)
        contract_runbook = build_runbook_from_contract(contract)
        policy_pack = contract_runbook.get("policy_pack") or infer_policy_pack(scan_metadata)
        runner = select_workspace_runner(
            policy_pack=str(policy_pack) if policy_pack else None,
            scan=scan_metadata,
            contract=contract,
        )
        runbook_commands = list(contract_runbook.get("commands") or [])
        if not runbook_commands:
            for section in ("setup", "test", "lint", "build", "format"):
                runbook_commands.extend(list((runner.get("commands") or {}).get(section, [])))
        if not runbook_commands:
            runbook_commands = list(scan_metadata.get("runbook_commands", []))
        runbook = {
            "commands": runbook_commands,
            "command_sections": contract_runbook.get("command_sections", {}),
            "required_env": contract_runbook.get("required_env", []),
            "required_binaries": contract_runbook.get("required_binaries", []),
            "required_files": contract_runbook.get("required_files", []),
            "package_manager": contract_runbook.get("package_manager"),
            "forbidden_paths": contract_runbook.get("forbidden_paths", []),
            "allowed_paths": contract_runbook.get("allowed_paths", []),
            "allowed_commands": contract_runbook.get("allowed_commands", []),
            "allowed_command_patterns": contract_runbook.get(
                "allowed_command_patterns", []
            ),
            "blocked_commands": contract_runbook.get("blocked_commands", []),
            "approval_required_paths": contract_runbook.get(
                "approval_required_paths", []
            ),
            "entrypoints": contract_runbook.get("entrypoints", []),
            "acceptance": contract_runbook.get("acceptance", {}),
            "risk_rules": contract_runbook.get("risk_rules", {}),
            "network_policy": contract_runbook.get("network_policy", "offline"),
            "runner": runner,
            "probe_commands": list((runner.get("commands") or {}).get("probe", [])),
            "updated_at": workspace.updated_at.isoformat(),
        }
        readiness = compute_workspace_readiness(
            scan=scan_metadata,
            contract=contract,
            runner=runner,
            learning=dict(workspace.metadata.get("learning") or {}),
        )
        updated_metadata = {
            **workspace.metadata,
            "scan": scan_metadata,
            "syncore_contract": contract,
            "policy_pack": policy_pack,
            "workspace_runner": runner,
            "workspace_readiness": readiness,
            "workspace_runbook": runbook,
        }
        updated_workspace = self._store.update_workspace(
            workspace_id,
            WorkspaceUpdate(metadata=updated_metadata),
        )
        if updated_workspace is None:
            raise LookupError("Workspace not found")
        return updated_workspace, scan_metadata

    def list_workspace_files(
        self,
        workspace_id: UUID,
        relative_path: str = ".",
        limit: int = 500,
    ) -> tuple[Workspace, list[str]]:
        workspace = self._store.get_workspace(workspace_id)
        if workspace is None:
            raise LookupError("Workspace not found")

        files = self._files_service.list_files(
            root_path=workspace.root_path,
            relative_path=relative_path,
            limit=limit,
        )
        return workspace, files
