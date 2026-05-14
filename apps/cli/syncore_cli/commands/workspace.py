from __future__ import annotations

from typing import Callable

import typer

from syncore_cli.client import SyncoreApiClient, SyncoreApiError


ClientFactory = Callable[[], SyncoreApiClient]
ResolveWorkspaceId = Callable[[SyncoreApiClient, str], str]


def register_workspace_commands(
    workspace_app: typer.Typer,
    *,
    client_factory: ClientFactory,
    resolve_workspace_id: ResolveWorkspaceId,
    print_error: Callable[[str], None],
    print_json: Callable[[object], None],
) -> None:
    @workspace_app.command("list")
    def workspace_list() -> None:
        client = client_factory()
        try:
            workspaces = client.list_workspaces()
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(workspaces)

    @workspace_app.command("add")
    def workspace_add(
        root_path: str,
        name: str = typer.Option(..., "--name"),
        repo_url: str | None = typer.Option(None, "--repo-url"),
        branch: str | None = typer.Option(None, "--branch"),
    ) -> None:
        client = client_factory()
        payload = {
            "name": name,
            "root_path": root_path,
            "repo_url": repo_url,
            "branch": branch,
            "runtime_mode": "native",
            "metadata": {},
        }
        try:
            created = client.create_workspace(payload)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(created)

    @workspace_app.command("show")
    def workspace_show(workspace_id_or_name: str) -> None:
        client = client_factory()
        try:
            workspace_id = resolve_workspace_id(client, workspace_id_or_name)
            workspace = client.get_workspace(workspace_id)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(workspace)

    @workspace_app.command("scan")
    def workspace_scan(workspace_id_or_name: str) -> None:
        client = client_factory()
        try:
            workspace_id = resolve_workspace_id(client, workspace_id_or_name)
            result = client.scan_workspace(workspace_id)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(result)

    @workspace_app.command("files")
    def workspace_files(workspace_id_or_name: str) -> None:
        client = client_factory()
        try:
            workspace_id = resolve_workspace_id(client, workspace_id_or_name)
            files = client.list_workspace_files(workspace_id)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(files)
