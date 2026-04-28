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
    TaskUpdate,
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
)


class SQLiteMemoryStore:
    def __init__(self, sqlite_db_path: str) -> None:
        self._sqlite_db_path = sqlite_db_path
        Path(self._sqlite_db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_task_workspace_column()

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

    def _ensure_task_workspace_column(self) -> None:
        with sqlite3.connect(self._sqlite_db_path) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if columns and "workspace_id" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN workspace_id TEXT")
                connection.commit()

    def create_task(self, task: TaskCreate) -> Task:
        task_id = str(uuid4())
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO tasks (id, title, status, task_type, complexity, workspace_id, created_at, updated_at)
                VALUES (?, ?, 'new', ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task.title,
                    task.task_type,
                    task.complexity,
                    str(task.workspace_id) if task.workspace_id else None,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT id, title, status, task_type, complexity, workspace_id, created_at, updated_at
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
                SELECT id, title, status, task_type, complexity, workspace_id, created_at, updated_at
                FROM tasks
                WHERE id = ?
                """,
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        return Task.model_validate(dict(row))

    def list_tasks(self, limit: int = 50, workspace_id: UUID | None = None) -> list[Task]:
        bounded_limit = min(max(limit, 1), 200)
        with self._connection() as connection:
            if workspace_id is None:
                rows = connection.execute(
                    """
                    SELECT id, title, status, task_type, complexity, workspace_id, created_at, updated_at
                    FROM tasks
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (bounded_limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, title, status, task_type, complexity, workspace_id, created_at, updated_at
                    FROM tasks
                    WHERE workspace_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (str(workspace_id), bounded_limit),
                ).fetchall()
        return [Task.model_validate(dict(row)) for row in rows]

    def update_task(self, task_id: UUID, payload: TaskUpdate) -> Task | None:
        assignments: list[str] = []
        values: list[object] = []

        if payload.title is not None:
            assignments.append("title = ?")
            values.append(payload.title)
        if payload.status is not None:
            assignments.append("status = ?")
            values.append(payload.status)
        if payload.task_type is not None:
            assignments.append("task_type = ?")
            values.append(payload.task_type)
        if payload.complexity is not None:
            assignments.append("complexity = ?")
            values.append(payload.complexity)
        if "workspace_id" in payload.model_fields_set:
            assignments.append("workspace_id = ?")
            values.append(str(payload.workspace_id) if payload.workspace_id else None)

        if not assignments:
            raise ValueError("At least one field must be provided for task update")

        assignments.append("updated_at = ?")
        values.append(self._now())
        values.append(str(task_id))

        with self._connection() as connection:
            connection.execute(
                f"""
                UPDATE tasks
                SET {", ".join(assignments)}
                WHERE id = ?
                """,
                tuple(values),
            )
            row = connection.execute(
                """
                SELECT id, title, status, task_type, complexity, workspace_id, created_at, updated_at
                FROM tasks
                WHERE id = ?
                """,
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        return Task.model_validate(dict(row))

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
                (
                    run_id,
                    str(run.task_id),
                    run.role,
                    run.status,
                    run.input_summary,
                    now,
                    now,
                ),
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

    def get_agent_run(self, run_id: UUID) -> AgentRun | None:
        with self._connection() as connection:
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

    def list_agent_runs(
        self, task_id: UUID | None = None, limit: int = 50
    ) -> list[AgentRun]:
        bounded_limit = min(max(limit, 1), 200)
        with self._connection() as connection:
            if task_id is None:
                rows = connection.execute(
                    """
                    SELECT id, task_id, role, status, input_summary, output_summary,
                           error_message, created_at, updated_at
                    FROM agent_runs
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (bounded_limit,),
                ).fetchall()
            else:
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
        payload = json.dumps(
            packet.payload.model_dump(), ensure_ascii=True, sort_keys=True
        )
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

    def list_project_events(
        self, task_id: UUID | None = None, limit: int = 50
    ) -> list[ProjectEvent]:
        bounded_limit = min(max(limit, 1), 200)
        with self._connection() as connection:
            if task_id is None:
                rows = connection.execute(
                    """
                    SELECT id, task_id, event_type, event_data, created_at
                    FROM project_events
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (bounded_limit,),
                ).fetchall()
            else:
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

    def create_workspace(self, payload: WorkspaceCreate) -> Workspace:
        workspace_id = str(uuid4())
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO workspaces (
                    id, name, root_path, repo_url, branch, runtime_mode, metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace_id,
                    payload.name,
                    payload.root_path,
                    payload.repo_url,
                    payload.branch,
                    payload.runtime_mode,
                    json.dumps(payload.metadata, ensure_ascii=True, sort_keys=True),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    root_path,
                    repo_url,
                    branch,
                    runtime_mode,
                    metadata,
                    created_at,
                    updated_at
                FROM workspaces
                WHERE id = ?
                """,
                (workspace_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to create workspace")
        record = dict(row)
        record["metadata"] = json.loads(record["metadata"])
        return Workspace.model_validate(record)

    def get_workspace(self, workspace_id: UUID) -> Workspace | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    root_path,
                    repo_url,
                    branch,
                    runtime_mode,
                    metadata,
                    created_at,
                    updated_at
                FROM workspaces
                WHERE id = ?
                """,
                (str(workspace_id),),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["metadata"] = json.loads(record["metadata"])
        return Workspace.model_validate(record)

    def list_workspaces(self, limit: int = 100) -> list[Workspace]:
        bounded_limit = min(max(limit, 1), 500)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    name,
                    root_path,
                    repo_url,
                    branch,
                    runtime_mode,
                    metadata,
                    created_at,
                    updated_at
                FROM workspaces
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        result: list[Workspace] = []
        for row in rows:
            record = dict(row)
            record["metadata"] = json.loads(record["metadata"])
            result.append(Workspace.model_validate(record))
        return result

    def update_workspace(
        self, workspace_id: UUID, payload: WorkspaceUpdate
    ) -> Workspace | None:
        assignments: list[str] = []
        values: list[object] = []

        if payload.name is not None:
            assignments.append("name = ?")
            values.append(payload.name)
        if payload.root_path is not None:
            assignments.append("root_path = ?")
            values.append(payload.root_path)
        if payload.repo_url is not None:
            assignments.append("repo_url = ?")
            values.append(payload.repo_url)
        if payload.branch is not None:
            assignments.append("branch = ?")
            values.append(payload.branch)
        if payload.runtime_mode is not None:
            assignments.append("runtime_mode = ?")
            values.append(payload.runtime_mode)
        if payload.metadata is not None:
            assignments.append("metadata = ?")
            values.append(
                json.dumps(payload.metadata, ensure_ascii=True, sort_keys=True)
            )

        if not assignments:
            raise ValueError("At least one field must be provided for workspace update")

        assignments.append("updated_at = ?")
        values.append(self._now())
        values.append(str(workspace_id))

        with self._connection() as connection:
            connection.execute(
                f"""
                UPDATE workspaces
                SET {", ".join(assignments)}
                WHERE id = ?
                """,
                tuple(values),
            )
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    root_path,
                    repo_url,
                    branch,
                    runtime_mode,
                    metadata,
                    created_at,
                    updated_at
                FROM workspaces
                WHERE id = ?
                """,
                (str(workspace_id),),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["metadata"] = json.loads(record["metadata"])
        return Workspace.model_validate(record)

    def delete_workspace(self, workspace_id: UUID) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                DELETE FROM workspaces
                WHERE id = ?
                """,
                (str(workspace_id),),
            )
        return cursor.rowcount > 0

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
