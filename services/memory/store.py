from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from packages.contracts.python.models import (
    AgentRun,
    AgentRunCreate,
    AgentRunUpdate,
    BatonPacket,
    BatonPacketCreate,
    ProjectEvent,
    ProjectEventCreate,
    Task,
    TaskCreate,
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

    def create_task(self, task: TaskCreate) -> Task:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tasks (title, task_type, complexity)
                VALUES (%s, %s, %s)
                RETURNING id, title, status, task_type, complexity, created_at, updated_at
                """,
                (task.title, task.task_type, task.complexity),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to create task")

        return Task.model_validate(row)

    def get_task(self, task_id: UUID) -> Task | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, title, status, task_type, complexity, created_at, updated_at
                FROM tasks
                WHERE id = %s
                """,
                (task_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return Task.model_validate(row)

    def list_tasks(self, limit: int = 50) -> list[Task]:
        bounded_limit = min(max(limit, 1), 200)
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, title, status, task_type, complexity, created_at, updated_at
                FROM tasks
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (bounded_limit,),
            )
            rows = cursor.fetchall()

        return [Task.model_validate(row) for row in rows]

    def create_agent_run(self, run: AgentRunCreate) -> AgentRun:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_runs (task_id, role, status, input_summary)
                VALUES (%s, %s, %s, %s)
                RETURNING id, task_id, role, status, input_summary, output_summary,
                          error_message, created_at, updated_at
                """,
                (run.task_id, run.role, run.status, run.input_summary),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to create agent run")

        return AgentRun.model_validate(row)

    def update_agent_run(self, run_id: UUID, update: AgentRunUpdate) -> AgentRun | None:
        assignments: list[str] = []
        values: list[object] = []

        if update.status is not None:
            assignments.append("status = %s")
            values.append(update.status)
        if update.output_summary is not None:
            assignments.append("output_summary = %s")
            values.append(update.output_summary)
        if update.error_message is not None:
            assignments.append("error_message = %s")
            values.append(update.error_message)

        if not assignments:
            raise ValueError("At least one field must be provided for run update")

        assignments.append("updated_at = NOW()")
        values.append(run_id)

        with self._cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE agent_runs
                SET {", ".join(assignments)}
                WHERE id = %s
                RETURNING id, task_id, role, status, input_summary, output_summary,
                          error_message, created_at, updated_at
                """,
                tuple(values),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return AgentRun.model_validate(row)

    def list_agent_runs(self, task_id: UUID, limit: int = 50) -> list[AgentRun]:
        bounded_limit = min(max(limit, 1), 200)
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, task_id, role, status, input_summary, output_summary,
                       error_message, created_at, updated_at
                FROM agent_runs
                WHERE task_id = %s
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (task_id, bounded_limit),
            )
            rows = cursor.fetchall()

        return [AgentRun.model_validate(row) for row in rows]

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
                    Json(packet.payload.model_dump()),
                ),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to persist baton packet")

        return BatonPacket.model_validate(row)

    def get_baton_packet(self, packet_id: UUID) -> BatonPacket | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, task_id, from_agent, to_agent, summary, payload, created_at
                FROM baton_packets
                WHERE id = %s
                """,
                (packet_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return BatonPacket.model_validate(row)

    def get_latest_baton_packet(self, task_id: UUID) -> BatonPacket | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, task_id, from_agent, to_agent, summary, payload, created_at
                FROM baton_packets
                WHERE task_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (task_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

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

        parsed = [ProjectEvent.model_validate(row) for row in rows]
        parsed.reverse()
        return parsed

    def count_project_events(self, task_id: UUID) -> int:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)::int AS total
                FROM project_events
                WHERE task_id = %s
                """,
                (task_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return 0

        return int(row["total"])

    def upsert_context_reference(
        self,
        *,
        ref_id: str,
        task_id: UUID,
        content_type: str,
        original_content: str,
        summary: str,
        retrieval_hint: str,
    ) -> dict[str, object]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO context_references (
                    ref_id,
                    task_id,
                    content_type,
                    original_content,
                    summary,
                    retrieval_hint
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (ref_id) DO UPDATE
                SET
                    summary = EXCLUDED.summary,
                    retrieval_hint = EXCLUDED.retrieval_hint
                RETURNING
                    ref_id,
                    task_id,
                    content_type,
                    original_content,
                    summary,
                    retrieval_hint,
                    created_at
                """,
                (
                    ref_id,
                    task_id,
                    content_type,
                    original_content,
                    summary,
                    retrieval_hint,
                ),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to persist context reference")
        return row

    def get_context_reference(self, ref_id: str) -> dict[str, object] | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ref_id,
                    task_id,
                    content_type,
                    original_content,
                    summary,
                    retrieval_hint,
                    created_at
                FROM context_references
                WHERE ref_id = %s
                """,
                (ref_id,),
            )
            row = cursor.fetchone()
        return row

    def save_context_bundle(
        self,
        *,
        task_id: UUID,
        target_agent: str,
        target_model: str,
        token_budget: int,
        optimized_context: dict[str, object],
        included_refs: list[str],
    ) -> dict[str, object]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO context_bundles (
                    task_id,
                    target_agent,
                    target_model,
                    token_budget,
                    optimized_context,
                    included_refs
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING
                    bundle_id,
                    task_id,
                    target_agent,
                    target_model,
                    token_budget,
                    optimized_context,
                    included_refs,
                    created_at
                """,
                (
                    task_id,
                    target_agent,
                    target_model,
                    token_budget,
                    Json(optimized_context),
                    included_refs,
                ),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to persist optimized context bundle")
        return row

    def get_latest_context_bundle(self, task_id: UUID) -> dict[str, object] | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    bundle_id,
                    task_id,
                    target_agent,
                    target_model,
                    token_budget,
                    optimized_context,
                    included_refs,
                    created_at
                FROM context_bundles
                WHERE task_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (task_id,),
            )
            row = cursor.fetchone()

        return row
