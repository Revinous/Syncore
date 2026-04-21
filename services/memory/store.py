from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from packages.contracts.python.models import (
    BatonPacket,
    BatonPacketCreate,
    ProjectEvent,
    ProjectEventCreate,
)


class MemoryStore:
    def __init__(self, postgres_dsn: str) -> None:
        self._postgres_dsn = postgres_dsn

    @contextmanager
    def _cursor(self) -> Iterator[psycopg.Cursor]:
        with psycopg.connect(self._postgres_dsn, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                yield cursor
            connection.commit()

    def save_baton_packet(self, packet: BatonPacketCreate) -> BatonPacket:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO baton_packets (task_id, from_agent, to_agent, summary, payload)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, task_id, from_agent, to_agent, summary, payload, created_at
                """,
                (
                    packet.task_id,
                    packet.from_agent,
                    packet.to_agent,
                    packet.summary,
                    Json(packet.payload),
                ),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to persist baton packet")

        return BatonPacket.model_validate(row)

    def list_baton_packets(self, task_id: UUID, limit: int = 20) -> list[BatonPacket]:
        bounded_limit = min(max(limit, 1), 200)
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, task_id, from_agent, to_agent, summary, payload, created_at
                FROM baton_packets
                WHERE task_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (task_id, bounded_limit),
            )
            rows = cursor.fetchall()

        return [BatonPacket.model_validate(row) for row in rows]

    def save_project_event(self, event: ProjectEventCreate) -> ProjectEvent:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO project_events (task_id, event_type, event_data)
                VALUES (%s, %s, %s)
                RETURNING id, task_id, event_type, event_data, created_at
                """,
                (
                    event.task_id,
                    event.event_type,
                    Json(event.event_data),
                ),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to persist project event")

        return ProjectEvent.model_validate(row)

    def list_project_events(self, task_id: UUID, limit: int = 50) -> list[ProjectEvent]:
        bounded_limit = min(max(limit, 1), 200)
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, task_id, event_type, event_data, created_at
                FROM project_events
                WHERE task_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (task_id, bounded_limit),
            )
            rows = cursor.fetchall()

        return [ProjectEvent.model_validate(row) for row in rows]
