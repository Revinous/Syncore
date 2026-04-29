from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from packages.contracts.python.models import (
    Notification,
    NotificationAcknowledgeResponse,
    ResearchFinding,
    ResearchFindingCreate,
)
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.store_factory import build_memory_store

router = APIRouter(tags=["notifications"])


def get_store(settings: Settings = Depends(get_settings)):
    return build_memory_store(settings)


class NotificationListResponse(BaseModel):
    items: list[Notification]


@router.get("/notifications", response_model=NotificationListResponse)
def list_notifications(
    acknowledged: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    store=Depends(get_store),
) -> NotificationListResponse:
    return NotificationListResponse(
        items=store.list_notifications(acknowledged=acknowledged, limit=limit)
    )


@router.get("/notifications/{notification_id}", response_model=Notification)
def get_notification(
    notification_id: UUID,
    store=Depends(get_store),
) -> Notification:
    item = store.get_notification(notification_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return item


@router.post(
    "/notifications/{notification_id}/ack",
    response_model=NotificationAcknowledgeResponse,
)
def acknowledge_notification(
    notification_id: UUID,
    store=Depends(get_store),
) -> NotificationAcknowledgeResponse:
    item = store.acknowledge_notification(notification_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return NotificationAcknowledgeResponse(notification=item)


@router.post("/research/findings", response_model=ResearchFinding, status_code=201)
def create_research_finding(
    payload: ResearchFindingCreate,
    store=Depends(get_store),
) -> ResearchFinding:
    finding = store.create_research_finding(payload)
    store.create_notification(
        category="research.finding",
        title=f"Research: {finding.title}",
        body=finding.summary,
        related_task_id=finding.task_id,
        related_workspace_id=finding.workspace_id,
        finding_id=finding.finding_id,
    )
    return finding


@router.get("/research/findings", response_model=list[ResearchFinding])
def list_research_findings(
    task_id: UUID | None = Query(default=None),
    workspace_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    store=Depends(get_store),
) -> list[ResearchFinding]:
    return store.list_research_findings(
        task_id=task_id,
        workspace_id=workspace_id,
        limit=limit,
    )
