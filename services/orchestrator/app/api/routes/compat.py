from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from packages.contracts.python.models import (
    BatonPacket,
    ExecutiveDigest,
    ProjectEvent,
    RoutingDecision,
    RoutingRequest,
)
from services.analyst.digest import AnalystDigestService

from app.config import Settings, get_settings
from app.services.baton_service import BatonService
from app.services.event_service import EventService
from app.services.routing_service import RoutingService
from app.store_factory import build_memory_store

router = APIRouter(tags=["compat"])


def _ensure_eli5(digest: ExecutiveDigest) -> ExecutiveDigest:
    if (digest.eli5_summary or "").strip():
        return digest
    digest.eli5_summary = f"Simple summary: {digest.summary}"
    return digest


def get_event_service(settings: Settings = Depends(get_settings)) -> EventService:
    return EventService(build_memory_store(settings))


def get_baton_service(settings: Settings = Depends(get_settings)) -> BatonService:
    return BatonService(build_memory_store(settings))


def get_routing_service() -> RoutingService:
    return RoutingService()


@router.get("/tasks/{task_id}/events", response_model=list[ProjectEvent])
def list_task_events(
    task_id: UUID,
    limit: int = Query(default=100, ge=1, le=200),
    service: EventService = Depends(get_event_service),
) -> list[ProjectEvent]:
    return service.list_events(task_id=task_id, limit=limit)


@router.get("/tasks/{task_id}/baton-packets", response_model=list[BatonPacket])
def list_task_batons(
    task_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    service: BatonService = Depends(get_baton_service),
) -> list[BatonPacket]:
    try:
        return service.list_packets_for_task(task_id=task_id, limit=limit)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/tasks/{task_id}/baton-packets/latest", response_model=BatonPacket)
def latest_task_baton(
    task_id: UUID,
    service: BatonService = Depends(get_baton_service),
) -> BatonPacket:
    try:
        packet = service.get_latest_packet_for_task(task_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if packet is None:
        raise HTTPException(status_code=404, detail="No baton packets found for task")
    return packet


@router.get("/tasks/{task_id}/routing", response_model=RoutingDecision)
def get_task_routing(
    task_id: UUID,
    settings: Settings = Depends(get_settings),
    service: RoutingService = Depends(get_routing_service),
) -> RoutingDecision:
    store = build_memory_store(settings)
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return service.choose_next(
        payload=RoutingRequest(
            task_type=task.task_type,
            complexity=task.complexity,
            requires_memory=store.count_project_events(task_id) > 0,
        )
    )


@router.get("/tasks/{task_id}/digest", response_model=ExecutiveDigest)
def get_task_digest_compat(
    task_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    settings: Settings = Depends(get_settings),
) -> ExecutiveDigest:
    store = build_memory_store(settings)
    events = store.list_project_events(task_id=task_id, limit=limit)
    latest_baton = store.get_latest_baton_packet(task_id)
    return _ensure_eli5(
        AnalystDigestService().generate_digest(
            task_id=task_id,
            events=events,
            latest_baton=latest_baton,
        )
    )
