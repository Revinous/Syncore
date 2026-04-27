from uuid import UUID

from packages.contracts.python.models import BatonPacket, BatonPacketCreate
from services.memory import MemoryStoreProtocol


class BatonService:
    def __init__(self, store: MemoryStoreProtocol) -> None:
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

    def list_packets_global(self, limit: int = 50) -> list[BatonPacket]:
        all_packets: list[BatonPacket] = []
        for task in self._store.list_tasks(limit=200):
            all_packets.extend(self._store.list_baton_packets(task.id, limit=limit))
            if len(all_packets) >= limit:
                break
        all_packets.sort(key=lambda packet: packet.created_at, reverse=True)
        return all_packets[:limit]

    def get_latest_packet_for_task(self, task_id: UUID) -> BatonPacket | None:
        task = self._store.get_task(task_id)
        if task is None:
            raise LookupError("Task not found")
        return self._store.get_latest_baton_packet(task_id)
