from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from .client import SyncoreApiClient, SyncoreApiError


def resolve_workspace_id(client: SyncoreApiClient, identifier: str) -> str:
    try:
        return str(UUID(identifier))
    except ValueError:
        pass

    workspaces = client.list_workspaces()
    for workspace in workspaces:
        if workspace.get("name") == identifier:
            return str(workspace["id"])

    raise SyncoreApiError(f"Workspace not found: {identifier}")


def normalize_path(path_str: str) -> Path:
    candidate = Path(path_str).expanduser()
    if not candidate.is_absolute():
        caller_cwd = os.getenv("SYNCORE_CALLER_CWD")
        base = Path(caller_cwd) if caller_cwd else Path.cwd()
        candidate = base / candidate
    return candidate.resolve()


def find_workspace_by_root(
    workspaces: list[dict[str, object]], root_path: Path
) -> dict[str, object] | None:
    root = str(root_path)
    for workspace in workspaces:
        if str(workspace.get("root_path", "")) == root:
            return workspace
    return None


def resolve_or_create_workspace(
    client: SyncoreApiClient, workspace_id_or_name: str
) -> tuple[str, dict[str, object]]:
    workspaces = client.list_workspaces()
    for workspace in workspaces:
        if str(workspace.get("id")) == workspace_id_or_name:
            workspace_id = str(workspace["id"])
            return workspace_id, client.get_workspace(workspace_id)
        if str(workspace.get("name")) == workspace_id_or_name:
            workspace_id = str(workspace["id"])
            return workspace_id, client.get_workspace(workspace_id)

    path_candidate = normalize_path(workspace_id_or_name)
    if path_candidate.exists() and path_candidate.is_dir():
        existing = find_workspace_by_root(workspaces, path_candidate)
        if existing is not None:
            workspace_id = str(existing["id"])
            return workspace_id, client.get_workspace(workspace_id)

        created = client.create_workspace(
            {
                "name": path_candidate.name or "workspace",
                "root_path": str(path_candidate),
                "repo_url": None,
                "branch": None,
                "runtime_mode": "native",
                "metadata": {},
            }
        )
        workspace_id = str(created["id"])
        return workspace_id, client.get_workspace(workspace_id)

    raise SyncoreApiError(
        f"Workspace not found: {workspace_id_or_name}. "
        "Pass an existing workspace name/id or a local directory path."
    )
