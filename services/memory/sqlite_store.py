from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import UUID, uuid4

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


class SQLiteMemoryStore:
    def __init__(self, sqlite_db_path: str) -> None:
        self._sqlite_db_path = sqlite_db_path
        Path(self._sqlite_db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._sqlite_db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def create_task(self, task: TaskCreate) -> Task:
        task_id = str(uuid4())
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO tasks (id, title, status, task_type, complexity, created_at, updated_at)
                VALUES (?, ?, 'new', ?, ?, ?, ?)
                """,
                (task_id, task.title, task.task_type, task.complexity, now, now),
            )
            row = connection.execute(
                """
                SELECT id, title, status, task_type, complexity, created_at, updated_at
                FROM tasks
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to create task")
        return Task.model_validate(dict(row))

    def get_task(self, task_id: UUID) -> Task | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, title, status, task_type, complexity, created_at, updated_at
                FROM tasks
                WHERE id = ?
                """,
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        return Task.model_validate(dict(row))

    def list_tasks(self, limit: int = 50) -> list[Task]:
        bounded_limit = min(max(limit, 1), 200)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, title, status, task_type, complexity, created_at, updated_at
                FROM tasks
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [Task.model_validate(dict(row)) for row in rows]

    def create_agent_run(self, run: AgentRunCreate) -> AgentRun:
        run_id = str(uuid4())
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    id,
                    task_id,
                    role,
                    status,
                    input_summary,
                    output_summary,
                    error_message,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                """,
                (run_id, str(run.task_id), run.role, run.status, run.input_summary, now, now),
            )
            row = connection.execute(
                """
                SELECT id, task_id, role, status, input_summary, output_summary,
                       error_message, created_at, updated_at
                FROM agent_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to create agent run")
        return AgentRun.model_validate(dict(row))

    def update_agent_run(self, run_id: UUID, update: AgentRunUpdate) -> AgentRun | None:
        assignments: list[str] = []
        values: list[object] = []

        if update.status is not None:
            assignments.append("status = ?")
            values.append(update.status)
        if update.output_summary is not None:
            assignments.append("output_summary = ?")
            values.append(update.output_summary)
        if update.error_message is not None:
            assignments.append("error_message = ?")
            values.append(update.error_message)

        if not assignments:
            raise ValueError("At least one field must be provided for run update")

        assignments.append("updated_at = ?")
        values.append(self._now())
        values.append(str(run_id))

        with self._connection() as connection:
            connection.execute(
                f"""
                UPDATE agent_runs
                SET {", ".join(assignments)}
                WHERE id = ?
                """,
                tuple(values),
            )
            row = connection.execute(
                """
                SELECT id, task_id, role, status, input_summary, output_summary,
                       error_message, created_at, updated_at
                FROM agent_runs
                WHERE id = ?
                """,
                (str(run_id),),
            ).fetchone()
        if row is None:
            return None
        return AgentRun.model_validate(dict(row))

    def list_agent_runs(self, task_id: UUID, limit: int = 50) -> list[AgentRun]:
        bounded_limit = min(max(limit, 1), 200)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, task_id, role, status, input_summary, output_summary,
                       error_message, created_at, updated_at
                FROM agent_runs
                WHERE task_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (str(task_id), bounded_limit),
            ).fetchall()
        return [AgentRun.model_validate(dict(row)) for row in rows]

    def save_baton_packet(self, packet: BatonPacketCreate) -> BatonPacket:
        packet_id = str(uuid4())
        now = self._now()
        payload = json.dumps(packet.payload.model_dump(), ensure_ascii=True, sort_keys=True)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO baton_packets (
                    id, task_id, from_agent, to_agent, summary, payload, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    packet_id,
                    str(packet.task_id),
                    packet.from_agent,
                    packet.to_agent,
                    packet.summary,
                    payload,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT id, task_id, from_agent, to_agent, summary, payload, created_at
                FROM baton_packets
                WHERE id = ?
                """,
                (packet_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to persist baton packet")
        parsed = dict(row)
        parsed["payload"] = json.loads(parsed["payload"])
        return BatonPacket.model_validate(parsed)

    def get_baton_packet(self, packet_id: UUID) -> BatonPacket | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, task_id, from_agent, to_agent, summary, payload, created_at
                FROM baton_packets
                WHERE id = ?
                """,
                (str(packet_id),),
            ).fetchone()
        if row is None:
            return None
        parsed = dict(row)
        parsed["payload"] = json.loads(parsed["payload"])
        return BatonPacket.model_validate(parsed)

    def get_latest_baton_packet(self, task_id: UUID) -> BatonPacket | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, task_id, from_agent, to_agent, summary, payload, created_at
                FROM baton_packets
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        parsed = dict(row)
        parsed["payload"] = json.loads(parsed["payload"])
        return BatonPacket.model_validate(parsed)

    def list_baton_packets(self, task_id: UUID, limit: int = 20) -> list[BatonPacket]:
        bounded_limit = min(max(limit, 1), 200)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, task_id, from_agent, to_agent, summary, payload, created_at
                FROM baton_packets
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (str(task_id), bounded_limit),
            ).fetchall()
        parsed_rows = []
        for row in rows:
            parsed = dict(row)
            parsed["payload"] = json.loads(parsed["payload"])
            parsed_rows.append(BatonPacket.model_validate(parsed))
        return parsed_rows

    def save_project_event(self, event: ProjectEventCreate) -> ProjectEvent:
        event_id = str(uuid4())
        now = self._now()
        event_data = json.dumps(event.event_data, ensure_ascii=True, sort_keys=True)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO project_events (id, task_id, event_type, event_data, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, str(event.task_id), event.event_type, event_data, now),
            )
            row = connection.execute(
                """
                SELECT id, task_id, event_type, event_data, created_at
                FROM project_events
                WHERE id = ?
                """,
                (event_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to persist project event")
        parsed = dict(row)
        parsed["event_data"] = json.loads(parsed["event_data"])
        return ProjectEvent.model_validate(parsed)

    def list_project_events(self, task_id: UUID, limit: int = 50) -> list[ProjectEvent]:
        bounded_limit = min(max(limit, 1), 200)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, task_id, event_type, event_data, created_at
                FROM project_events
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (str(task_id), bounded_limit),
            ).fetchall()
        parsed = []
        for row in rows:
            record = dict(row)
            record["event_data"] = json.loads(record["event_data"])
            parsed.append(ProjectEvent.model_validate(record))
        parsed.reverse()
        return parsed

    def count_project_events(self, task_id: UUID) -> int:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM project_events
                WHERE task_id = ?
                """,
                (str(task_id),),
            ).fetchone()
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
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO context_references (
                    ref_id,
                    task_id,
                    content_type,
                    original_content,
                    summary,
                    retrieval_hint,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ref_id) DO UPDATE SET
                    summary=excluded.summary,
                    retrieval_hint=excluded.retrieval_hint
                """,
                (
                    ref_id,
                    str(task_id),
                    content_type,
                    original_content,
                    summary,
                    retrieval_hint,
                    self._now(),
                ),
            )
            row = connection.execute(
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
                WHERE ref_id = ?
                """,
                (ref_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to persist context reference")
        return dict(row)

    def get_context_reference(self, ref_id: str) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
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
                WHERE ref_id = ?
                """,
                (ref_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

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
        bundle_id = str(uuid4())
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO context_bundles (
                    bundle_id,
                    task_id,
                    target_agent,
                    target_model,
                    token_budget,
                    optimized_context,
                    included_refs,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bundle_id,
                    str(task_id),
                    target_agent,
                    target_model,
                    token_budget,
                    json.dumps(optimized_context, ensure_ascii=True, sort_keys=True),
                    json.dumps(included_refs, ensure_ascii=True),
                    self._now(),
                ),
            )
            row = connection.execute(
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
                WHERE bundle_id = ?
                """,
                (bundle_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to persist optimized context bundle")
        record = dict(row)
        record["optimized_context"] = json.loads(record["optimized_context"])
        record["included_refs"] = json.loads(record["included_refs"])
        return record

    def get_latest_context_bundle(self, task_id: UUID) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
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
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["optimized_context"] = json.loads(record["optimized_context"])
        record["included_refs"] = json.loads(record["included_refs"])
        return record

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
