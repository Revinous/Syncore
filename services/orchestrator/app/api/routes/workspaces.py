from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from packages.contracts.python.models import Workspace, WorkspaceCreate, WorkspaceUpdate
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services.workspace_service import WorkspaceService
from app.store_factory import build_memory_store

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def get_workspace_service(settings: Settings = Depends(get_settings)) -> WorkspaceService:
    return WorkspaceService(build_memory_store(settings))


class WorkspaceScanResponse(BaseModel):
    workspace: Workspace
    scan: dict[str, list[str]] = Field(default_factory=dict)


class WorkspaceFilesResponse(BaseModel):
    workspace_id: UUID
    root_path: str
    files: list[str] = Field(default_factory=list)
    count: int = Field(ge=0)


@router.post("", response_model=Workspace, status_code=201)
def create_workspace(
    payload: WorkspaceCreate,
    service: WorkspaceService = Depends(get_workspace_service),
) -> Workspace:
    return service.create_workspace(payload)


@router.get("", response_model=list[Workspace])
def list_workspaces(
    limit: int = Query(default=100, ge=1, le=500),
    service: WorkspaceService = Depends(get_workspace_service),
) -> list[Workspace]:
    return service.list_workspaces(limit=limit)


@router.get("/{workspace_id}", response_model=Workspace)
def get_workspace(
    workspace_id: UUID,
    service: WorkspaceService = Depends(get_workspace_service),
) -> Workspace:
    workspace = service.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.patch("/{workspace_id}", response_model=Workspace)
def update_workspace(
    workspace_id: UUID,
    payload: WorkspaceUpdate,
    service: WorkspaceService = Depends(get_workspace_service),
) -> Workspace:
    try:
        workspace = service.update_workspace(workspace_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(
    workspace_id: UUID,
    service: WorkspaceService = Depends(get_workspace_service),
) -> Response:
    deleted = service.delete_workspace(workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return Response(status_code=204)


@router.post("/{workspace_id}/scan", response_model=WorkspaceScanResponse)
def scan_workspace(
    workspace_id: UUID,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceScanResponse:
    try:
        workspace, scan = service.scan_workspace(workspace_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return WorkspaceScanResponse(workspace=workspace, scan=scan)


@router.get("/{workspace_id}/files", response_model=WorkspaceFilesResponse)
def list_workspace_files(
    workspace_id: UUID,
    path: str = Query(default="."),
    limit: int = Query(default=500, ge=1, le=2000),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceFilesResponse:
    try:
        workspace, files = service.list_workspace_files(
            workspace_id=workspace_id,
            relative_path=path,
            limit=limit,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return WorkspaceFilesResponse(
        workspace_id=workspace.id,
        root_path=workspace.root_path,
        files=files,
        count=len(files),
    )
