from __future__ import annotations

from pathlib import Path
from uuid import UUID

from packages.contracts.python.models import Workspace, WorkspaceCreate, WorkspaceUpdate
from services.memory import MemoryStoreProtocol

from app.services.project_scanner import scan_project
from app.services.workspace_files import WorkspaceFilesService


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

        scan_metadata = scan_project(root_path=Path(workspace.root_path))
        updated_metadata = {
            **workspace.metadata,
            "scan": scan_metadata,
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
