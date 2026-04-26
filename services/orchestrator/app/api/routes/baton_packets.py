from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from packages.contracts.python.models import BatonPacket, BatonPacketCreate

from app.config import Settings, get_settings
from app.services.baton_service import BatonService
from app.store_factory import build_memory_store

router = APIRouter(prefix="/baton-packets", tags=["baton-packets"])


def get_baton_service(settings: Settings = Depends(get_settings)) -> BatonService:
    return BatonService(build_memory_store(settings))


@router.post("", response_model=BatonPacket, status_code=201)
def create_baton_packet(
    payload: BatonPacketCreate,
    service: BatonService = Depends(get_baton_service),
) -> BatonPacket:
    try:
        return service.create_packet(payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{task_id}", response_model=list[BatonPacket])
def list_baton_packets_for_task(
    task_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    service: BatonService = Depends(get_baton_service),
) -> list[BatonPacket]:
    try:
        return service.list_packets_for_task(task_id=task_id, limit=limit)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/by-id/{packet_id}", response_model=BatonPacket)
def get_baton_packet_by_id(
    packet_id: UUID,
    service: BatonService = Depends(get_baton_service),
) -> BatonPacket:
    packet = service.get_packet(packet_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="Baton packet not found")

    return packet
