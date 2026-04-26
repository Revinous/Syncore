from uuid import UUID

from packages.contracts.python.models import BatonPacket, BatonPacketCreate
from services.memory.store import MemoryStore


class BatonService:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def create_packet(self, payload: BatonPacketCreate) -> BatonPacket:
        task = self._store.get_task(payload.task_id)
        if task is None:
            raise LookupError("Task not found")

        return self._store.save_baton_packet(payload)

    def get_packet(self, packet_id: UUID) -> BatonPacket | None:
        return self._store.get_baton_packet(packet_id)

    def list_packets_for_task(self, task_id: UUID, limit: int = 50) -> list[BatonPacket]:
        task = self._store.get_task(task_id)
        if task is None:
            raise LookupError("Task not found")

        return self._store.list_baton_packets(task_id=task_id, limit=limit)
