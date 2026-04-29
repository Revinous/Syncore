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
    ResearchFinding,
    ResearchFindingCreate,
    Task,
    TaskCreate,
    TaskUpdate,
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
    Notification,
)


class SQLiteMemoryStore:
    def __init__(self, sqlite_db_path: str) -> None:
        self._sqlite_db_path = sqlite_db_path
        Path(self._sqlite_db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_task_workspace_column()
        self._ensure_context_bundle_columns()
        self._ensure_research_and_notifications_tables()

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

    def _ensure_context_bundle_columns(self) -> None:
        required_columns: dict[str, str] = {
            "raw_estimated_tokens": "INTEGER NOT NULL DEFAULT 0",
            "optimized_estimated_tokens": "INTEGER NOT NULL DEFAULT 0",
            "token_savings_estimate": "INTEGER NOT NULL DEFAULT 0",
            "token_savings_pct": "REAL NOT NULL DEFAULT 0",
            "estimated_cost_raw_usd": "REAL",
            "estimated_cost_optimized_usd": "REAL",
            "estimated_cost_saved_usd": "REAL",
        }
        with sqlite3.connect(self._sqlite_db_path) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(context_bundles)").fetchall()
            }
            if not columns:
                return
            for name, definition in required_columns.items():
                if name in columns:
                    continue
                connection.execute(
                    f"ALTER TABLE context_bundles ADD COLUMN {name} {definition}"
                )
            connection.commit()

    def _ensure_research_and_notifications_tables(self) -> None:
        with sqlite3.connect(self._sqlite_db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_findings (
                  finding_id TEXT PRIMARY KEY,
                  task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
                  workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
                  title TEXT NOT NULL,
                  summary TEXT NOT NULL,
                  details TEXT NOT NULL,
                  impact_level TEXT NOT NULL DEFAULT 'medium',
                  source TEXT NOT NULL DEFAULT 'researcher',
                  created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                  id TEXT PRIMARY KEY,
                  category TEXT NOT NULL,
                  title TEXT NOT NULL,
                  body TEXT NOT NULL,
                  related_task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
                  related_workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
                  finding_id TEXT REFERENCES research_findings(finding_id) ON DELETE SET NULL,
                  acknowledged INTEGER NOT NULL DEFAULT 0,
                  acknowledged_at TEXT,
                  created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_notifications_ack_created ON notifications (acknowledged, created_at DESC)"
            )
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

    def upsert_context_reference_layer(
        self,
        *,
        ref_id: str,
        layer: str,
        content: str,
    ) -> dict[str, object]:
        layer_id = str(uuid4())
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO context_reference_layers (
                    layer_id, ref_id, layer, content, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(ref_id, layer) DO UPDATE SET
                    content=excluded.content
                """,
                (layer_id, ref_id, layer, content, self._now()),
            )
            row = connection.execute(
                """
                SELECT layer_id, ref_id, layer, content, created_at
                FROM context_reference_layers
                WHERE ref_id = ? AND layer = ?
                """,
                (ref_id, layer),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to persist context reference layer")
        return dict(row)

    def get_context_reference_layer(
        self, *, ref_id: str, layer: str
    ) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT layer_id, ref_id, layer, content, created_at
                FROM context_reference_layers
                WHERE ref_id = ? AND layer = ?
                """,
                (ref_id, layer),
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
        raw_estimated_tokens: int,
        optimized_estimated_tokens: int,
        token_savings_estimate: int,
        token_savings_pct: float,
        estimated_cost_raw_usd: float | None,
        estimated_cost_optimized_usd: float | None,
        estimated_cost_saved_usd: float | None,
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
                    raw_estimated_tokens,
                    optimized_estimated_tokens,
                    token_savings_estimate,
                    token_savings_pct,
                    estimated_cost_raw_usd,
                    estimated_cost_optimized_usd,
                    estimated_cost_saved_usd,
                    optimized_context,
                    included_refs,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bundle_id,
                    str(task_id),
                    target_agent,
                    target_model,
                    token_budget,
                    max(raw_estimated_tokens, 0),
                    max(optimized_estimated_tokens, 0),
                    token_savings_estimate,
                    token_savings_pct,
                    estimated_cost_raw_usd,
                    estimated_cost_optimized_usd,
                    estimated_cost_saved_usd,
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
                    raw_estimated_tokens,
                    optimized_estimated_tokens,
                    token_savings_estimate,
                    token_savings_pct,
                    estimated_cost_raw_usd,
                    estimated_cost_optimized_usd,
                    estimated_cost_saved_usd,
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
                    raw_estimated_tokens,
                    optimized_estimated_tokens,
                    token_savings_estimate,
                    token_savings_pct,
                    estimated_cost_raw_usd,
                    estimated_cost_optimized_usd,
                    estimated_cost_saved_usd,
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

    def list_recent_context_bundles(self, limit: int = 200) -> list[dict[str, object]]:
        bounded_limit = min(max(limit, 1), 1000)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    bundle_id,
                    task_id,
                    target_agent,
                    target_model,
                    token_budget,
                    raw_estimated_tokens,
                    optimized_estimated_tokens,
                    token_savings_estimate,
                    token_savings_pct,
                    estimated_cost_raw_usd,
                    estimated_cost_optimized_usd,
                    estimated_cost_saved_usd,
                    optimized_context,
                    included_refs,
                    created_at
                FROM context_bundles
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        records: list[dict[str, object]] = []
        for row in rows:
            record = dict(row)
            record["optimized_context"] = json.loads(record["optimized_context"])
            record["included_refs"] = json.loads(record["included_refs"])
            records.append(record)
        return records

    def enqueue_run_job(
        self, *, task_id: UUID, payload: dict[str, object], max_attempts: int = 3
    ) -> dict[str, object]:
        job_id = str(uuid4())
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO run_queue (
                    job_id, task_id, payload, status, attempt_count, max_attempts,
                    last_error, run_id, available_at, created_at, updated_at
                )
                VALUES (?, ?, ?, 'queued', 0, ?, NULL, NULL, ?, ?, ?)
                """,
                (
                    job_id,
                    str(task_id),
                    json.dumps(payload, ensure_ascii=True, sort_keys=True),
                    max(1, max_attempts),
                    now,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM run_queue WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to enqueue run job")
        record = dict(row)
        record["payload"] = json.loads(str(record["payload"]))
        return record

    def claim_next_run_job(self) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM run_queue
                WHERE status IN ('queued', 'retry') AND available_at <= ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (self._now(),),
            ).fetchone()
            if row is None:
                return None
            job_id = str(row["job_id"])
            connection.execute(
                """
                UPDATE run_queue
                SET status = 'running', updated_at = ?
                WHERE job_id = ? AND status IN ('queued', 'retry')
                """,
                (self._now(), job_id),
            )
            claimed = connection.execute(
                "SELECT * FROM run_queue WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if claimed is None:
            return None
        record = dict(claimed)
        record["payload"] = json.loads(str(record["payload"]))
        return record

    def complete_run_job(
        self,
        *,
        job_id: str,
        status: str,
        run_id: UUID | None = None,
        error: str | None = None,
    ) -> dict[str, object] | None:
        next_status = status if status in {"completed", "failed", "retry"} else "failed"
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT * FROM run_queue WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if existing is None:
                return None
            attempt_count = int(existing["attempt_count"])
            max_attempts = int(existing["max_attempts"])
            if next_status == "retry":
                attempt_count += 1
                if attempt_count >= max_attempts:
                    next_status = "failed"
            connection.execute(
                """
                UPDATE run_queue
                SET status = ?, attempt_count = ?, last_error = ?, run_id = ?, available_at = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    next_status,
                    attempt_count,
                    (error or "")[:500] if error else None,
                    str(run_id) if run_id is not None else None,
                    self._now(),
                    self._now(),
                    job_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM run_queue WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["payload"] = json.loads(str(record["payload"]))
        return record

    def save_autonomy_snapshot(
        self,
        *,
        task_id: UUID,
        cycle: int,
        stage: str,
        state: str,
        strategy: str,
        quality_score: int,
        details: dict[str, object],
    ) -> dict[str, object]:
        snapshot_id = str(uuid4())
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO autonomy_snapshots (
                    snapshot_id, task_id, cycle, stage, state, strategy, quality_score, details, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    str(task_id),
                    max(cycle, 1),
                    stage,
                    state,
                    strategy,
                    max(min(int(quality_score), 100), 0),
                    json.dumps(details, ensure_ascii=True, sort_keys=True),
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM autonomy_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to persist autonomy snapshot")
        record = dict(row)
        record["details"] = json.loads(str(record["details"]))
        return record

    def list_autonomy_snapshots(
        self, *, task_id: UUID, limit: int = 200
    ) -> list[dict[str, object]]:
        bounded_limit = min(max(limit, 1), 500)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM autonomy_snapshots
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (str(task_id), bounded_limit),
            ).fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            record = dict(row)
            record["details"] = json.loads(str(record["details"]))
            result.append(record)
        return result

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_research_finding(self, payload: ResearchFindingCreate) -> ResearchFinding:
        finding_id = str(uuid4())
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO research_findings (
                    finding_id, task_id, workspace_id, title, summary, details, impact_level, source, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding_id,
                    str(payload.task_id) if payload.task_id else None,
                    str(payload.workspace_id) if payload.workspace_id else None,
                    payload.title,
                    payload.summary,
                    payload.details,
                    payload.impact_level,
                    payload.source,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT finding_id, task_id, workspace_id, title, summary, details, impact_level, source, created_at
                FROM research_findings
                WHERE finding_id = ?
                """,
                (finding_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to create research finding")
        return ResearchFinding.model_validate(dict(row))

    def list_research_findings(
        self, task_id: UUID | None = None, workspace_id: UUID | None = None, limit: int = 100
    ) -> list[ResearchFinding]:
        bounded_limit = min(max(limit, 1), 500)
        query = """
            SELECT finding_id, task_id, workspace_id, title, summary, details, impact_level, source, created_at
            FROM research_findings
        """
        clauses: list[str] = []
        values: list[object] = []
        if task_id is not None:
            clauses.append("task_id = ?")
            values.append(str(task_id))
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            values.append(str(workspace_id))
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        values.append(bounded_limit)
        with self._connection() as connection:
            rows = connection.execute(query, tuple(values)).fetchall()
        return [ResearchFinding.model_validate(dict(row)) for row in rows]

    def create_notification(
        self,
        *,
        category: str,
        title: str,
        body: str,
        related_task_id: UUID | None = None,
        related_workspace_id: UUID | None = None,
        finding_id: UUID | None = None,
    ) -> Notification:
        notification_id = str(uuid4())
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO notifications (
                    id, category, title, body, related_task_id, related_workspace_id, finding_id, acknowledged, acknowledged_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
                """,
                (
                    notification_id,
                    category,
                    title,
                    body,
                    str(related_task_id) if related_task_id else None,
                    str(related_workspace_id) if related_workspace_id else None,
                    str(finding_id) if finding_id else None,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT id, category, title, body, related_task_id, related_workspace_id, finding_id, acknowledged, acknowledged_at, created_at
                FROM notifications
                WHERE id = ?
                """,
                (notification_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to create notification")
        return Notification.model_validate({**dict(row), "acknowledged": bool(dict(row)["acknowledged"])})

    def list_notifications(
        self, *, acknowledged: bool | None = None, limit: int = 100
    ) -> list[Notification]:
        bounded_limit = min(max(limit, 1), 500)
        query = """
            SELECT id, category, title, body, related_task_id, related_workspace_id, finding_id, acknowledged, acknowledged_at, created_at
            FROM notifications
        """
        values: list[object] = []
        if acknowledged is not None:
            query += " WHERE acknowledged = ?"
            values.append(1 if acknowledged else 0)
        query += " ORDER BY created_at DESC LIMIT ?"
        values.append(bounded_limit)
        with self._connection() as connection:
            rows = connection.execute(query, tuple(values)).fetchall()
        return [
            Notification.model_validate({**dict(row), "acknowledged": bool(dict(row)["acknowledged"])})
            for row in rows
        ]

    def get_notification(self, notification_id: UUID) -> Notification | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, category, title, body, related_task_id, related_workspace_id, finding_id, acknowledged, acknowledged_at, created_at
                FROM notifications
                WHERE id = ?
                """,
                (str(notification_id),),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["acknowledged"] = bool(record["acknowledged"])
        return Notification.model_validate(record)

    def acknowledge_notification(self, notification_id: UUID) -> Notification | None:
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE notifications
                SET acknowledged = 1, acknowledged_at = ?
                WHERE id = ?
                """,
                (now, str(notification_id)),
            )
            row = connection.execute(
                """
                SELECT id, category, title, body, related_task_id, related_workspace_id, finding_id, acknowledged, acknowledged_at, created_at
                FROM notifications
                WHERE id = ?
                """,
                (str(notification_id),),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["acknowledged"] = bool(record["acknowledged"])
        return Notification.model_validate(record)
